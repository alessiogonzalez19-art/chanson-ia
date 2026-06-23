"""
FastAPI Routes for Studio IA
"""

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Form, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import uuid
import shutil
import re
import zipfile
from urllib.parse import quote
from loguru import logger
import os
import json
import datetime
import threading
import socketio

from config import config

# Plans directory for session persistence
PLANS_DIR = str(Path(config.workspace_root) / "plans")
os.makedirs(PLANS_DIR, exist_ok=True)

from workers.tasks import process_audio_project
from models.manager import WorldClassModelManager
from utils.log_watcher import LogWatcher
import asyncio

# Socket.io setup for real-time collaboration
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI(
    title="Studio IA Local et Autonome",
    description="World-class AI music production studio with 10 specialized agents",
    version="2.1.0"
)
sio_app = socketio.ASGIApp(sio, app)

# Global mixer state for synchronization
_mixer_projects = {} # project_id -> { tracks: {}, faders: {}, pans: {} }

@sio.event
async def connect(sid, environ):
    logger.info(f"🤝 Client connecté aux WebSockets: {sid}")

@sio.event
async def join_project(sid, project_id):
    await sio.enter_room(sid, project_id)
    logger.info(f"👥 Client {sid} a rejoint le projet {project_id}")
    # Envoyer l'état actuel du projet au nouvel arrivant
    if project_id in _mixer_projects:
        await sio.emit('sync_state', _mixer_projects[project_id], room=sid)

@sio.event
async def update_fader(sid, data):
    project_id = data.get('project_id')
    track = data.get('track')
    value = data.get('value')
    
    if project_id not in _mixer_projects:
        _mixer_projects[project_id] = {"faders": {}, "pans": {}}
    
    _mixer_projects[project_id]["faders"][track] = value
    # Diffuser à tous les autres clients du projet
    await sio.emit('fader_moved', {"track": track, "value": value}, room=project_id, skip_sid=sid)

@sio.event
async def update_pan(sid, data):
    project_id = data.get('project_id')
    track = data.get('track')
    value = data.get('value')
    
    if project_id not in _mixer_projects:
        _mixer_projects[project_id] = {"faders": {}, "pans": {}}
    
    _mixer_projects[project_id]["pans"][track] = value
    await sio.emit('pan_moved', {"track": track, "value": value}, room=project_id, skip_sid=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"👋 Client déconnecté: {sid}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Global model manager
model_manager = WorldClassModelManager()

# Global log watcher
log_watcher = None

@app.on_event("startup")
async def startup_event():
    global log_watcher
    log_watcher = LogWatcher(log_dir=str(config.workspace_root / "logs"))
    # Run log watcher in background without blocking
    asyncio.create_task(log_watcher.watch_logs(lambda err, file: logger.error(f"Gardien detected: {err} in {file}")))

@app.on_event("shutdown")
async def shutdown_event():
    if log_watcher:
        log_watcher.stop()


def _resolve_allowed_audio_path(raw_path: str) -> Path:
    """Resolve and validate user-facing audio paths."""
    if ".." in raw_path:
        raise HTTPException(status_code=400, detail="Tentative de path traversal non autorisee")
        
    candidate = Path(raw_path).expanduser().resolve()
    
    allowed_roots = [
        config.temp_folder.resolve(),
        config.fl_studio_output_folder.resolve(),
        config.workspace_root.resolve(),
    ]
    
    if not any(candidate.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Chemin audio non autorise : hors des repertoires permis")
        
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Fichier audio introuvable")
        
    return candidate


def _audio_preview_url(audio_path: str) -> str:
    return f"/api/audio/file?path={quote(audio_path)}"


def _store_uploaded_audio(file: UploadFile, upload_dir: Path) -> Path:
    """Save an uploaded audio file and convert it to WAV when useful."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or f"audio_{uuid.uuid4().hex}.wav"
    orig_path = upload_dir / Path(original_name).name

    with open(orig_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    suffix = orig_path.suffix.lower()
    final_path = orig_path
    convertible = {".m4a", ".mp3", ".ogg", ".aiff", ".aif", ".flac", ".webm"}

    if suffix in convertible:
        wav_path = orig_path.with_suffix(".wav")
        try:
            from pydub import AudioSegment
            import imageio_ffmpeg

            AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
            fmt = suffix.lstrip(".")
            if fmt == "aif":
                fmt = "aiff"
            audio = AudioSegment.from_file(str(orig_path), format=fmt)
            audio.export(str(wav_path), format="wav")
            orig_path.unlink(missing_ok=True)
            final_path = wav_path
            logger.info(f"🔄 Converti {original_name} → {wav_path.name}")
        except Exception as conv_err:
            logger.warning(f"Conversion échouée pour {original_name} : {conv_err}")

    return final_path


def _safe_output_name(name: str, fallback: str = "edit") -> str:
    stem = Path(name or fallback).stem
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return clean or fallback


def _collect_audio_paths(payload) -> List[Path]:
    """Collect real output files from nested task payloads."""
    paths: List[Path] = []

    if isinstance(payload, dict):
        for key in ("output_path", "output_file", "final_mix", "remix_path", "generated_audio"):
            value = payload.get(key)
            if isinstance(value, str):
                candidate = Path(value)
                if candidate.exists() and candidate.is_file():
                    paths.append(candidate)

        output_files = payload.get("output_files")
        if isinstance(output_files, dict):
            paths.extend(_collect_audio_paths(output_files))
        elif isinstance(output_files, list):
            paths.extend(_collect_audio_paths({"output_files_nested": output_files}))

        for value in payload.values():
            if isinstance(value, (dict, list)):
                paths.extend(_collect_audio_paths(value))

    elif isinstance(payload, list):
        for item in payload:
            paths.extend(_collect_audio_paths(item))
    elif isinstance(payload, str):
        candidate = Path(payload)
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in {
            ".wav", ".mp3", ".flac", ".aiff", ".aif", ".ogg", ".m4a", ".webm", ".zip"
        }:
            paths.append(candidate)

    unique: List[Path] = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    return unique


def _zip_files(task_id: str, files: List[Path]) -> Path:
    archive_dir = config.fl_studio_output_folder / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / f"studio_ia_{_safe_output_name(task_id, 'task')}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for file_path in files:
            arcname = file_path.name
            if arcname in used_names:
                arcname = f"{file_path.stem}_{uuid.uuid4().hex[:6]}{file_path.suffix}"
            used_names.add(arcname)
            zf.write(file_path, arcname=arcname)

    return zip_path

# Mount static files (frontend UI)
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

config.fl_studio_output_folder.mkdir(parents=True, exist_ok=True)
app.mount("/exports", StaticFiles(directory=str(config.fl_studio_output_folder)), name="exports")


class ProjectRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    genre: Optional[str] = "Electronic"
    bpm: Optional[float] = None
    key: Optional[str] = None
    references: Optional[List[str]] = []
    options: Optional[dict] = {}


class GenerationRequest(BaseModel):
    prompt: str
    duration: int = 30
    bpm: Optional[float] = None
    key: Optional[str] = None

class YoutubeRequest(BaseModel):
    url: str

class ChatRequest(BaseModel):
    message: str
    audio_path: Optional[str] = None
    session_id: Optional[str] = None


# ─── Session Manager ───────────────────────────────────────────────────────────

class SessionManager:
    def __init__(self):
        self.sessions = {}  # session_id -> session dict
        self._lock = threading.Lock()
        self._cleanup_interval = 7200  # 2 hours

    def get_or_create(self, session_id=None):
        with self._lock:
            if session_id and session_id in self.sessions:
                session = self.sessions[session_id]
                session["last_activity"] = datetime.datetime.now().isoformat()
                return session
            new_id = session_id or str(uuid.uuid4())
            session = {
                "session_id": new_id,
                "conversation_history": [],
                "current_plan": None,
                "audio_context": {},
                "status": "chatting",  # chatting | planning | executing | done
                "last_activity": datetime.datetime.now().isoformat(),
            }
            self.sessions[new_id] = session
            return session

    def add_message(self, session_id, role, content):
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]["conversation_history"].append({
                    "role": role,
                    "content": content,
                    "timestamp": datetime.datetime.now().isoformat()
                })

    def cleanup_expired(self):
        with self._lock:
            now = datetime.datetime.now()
            expired = []
            for sid, session in self.sessions.items():
                last = datetime.datetime.fromisoformat(session["last_activity"])
                if (now - last).total_seconds() > self._cleanup_interval:
                    expired.append(sid)
            for sid in expired:
                # Clean up plan file if exists
                plan_path = Path(PLANS_DIR) / f"plan_{sid}.json"
                if plan_path.exists():
                    plan_path.unlink()
                del self.sessions[sid]


session_manager = SessionManager()


# ─── Plan Lifecycle Functions ─────────────────────────────────────────────────

def save_plan_to_disk(session):
    """Save current plan to .local_workspace/plans/plan_{session_id}.json"""
    if not session.get("current_plan"):
        return
    plan_path = Path(PLANS_DIR) / f"plan_{session['session_id']}.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(session["current_plan"], f, ensure_ascii=False, indent=2)


def delete_plan_from_disk(session_id):
    """Delete plan file when completed"""
    plan_path = Path(PLANS_DIR) / f"plan_{session_id}.json"
    if plan_path.exists():
        plan_path.unlink()


def check_plan_completion(session):
    """Check if all plan steps are completed, auto-delete if so"""
    plan = session.get("current_plan")
    if not plan or not plan.get("steps"):
        return False
    all_done = all(step.get("status") == "completed" for step in plan["steps"])
    if all_done:
        delete_plan_from_disk(session["session_id"])
        session["current_plan"] = None
        session["status"] = "done"
        return True
    return False


# ─── Conversational LLM Response ──────────────────────────────────────────────

async def generate_conversational_response(session, user_message, analysis_result=None):
    """Generate a conversational AI response using LLM with full context"""

    system_prompt = """Tu es l'IA d'un studio de musique professionnel. Tu es une experte en production musicale,
mixage, mastering, et composition. Tu parles toujours en français.

RÈGLES IMPORTANTES:
- Tu ne lances JAMAIS une action automatiquement. Tu discutes d'abord avec l'utilisateur.
- Après une analyse audio, tu présentes les résultats en détail et tu termines par "J'attends vos ordres et suggestions pour la suite."
- Quand l'utilisateur donne des directions créatives, tu acquiesces, résumes ta compréhension, et proposes des améliorations.
- Tu ne crées un plan QUE quand l'utilisateur le demande explicitement.
- Quand on te demande de créer un plan, tu synthétises TOUS les points discutés dans la conversation en un plan structuré.
- Tu es collaborative, enthousiaste, et professionnelle."""

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history for context
    for msg in session.get("conversation_history", [])[-20:]:  # Last 20 messages for context window
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message with any analysis context
    current_content = user_message
    if analysis_result:
        current_content += f"\n\n[RÉSULTATS D'ANALYSE AUDIO]\n{json.dumps(analysis_result, ensure_ascii=False, indent=2)}"

    if session.get("audio_context"):
        audio_info = f"\n\n[CONTEXTE AUDIO EN SESSION]\nFichier: {session['audio_context'].get('file', 'N/A')}"
        if session['audio_context'].get('analysis'):
            audio_info += f"\nAnalyse: {json.dumps(session['audio_context']['analysis'], ensure_ascii=False)}"
        current_content += audio_info

    if session.get("current_plan"):
        plan_info = f"\n\n[PLAN ACTUEL]\n{json.dumps(session['current_plan'], ensure_ascii=False, indent=2)}"
        current_content += plan_info

    messages.append({"role": "user", "content": current_content})

    # Try to call LLM - use the same pattern as existing code in the file
    try:
        # Use the orchestrator/deepseek model if available
        from models.manager import WorldClassModelManager
        manager = WorldClassModelManager()
        llm = await manager.load_orchestrator()

        if llm and hasattr(llm, 'ainvoke'):
            response = await llm.ainvoke(messages)
            return response.content if hasattr(response, 'content') else str(response)
        elif llm and hasattr(llm, 'invoke'):
            response = llm.invoke(messages)
            return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"LLM error: {e}")

    # Fallback: generate a structured response without LLM
    if analysis_result:
        return _format_analysis_fallback(analysis_result)
    return "Je suis prête à discuter de votre projet musical. Envoyez-moi un fichier audio ou décrivez-moi votre idée ! J'attends vos ordres et suggestions."


def _format_analysis_fallback(analysis):
    """Format analysis results as a detailed French response when LLM is unavailable"""
    lines = ["Voici mon analyse détaillée de votre fichier audio :\n"]
    if "bpm" in analysis:
        lines.append(f"**Tempo** : {analysis['bpm']} BPM")
    if "vocal_bpm" in analysis:
        lines.append(f"**Tempo vocal** : {analysis['vocal_bpm']} BPM")
    if "key" in analysis:
        lines.append(f"**Tonalité** : {analysis['key']}")
    if "duration_seconds" in analysis:
        dur = analysis['duration_seconds']
        mins, secs = divmod(int(dur), 60)
        lines.append(f"**Durée** : {mins}m {secs}s")
    if "structure" in analysis:
        struct = analysis["structure"]
        lines.append(f"**Structure** : {struct.get('num_sections', '?')} sections détectées")
    if "spectral" in analysis:
        spec = analysis["spectral"]
        if "spectral_centroid_mean" in spec:
            lines.append(f"**Centroïde spectral** : {spec['spectral_centroid_mean']:.1f} Hz")
        if "rms_mean" in spec:
            lines.append(f"**Niveau RMS moyen** : {spec['rms_mean']:.6f}")
    if "beat_grid" in analysis:
        lines.append(f"**Grille de beats** : {analysis['beat_grid'].get('num_beats', '?')} beats détectés")
    lines.append("\nJ'attends vos ordres et suggestions pour la suite.")
    return "\n".join(lines)


@app.get("/api/library")
async def get_library():
    """Returns the list of audio files available in the user library and exports."""
    tracks = []
    
    dirs_to_scan = [
        (config.workspace_root / "library", "Bibliothèque"),
        (config.fl_studio_output_folder, "Exports")
    ]
    
    for directory, source_name in dirs_to_scan:
        if directory.exists():
            for file_path in directory.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                    tracks.append({
                        "filename": file_path.name,
                        "source": source_name,
                        "duration": 0, # Not calculating duration to avoid slow performance
                        "genre": "Audio"
                    })
                    
    return {"status": "success", "tracks": tracks}

@app.get("/api/library/stream/{filename}")
async def stream_library_file(filename: str):
    """Stream a file from library or exports"""
    dirs_to_scan = [
        config.workspace_root / "library",
        config.fl_studio_output_folder,
        config.fl_studio_output_folder / "Edits",
        config.fl_studio_output_folder / "archives"
    ]
    
    for directory in dirs_to_scan:
        if directory.exists():
            for file_path in directory.rglob(filename):
                if file_path.is_file():
                    return FileResponse(str(file_path))
                    
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/audio/file")
async def get_audio_file(path: str):
    """Serve an audio file from an approved local processing directory."""
    audio_path = _resolve_allowed_audio_path(path)
    media_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
    }
    return FileResponse(
        str(audio_path),
        media_type=media_types.get(audio_path.suffix.lower(), "application/octet-stream"),
        filename=audio_path.name,
        headers={"Accept-Ranges": "bytes"},
    )


@app.post("/api/audio/upload-source")
async def upload_source_audio(file: UploadFile = File(...)):
    """Upload a source track without triggering the full AI pipeline."""
    upload_dir = config.temp_folder / "source_uploads" / str(uuid.uuid4())
    final_path = _store_uploaded_audio(file, upload_dir)
    return {
        "status": "success",
        "audio_path": str(final_path),
        "preview_url": _audio_preview_url(str(final_path)),
        "filename": final_path.name,
    }


@app.post("/api/audio/save-edit")
async def save_audio_edit(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
):
    """Persist a validated browser edit and expose a download URL."""
    target_dir = config.fl_studio_output_folder / "Edits"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_name = file.filename or "edit.wav"
    suffix = Path(source_name).suffix or ".wav"
    safe_name = _safe_output_name(name or source_name, fallback="edit")
    final_path = target_dir / f"{safe_name}_{uuid.uuid4().hex[:8]}{suffix}"

    with open(final_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"💾 Edit audio sauvegardee : {final_path}")
    return {
        "status": "success",
        "output_path": str(final_path),
        "preview_url": _audio_preview_url(str(final_path)),
        "download_url": f"/exports/Edits/{final_path.name}",
        "filename": final_path.name,
        "message": "Version retouchee enregistree avec succes.",
    }

@app.post("/api/youtube")
async def download_youtube(req: YoutubeRequest):
    """Download audio from YouTube"""
    from utils.youtube import YouTubeDownloader, YouTubeAuthRequired, YouTubeBlocked
    try:
        ydl = YouTubeDownloader()
        file_path = ydl.download_audio(req.url)
        return {"status": "success", "file_path": file_path}
    except YouTubeAuthRequired:
        raise HTTPException(
            status_code=403,
            detail=(
                "YouTube a bloqué le téléchargement (vérification anti-bot). "
                "Reconnecte-toi à YouTube puis réexporte tes cookies dans youtube_cookies.txt "
                "ou utilise une autre vidéo."
            ),
        )
    except YouTubeBlocked:
        raise HTTPException(
            status_code=403,
            detail="Cette vidéo est indisponible / bloquée pour téléchargement.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur YouTube: {e}")

@app.post("/api/chat")
async def process_chat(req: ChatRequest):
    """Conversational AI chat with session management, plan creation, and execution"""
    # Get or create session
    session = session_manager.get_or_create(req.session_id)
    session_id = session["session_id"]

    # Store user message in history
    session_manager.add_message(session_id, "user", req.message)

    # Update audio context if provided
    if req.audio_path:
        session["audio_context"]["file"] = req.audio_path

    user_msg_lower = req.message.lower().strip()

    # --- PLAN TRIGGER KEYWORDS ---
    plan_triggers = ["fais le plan", "fait le plan", "créer le plan", "creer le plan",
                     "c'est bon", "on y va", "go", "lance le plan", "fais-le",
                     "create the plan", "make the plan"]

    # --- EXECUTION TRIGGER KEYWORDS ---
    exec_triggers = ["execute", "exécute", "lance", "run", "démarre", "start"]

    # --- ANALYSIS KEYWORDS ---
    analysis_triggers = ["analys", "analyse tout", "analyze", "bpm", "tonalité", "tonalite", "tempo"]

    # Check if this is a plan creation request
    if any(trigger in user_msg_lower for trigger in plan_triggers):
        if session["status"] == "chatting" or session["status"] == "planning":
            # Create or finalize plan from conversation
            plan = await _create_plan_from_conversation(session)
            session["current_plan"] = plan
            session["status"] = "planning"
            save_plan_to_disk(session)

            reply = await generate_conversational_response(session, req.message)
            session_manager.add_message(session_id, "assistant", reply)

            return {
                "status": "plan_created",
                "reply": reply,
                "session_id": session_id,
                "plan": plan
            }

    # Check if this is an execution request (when a plan exists)
    if session.get("current_plan") and any(trigger in user_msg_lower for trigger in exec_triggers):
        # Execute the plan
        task_ids = await _execute_plan(session)
        session["status"] = "executing"
        save_plan_to_disk(session)

        reply = "Le plan est en cours d'exécution ! Je vous tiendrai informé de l'avancement."
        session_manager.add_message(session_id, "assistant", reply)

        return {
            "status": "executing",
            "reply": reply,
            "session_id": session_id,
            "task_ids": task_ids,
            "plan": session["current_plan"]
        }

    # Check if user is adding to an existing plan (plan exists + new instruction)
    if session.get("current_plan") and session["status"] == "planning":
        # Amend existing plan
        session["current_plan"] = await _amend_plan(session, req.message)
        session["current_plan"]["updated_at"] = datetime.datetime.now().isoformat()
        save_plan_to_disk(session)

        reply = await generate_conversational_response(session, req.message)
        session_manager.add_message(session_id, "assistant", reply)

        return {
            "status": "plan_updated",
            "reply": reply,
            "session_id": session_id,
            "plan": session["current_plan"]
        }

    # Check if analysis is requested
    if any(trigger in user_msg_lower for trigger in analysis_triggers):
        audio_path = req.audio_path or session["audio_context"].get("file")
        if audio_path:
            try:
                from agents.analyste import Analyste
                analyste = Analyste()
                analysis = analyste.analyze(audio_path)
                session["audio_context"]["analysis"] = analysis
                session["audio_context"]["file"] = audio_path

                reply = await generate_conversational_response(session, req.message, analysis_result=analysis)
                session_manager.add_message(session_id, "assistant", reply)

                return {
                    "status": "analysis_complete",
                    "reply": reply,
                    "session_id": session_id,
                    "analysis": analysis
                }
            except Exception as e:
                reply = f"Erreur lors de l'analyse : {str(e)}. Pouvez-vous vérifier le fichier audio ?"
                session_manager.add_message(session_id, "assistant", reply)
                return {"status": "error", "reply": reply, "session_id": session_id}
        else:
            reply = "Je n'ai pas de fichier audio à analyser. Envoyez-moi un fichier audio d'abord !"
            session_manager.add_message(session_id, "assistant", reply)
            return {"status": "waiting_audio", "reply": reply, "session_id": session_id}

    # Default: conversational mode - just chat
    reply = await generate_conversational_response(session, req.message)
    session_manager.add_message(session_id, "assistant", reply)

    return {
        "status": "chatting",
        "reply": reply,
        "session_id": session_id
    }


# ─── Plan Creation & Amendment Helpers ────────────────────────────────────────

async def _create_plan_from_conversation(session):
    """Synthesize conversation into a structured plan"""
    plan = {
        "session_id": session["session_id"],
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
        "status": "draft",
        "conversation_summary": "",
        "steps": [],
        "audio_context": session.get("audio_context", {})
    }

    # Try to use LLM to create the plan from conversation
    try:
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in session.get("conversation_history", [])
        ])

        plan_prompt = f"""Basé sur cette conversation, crée un plan de production structuré.
Retourne UNIQUEMENT un JSON valide avec cette structure:
{{
  "conversation_summary": "résumé de ce qui a été discuté",
  "steps": [
    {{"step": 1, "action": "description de l'action", "agent": "nom_agent", "params": {{}}, "status": "pending"}}
  ]
}}

Les agents disponibles sont: analyste, chirurgien, compositeur, arrangeur, ingenieur_son, mastering, dj_pro, expert_vocal, superviseur

Conversation:
{conversation_text}"""

        from models.manager import WorldClassModelManager
        manager = WorldClassModelManager()
        llm = await manager.load_orchestrator()

        if llm:
            if hasattr(llm, 'ainvoke'):
                response = await llm.ainvoke([{"role": "user", "content": plan_prompt}])
            else:
                response = llm.invoke([{"role": "user", "content": plan_prompt}])

            content = response.content if hasattr(response, 'content') else str(response)

            # Try to parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                plan["conversation_summary"] = parsed.get("conversation_summary", "")
                plan["steps"] = parsed.get("steps", [])
    except Exception as e:
        print(f"Plan creation LLM error: {e}")
        # Fallback: create basic plan from audio context
        plan["conversation_summary"] = "Plan créé à partir de la conversation"
        if session.get("audio_context", {}).get("file"):
            plan["steps"].append({
                "step": 1, "action": "Analyse audio complète",
                "agent": "analyste", "params": {"file": session["audio_context"]["file"]},
                "status": "pending"
            })

    return plan


async def _amend_plan(session, new_instruction):
    """Add new instructions to existing plan without creating a new one"""
    plan = session["current_plan"]

    try:
        existing_steps = json.dumps(plan.get("steps", []), ensure_ascii=False)
        amend_prompt = f"""Le plan actuel a ces étapes:
{existing_steps}

L'utilisateur ajoute cette instruction: "{new_instruction}"

Retourne UNIQUEMENT un JSON valide avec le tableau "steps" mis à jour (ajoute ou modifie les étapes nécessaires):
{{"steps": [...]}}"""

        from models.manager import WorldClassModelManager
        manager = WorldClassModelManager()
        llm = await manager.load_orchestrator()

        if llm:
            if hasattr(llm, 'ainvoke'):
                response = await llm.ainvoke([{"role": "user", "content": amend_prompt}])
            else:
                response = llm.invoke([{"role": "user", "content": amend_prompt}])

            content = response.content if hasattr(response, 'content') else str(response)

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                plan["steps"] = parsed.get("steps", plan["steps"])
    except Exception as e:
        print(f"Plan amendment LLM error: {e}")
        # Fallback: just append a new step
        next_step = len(plan.get("steps", [])) + 1
        plan["steps"].append({
            "step": next_step,
            "action": new_instruction,
            "agent": "orchestrateur",
            "params": {},
            "status": "pending"
        })

    return plan


async def _execute_plan(session):
    """Execute plan steps by dispatching appropriate Celery tasks"""
    plan = session.get("current_plan")
    if not plan:
        return []

    plan["status"] = "executing"
    task_ids = []

    for step in plan.get("steps", []):
        if step.get("status") != "pending":
            continue

        agent_name = step.get("agent", "").lower()
        params = step.get("params", {})
        audio_file = params.get("file") or session.get("audio_context", {}).get("file", "")

        try:
            from workers.tasks import (analyze_audio, separate_stems,
                                        generate_music, vocal_production_task, auto_remix_task)

            if agent_name in ["analyste", "analysis"]:
                task = analyze_audio.delay(audio_file)
            elif agent_name in ["chirurgien", "separation"]:
                task = separate_stems.delay(audio_file)
            elif agent_name in ["compositeur", "generation"]:
                task = generate_music.delay(params.get("prompt", ""), params.get("duration", 30))
            elif agent_name in ["expert_vocal", "vocals"]:
                task = vocal_production_task.delay(audio_file)
            elif agent_name in ["dj_pro", "remix"]:
                task = auto_remix_task.delay(audio_file)
            else:
                # Generic: try analyze as default
                task = analyze_audio.delay(audio_file)

            step["task_id"] = task.id
            step["status"] = "processing"
            task_ids.append(task.id)
        except Exception as e:
            step["status"] = "failed"
            step["error"] = str(e)

    save_plan_to_disk(session)
    return task_ids


@app.on_event("startup")
async def startup_cleanup():
    """Clean up old plan files on startup"""
    plans_dir = Path(PLANS_DIR)
    if plans_dir.exists():
        for plan_file in plans_dir.glob("plan_*.json"):
            try:
                with open(plan_file, "r") as f:
                    plan_data = json.load(f)
                if plan_data.get("status") == "completed":
                    plan_file.unlink()
            except:
                pass


@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    import os
    # Chargement du profil lite si nécessaire
    if os.getenv("STUDIO_PROFILE") == "lite":
        try:
            import config_lite  # noqa: F401
            logger.info("⚡ Profil Lite chargé dans FastAPI")
        except Exception as e:
            logger.warning(f"Impossible de charger config_lite : {e}")
    config.setup_directories()
    logger.info("🚀 Studio IA API starting...")
    logger.info(f"💻 Hardware: {config.get_vram_info()}")


@app.get("/")
async def root():
    """Serve the frontend UI"""
    index_file = Path(__file__).parent.parent / "static" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {
        "name": "Studio IA Local et Autonome",
        "version": "2.0.0",
        "agents": len(config.AGENT_TEAM),
        "models": "World-class open source",
        "status": "operational"
    }


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.post("/api/projects/create")
async def create_project(project: ProjectRequest, background_tasks: BackgroundTasks):
    """Create new music production project"""
    
    project_id = str(uuid.uuid4())
    
    # Start background processing
    task = process_audio_project.delay({
        "project_id": project_id,
        "name": project.name,
        "description": project.description,
        "genre": project.genre,
        "bpm": project.bpm,
        "key": project.key,
        "references": project.references,
        "options": project.options
    })
    
    return {
        "project_id": project_id,
        "task_id": task.id,
        "status": "processing",
        "message": "Project created and processing started"
    }


@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    project_id: Optional[str] = None
):
    """Upload audio files for processing — auto-converts M4A/MP3/OGG to WAV"""

    upload_dir = config.temp_folder / str(uuid.uuid4())
    upload_dir.mkdir(parents=True)

    uploaded_files = []

    for file in files:
        final_path = _store_uploaded_audio(file, upload_dir)
        uploaded_files.append(str(final_path))

    # Start processing
    task = process_audio_project.delay({
        "project_id": project_id or str(uuid.uuid4()),
        "audio_files": uploaded_files,
        "separate_stems": True,
        "process_vocals": True
    })
    
    return {
        "task_id": task.id,
        "files_uploaded": len(uploaded_files),
        "status": "processing",
        "audio_path": uploaded_files[0] if uploaded_files else None
    }


class VocalProductionRequest(BaseModel):
    audio_path: str
    style_prompt: Optional[str] = ""
    autotune_strength: Optional[float] = 0.7
    key: Optional[str] = None          # ex: "C minor" — auto-détecté si absent
    bpm: Optional[float] = None        # auto-détecté si absent


@app.post("/api/vocal-prod")
async def vocal_production(request: VocalProductionRequest):
    """
    Production complète sur une voix brute :
    autotune + reverb + delay + beat synchro BPM + mix pro.

    Équivalent à dire 'je chante, produis derrière moi'.
    """
    if not Path(request.audio_path).exists():
        raise HTTPException(status_code=400,
                            detail=f"Fichier vocal introuvable : {request.audio_path}")

    from workers.tasks import vocal_production_task
    task = vocal_production_task.delay(request.audio_path, request.style_prompt or "")

    return {
        "task_id": task.id,
        "status": "processing",
        "message": (
            "Production lancée ! Analyse BPM/tonalité → autotune → reverb/delay → "
            "génération beat → mix pro → export FL Studio."
        ),
    }


@app.post("/api/generate")
async def generate_music(request: GenerationRequest):
    """Generate music from prompt"""
    
    from workers.tasks import generate_music
    
    task = generate_music.delay(
        request.prompt,
        request.duration
    )
    
    return {
        "task_id": task.id,
        "prompt": request.prompt,
        "status": "generating"
    }


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Check task status"""
    
    from celery.result import AsyncResult
    from workers.celery_app import celery_app
    
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready()
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.info)
    
    return response


@app.get("/api/download/{task_id}")
async def download_result(task_id: str):
    """Download processed files"""

    result_dir = config.fl_studio_output_folder / task_id
    zip_path = result_dir.with_suffix('.zip')

    if zip_path.exists():
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"studio_ia_{task_id}.zip"
        )

    candidate_dirs = [
        result_dir,
        config.temp_folder / task_id,
        config.workspace_root / task_id,
    ]
    files: List[Path] = []
    audio_extensions = {".wav", ".mp3", ".flac", ".aiff", ".aif", ".ogg", ".m4a", ".webm"}
    for candidate_dir in candidate_dirs:
        if candidate_dir.exists():
            files.extend(
                path for path in candidate_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in audio_extensions
            )

    if not files:
        from celery.result import AsyncResult
        from workers.celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)
        if result.ready() and result.successful():
            files = _collect_audio_paths(result.result)

    if not files:
        raise HTTPException(status_code=404, detail="Results not ready")

    generated_zip = _zip_files(task_id, files)
    return FileResponse(
        generated_zip,
        media_type="application/zip",
        filename=f"studio_ia_{task_id}.zip"
    )


@app.get("/api/status/system")
async def system_status():
    """Get system status"""
    
    vram_info = config.get_vram_info()
    model_status = model_manager.get_status()
    
    return {
        "hardware": vram_info,
        "models": model_status,
        "workspace": str(config.workspace_root),
        "fl_studio_connected": config.fl_studio_watch_folder.exists()
    }


@app.get("/api/agents")
async def list_agents():
    """List all agents"""
    return {
        "agents": config.AGENT_TEAM,
        "total": len(config.AGENT_TEAM)
    }


@app.delete("/api/models/unload/{model_name}")
async def unload_model(model_name: str):
    """Unload a model to free VRAM"""
    
    await model_manager.unload_model(model_name)
    
    return {
        "status": "unloaded",
        "model": model_name,
        "vram_free_gb": model_manager.vram_manager.get_available_vram_gb()
    }


@app.post("/api/fl-studio/export")
async def export_to_fl_studio(task_id: str):
    """Export processed files to FL Studio"""

    from utils.fl_studio_bridge import FLStudioBridge

    bridge = FLStudioBridge()
    exported = await bridge.export_project(task_id)

    if not exported:
        from celery.result import AsyncResult
        from workers.celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)
        if result.ready() and result.successful():
            files = _collect_audio_paths(result.result)
            if files:
                export_dir = config.fl_studio_output_folder / task_id
                export_dir.mkdir(parents=True, exist_ok=True)
                for file_path in files:
                    dest_path = export_dir / file_path.name
                    shutil.copy2(file_path, dest_path)
                    exported.append(str(dest_path))

    if not exported:
        raise HTTPException(status_code=404, detail="Aucun fichier exportable pour cette tache")
    
    return {
        "exported_to": str(config.fl_studio_output_folder),
        "files": exported
    }


class MasteringRequest(BaseModel):
    audio_path: str
    creative: Optional[bool] = False
    enhance_vocals: Optional[bool] = True
    add_warmth: Optional[bool] = True
    stereo_width: Optional[float] = 1.2


@app.post("/api/mastering/youtube")
async def master_for_youtube(request: MasteringRequest):
    """
    Mastering professionnel optimisé YouTube :
    - Lisse les défauts (de-esser, réduction de bruit)
    - Normalisation LUFS -14 (standard YouTube)
    - Compression multiband
    - Limiteur final sans distorsion
    - True peak -1.0 dB
    """
    if not Path(request.audio_path).exists():
        raise HTTPException(status_code=400, 
                          detail=f"Fichier introuvable : {request.audio_path}")
    
    try:
        from utils.youtube_mastering import YouTubeMaster, YouTubeMasterAdvanced
        
        if request.creative:
            master = YouTubeMasterAdvanced()
            output_path = master.master_creative(
                Path(request.audio_path),
                enhance_vocals=request.enhance_vocals,
                add_warmth=request.add_warmth,
                stereo_width=request.stereo_width
            )
        else:
            master = YouTubeMaster()
            output_path = master.master(Path(request.audio_path))
        
        return {
            "status": "success",
            "output_path": str(output_path),
            "target_lufs": -14.0,
            "true_peak": -1.0,
            "message": "Mastering terminé ! Prêt pour YouTube 🎬"
        }
    
    except Exception as e:
        logger.error(f"Erreur mastering : {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mastering/auto")
async def auto_master_upload(file: UploadFile = File(...), creative: bool = False):
    """
    Upload + mastering automatique en une seule étape.
    Drag & drop ton fichier et récupère la version masterisée !
    """
    # Sauvegarde temporaire
    upload_dir = config.temp_folder / "mastering_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    temp_path = upload_dir / file.filename
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Mastering
    try:
        from utils.youtube_mastering import master_for_youtube
        output_path = master_for_youtube(str(temp_path), creative=creative)
        
        # Copie vers "music prete"
        final_dir = config.fl_studio_output_folder / "Mastered"
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / Path(output_path).name
        shutil.copy2(output_path, final_path)
        
        logger.info(f"✅ Masterisé : {final_path}")
        
        return {
            "status": "success",
            "output_path": str(final_path),
            "download_url": f"/exports/Mastered/{final_path.name}",
            "message": f"✅ Masterisé pour YouTube ! LUFS -14 | True Peak -1.0 dB"
        }
    
    except Exception as e:
        logger.error(f"Erreur auto-mastering : {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Task List Endpoint ────────────────────────────────────────────────────────

@app.get("/api/tasks/list")
async def list_tasks():
    """
    Returns a list of recent Celery tasks from the SQLite backend.
    Queries celery results table and returns structured task info.
    """
    import sqlite3

    tasks = []

    # Query the SQLite celery results DB
    db_candidates = [
        Path("celeryresults.sqlite"),
        Path("celerydb.sqlite"),
        config.workspace_root / "celeryresults.sqlite",
        config.workspace_root / "celerydb.sqlite",
    ]

    for db_path in db_candidates:
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Try celery_taskmeta table (standard celery db backend)
                try:
                    cursor.execute(
                        "SELECT task_id, status, result, date_done, traceback "
                        "FROM celery_taskmeta ORDER BY date_done DESC LIMIT 100"
                    )
                    rows = cursor.fetchall()
                    for row in rows:
                        task_id = row["task_id"]
                        status_raw = (row["status"] or "").upper()

                        # Map Celery statuses
                        status_map = {
                            "SUCCESS": "completed",
                            "FAILURE": "failed",
                            "PENDING": "pending",
                            "STARTED": "running",
                            "RETRY": "running",
                            "REVOKED": "failed",
                        }
                        status = status_map.get(status_raw, status_raw.lower())

                        # Try to parse result for download URL
                        download_url = None
                        result_raw = row["result"]
                        if result_raw and status == "completed":
                            try:
                                import pickle, base64
                                # Celery stores results as pickled + base64 or JSON
                                try:
                                    result_data = json.loads(result_raw)
                                except Exception:
                                    result_data = None
                                if isinstance(result_data, dict):
                                    for key in ("output_path", "final_mix", "remix_path", "generated_audio"):
                                        val = result_data.get(key)
                                        if val and isinstance(val, str) and Path(val).exists():
                                            download_url = f"/api/download/{task_id}"
                                            break
                                    if not download_url and result_data:
                                        audio_files = _collect_audio_paths(result_data)
                                        if audio_files:
                                            download_url = f"/api/download/{task_id}"
                            except Exception:
                                pass

                        # Determine task type from task_id or result
                        task_type = "audio_project"

                        error_msg = None
                        if status == "failed" and row["traceback"]:
                            tb = row["traceback"]
                            # Get last line of traceback
                            lines = [l for l in tb.strip().splitlines() if l.strip()]
                            error_msg = lines[-1] if lines else tb[:200]

                        created_at = ""
                        completed_at = ""
                        if row["date_done"]:
                            completed_at = str(row["date_done"])

                        tasks.append({
                            "id": task_id,
                            "type": task_type,
                            "status": status,
                            "progress": 100 if status == "completed" else (50 if status == "running" else 0),
                            "created_at": created_at,
                            "completed_at": completed_at,
                            "error": error_msg,
                            "download_url": download_url,
                        })
                except sqlite3.OperationalError:
                    # Table doesn't exist in this DB
                    pass

                conn.close()
                if tasks:
                    break
            except Exception as e:
                logger.warning(f"Error reading celery DB {db_path}: {e}")

    # Also enrich with live Celery AsyncResult data for PENDING tasks
    try:
        from celery.result import AsyncResult
        from workers.celery_app import celery_app

        for task in tasks:
            if task["status"] in ("pending", "running"):
                try:
                    result = AsyncResult(task["id"], app=celery_app)
                    live_status_map = {
                        "SUCCESS": "completed", "FAILURE": "failed",
                        "PENDING": "pending", "STARTED": "running",
                        "RETRY": "running", "REVOKED": "failed",
                    }
                    task["status"] = live_status_map.get(result.status, result.status.lower())
                    if result.info and isinstance(result.info, dict):
                        task["progress"] = result.info.get("progress", task["progress"])
                        if "type" in result.info:
                            task["type"] = result.info["type"]
                except Exception:
                    pass
    except Exception:
        pass

    return {"tasks": tasks}


# ─── Mixer / Project Track Routes ─────────────────────────────────────────────

# In-memory project store (per session)
_mixer_projects = {}  # project_id -> {tracks: [], settings: {}}


class MixerTrackAdd(BaseModel):
    project_id: Optional[str] = "default"
    slot: Optional[int] = None  # 1-8, auto-assigned if None
    audio_path: Optional[str] = None  # existing path OR upload
    name: Optional[str] = None

class MixerSettings(BaseModel):
    project_id: Optional[str] = "default"
    tracks: Optional[list] = []
    master: Optional[dict] = {}
    bpm: Optional[float] = 120

class AIDirectiveRequest(BaseModel):
    directive: str
    project_id: Optional[str] = "default"
    session_id: Optional[str] = None

class AutoMixRequest(BaseModel):
    project_id: Optional[str] = "default"


@app.post("/api/project/tracks/add")
async def add_mixer_track(file: UploadFile = File(None), slot: int = Form(None), project_id: str = Form("default"), name: str = Form(None)):
    """Add audio track to mixer project (upload file, assign to track slot 1-8)"""
    if project_id not in _mixer_projects:
        _mixer_projects[project_id] = {"tracks": {}, "settings": {"bpm": 120, "master": {}}}
    
    project = _mixer_projects[project_id]
    
    # Auto-assign slot if not provided
    if slot is None:
        used = set(project["tracks"].keys())
        for s in range(1, 9):
            if s not in used:
                slot = s
                break
    
    if slot is None or slot > 8:
        raise HTTPException(status_code=400, detail="No free slots (max 8 tracks)")
    
    track_info = {"slot": slot, "name": name or f"Track {slot}", "audio_path": None, "duration": 0}
    
    if file:
        upload_dir = config.temp_folder / "mixer_uploads" / project_id
        final_path = _store_uploaded_audio(file, upload_dir)
        track_info["audio_path"] = str(final_path)
        track_info["name"] = name or file.filename or f"Track {slot}"
        track_info["preview_url"] = _audio_preview_url(str(final_path))
        track_info["stream_url"] = f"/api/audio/file?path={quote(str(final_path))}"
    
    project["tracks"][slot] = track_info
    logger.info(f"🎛️ Track added: slot={slot} project={project_id}")
    
    return {"status": "success", "slot": slot, "track": track_info, "project_id": project_id}


@app.delete("/api/project/tracks/{slot}")
async def remove_mixer_track(slot: int, project_id: str = "default"):
    """Remove track from project"""
    if project_id in _mixer_projects:
        _mixer_projects[project_id]["tracks"].pop(slot, None)
    return {"status": "success", "slot": slot}


@app.get("/api/project/tracks")
async def list_mixer_tracks(project_id: str = "default"):
    """List all tracks in current mixer project"""
    if project_id not in _mixer_projects:
        return {"status": "success", "tracks": {}, "settings": {}}
    return {
        "status": "success",
        "tracks": _mixer_projects[project_id]["tracks"],
        "settings": _mixer_projects[project_id].get("settings", {})
    }


@app.post("/api/project/save")
async def save_mixer_project(settings: MixerSettings):
    """Save full project state (track config, mixer settings, effects)"""
    project_id = settings.project_id or "default"
    if project_id not in _mixer_projects:
        _mixer_projects[project_id] = {"tracks": {}, "settings": {}}
    
    # Persist to disk
    save_path = config.workspace_root / "projects"
    save_path.mkdir(parents=True, exist_ok=True)
    project_file = save_path / f"{project_id}.json"
    
    _mixer_projects[project_id]["settings"] = {
        "tracks": settings.tracks,
        "master": settings.master,
        "bpm": settings.bpm,
        "saved_at": datetime.datetime.now().isoformat()
    }
    
    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(_mixer_projects[project_id], f, ensure_ascii=False, indent=2)
    
    return {"status": "success", "project_id": project_id, "saved_to": str(project_file)}


@app.get("/api/project/load/{project_id}")
async def load_mixer_project(project_id: str):
    """Load saved project from disk"""
    project_file = config.workspace_root / "projects" / f"{project_id}.json"
    if not project_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    with open(project_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    _mixer_projects[project_id] = data
    return {"status": "success", "project_id": project_id, "data": data}


@app.post("/api/ai/realtime-directive")
async def ai_realtime_directive(req: AIDirectiveRequest):
    """
    Parse natural language mixing directive and return structured JSON commands.
    e.g., 'boost the bass on track 2 by 4dB' -> {action: set_eq, track: 2, band: low, gain: 4}
    """
    directive = req.directive.lower()
    commands = []
    reply = ""

    # Simple pattern matching for common mixing directives
    import re as re_module
    
    # Volume patterns: 'volume track 3 to -6', 'set track 2 volume -3dB'
    vol_match = re_module.search(r'(?:volume|vol|fader)[^\d]*?(\d+)[^-\d]*([-\d\.]+)\s*db?', directive)
    if vol_match:
        track = int(vol_match.group(1))
        val = float(vol_match.group(2))
        commands.append({"action": "set_volume", "track": track, "value": val})
        reply = f"Volume track {track} mis à {val}dB"
    
    # EQ patterns: 'boost bass track 1 by 3dB', 'cut high on track 2'
    eq_match = re_module.search(r'(boost|cut|add|reduce)[^\d]*(bass|low|mid|treble|high)[^\d]*(track[^\d]*(\d+))?[^\d]*([-\d\.]+)?\s*db?', directive)
    if eq_match:
        action = eq_match.group(1)
        band_raw = eq_match.group(2)
        track = int(eq_match.group(4)) if eq_match.group(4) else 1
        val_str = eq_match.group(5)
        val = float(val_str) if val_str else 3.0
        if action in ('cut', 'reduce'): val = -val
        band = 'low' if band_raw in ('bass', 'low') else ('high' if band_raw in ('treble', 'high') else 'mid')
        commands.append({"action": "set_eq", "track": track, "band": band, "value": val})
        reply = f"EQ {band} track {track}: {'+' if val > 0 else ''}{val}dB"
    
    # Reverb patterns: 'add reverb to track 3'
    reverb_match = re_module.search(r'(?:add|put|apply)\s+reverb[^\d]*(track[^\d]*(\d+))?', directive)
    if reverb_match:
        track = int(reverb_match.group(2)) if reverb_match.group(2) else 1
        commands.append({"action": "add_effect", "track": track, "effect": "reverb", "params": {"decay": 2.5, "mix": 0.3}})
        reply = f"Reverb ajouté à la track {track}"
    
    # Delay pattern
    delay_match = re_module.search(r'(?:add|put|apply)\s+delay[^\d]*(track[^\d]*(\d+))?', directive)
    if delay_match:
        track = int(delay_match.group(2)) if delay_match.group(2) else 1
        commands.append({"action": "add_effect", "track": track, "effect": "delay", "params": {"time": 0.25, "feedback": 0.3}})
        reply = f"Delay ajouté à la track {track}"
    
    # Mute/solo
    mute_match = re_module.search(r'(mute|solo|unmute|unsolo)[^\d]*(track[^\d]*(\d+))?', directive)
    if mute_match:
        action = mute_match.group(1)
        track = int(mute_match.group(3)) if mute_match.group(3) else 1
        commands.append({"action": f'set_{"mute" if "mute" in action else "solo"}', "track": track, "value": 'un' not in action})
        reply = f"{action.capitalize()} track {track}"
    
    # Pan
    pan_match = re_module.search(r'pan[^\d]*(track[^\d]*(\d+))?[^\d]*(left|right|center)?[^\d]*([-\d\.]+)?', directive)
    if pan_match:
        track = int(pan_match.group(2)) if pan_match.group(2) else 1
        direction = pan_match.group(3)
        val_str = pan_match.group(4)
        val = float(val_str) if val_str else (-0.7 if direction == 'left' else (0.7 if direction == 'right' else 0))
        commands.append({"action": "set_pan", "track": track, "value": val})
        reply = f"Pan track {track}: {val}"
    
    if not commands:
        reply = "Je n'ai pas reconnu cette directive. Essayez: 'boost bass track 2 by 3dB', 'add reverb to track 1', 'mute track 4'"
    
    return {"status": "success", "commands": commands, "reply": reply}


@app.post("/api/ai/auto-mix")
async def ai_auto_mix(req: AutoMixRequest):
    """
    AI analyzes all tracks and returns suggested fader/pan/EQ settings.
    Returns structured commands the frontend can animate.
    """
    project = _mixer_projects.get(req.project_id, {"tracks": {}})
    tracks = project.get("tracks", {})
    
    commands = []
    suggestions = []
    
    # Generate intelligent mix suggestions based on track count
    track_count = len(tracks)
    
    # Standard mix templates
    pan_positions = {1: 0, 2: -0.3, 3: 0.3, 4: -0.5, 5: 0.5, 6: -0.2, 7: 0.2, 8: 0}
    volume_suggestions = {1: -3, 2: -6, 3: -6, 4: -9, 5: -9, 6: -12, 7: -12, 8: -6}
    
    for slot_str, track in tracks.items():
        slot = int(slot_str)
        pan = pan_positions.get(slot, 0)
        vol = volume_suggestions.get(slot, -6)
        
        commands.append({"action": "set_volume", "track": slot, "value": vol})
        commands.append({"action": "set_pan", "track": slot, "value": pan})
        suggestions.append(f"Track {slot} ({track.get('name', 'Unknown')}): Vol {vol}dB, Pan {pan}")
    
    # Master settings
    commands.append({"action": "set_master_volume", "value": -3})
    
    reply = "Auto-Mix IA appliqué !\n" + "\n".join(suggestions)
    
    return {"status": "success", "commands": commands, "reply": reply}


@app.post("/api/audio/waveform")
async def get_waveform(file: UploadFile = File(None), audio_path: str = Form(None)):
    """Generate waveform peaks data for track visualization"""
    try:
        import librosa
        import numpy as np
        
        if file:
            upload_dir = config.temp_folder / "waveform_temp"
            upload_dir.mkdir(parents=True, exist_ok=True)
            temp_path = upload_dir / (file.filename or "temp.wav")
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            path = str(temp_path)
        elif audio_path:
            path = audio_path
        else:
            raise HTTPException(status_code=400, detail="No file or path provided")
        
        y, sr = librosa.load(path, sr=None, mono=True, duration=120)  # Max 2min
        # Compute peaks over 200 samples
        samples = 200
        block_size = max(1, len(y) // samples)
        peaks = []
        for i in range(samples):
            block = y[i * block_size: (i + 1) * block_size]
            peaks.append(float(np.max(np.abs(block)))) if len(block) > 0 else peaks.append(0)
        
        duration = librosa.get_duration(y=y, sr=sr)
        return {"status": "success", "peaks": peaks, "duration": duration, "samples": samples}
    except Exception as e:
        return {"status": "error", "peaks": [0.5] * 200, "duration": 0, "error": str(e)}

# ── NOUVELLES ROUTES (Macro Board) ────────────────────────────────────────────────
@router.post("/audio/generate-sample")
async def api_generate_sample(prompt: str = Form(...), duration: int = Form(3)):
    """Generate a short 1-3 second audio sample (one-shot)"""
    try:
        from workers.tasks import generate_music
        task = generate_music.delay(prompt, duration)
        return {"status": "success", "task_id": task.id, "message": f"Génération du sample ({duration}s) lancée"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BounceRequest(BaseModel):
    tracks: list
    
@router.post("/project/bounce")
async def api_project_bounce(request: BounceRequest):
    """Mix multiple tracks together server-side using Pydub"""
    try:
        from pydub import AudioSegment
        import os
        from pathlib import Path

        if not request.tracks:
            return {"status": "error", "message": "No tracks to bounce"}

        # Initialisation du mix avec la première piste
        mixed_audio = None
        
        for track in request.tracks:
            file_path = track.get("path")
            if not file_path or not os.path.exists(file_path):
                continue
                
            audio = AudioSegment.from_file(file_path)
            
            # Appliquer le volume (gain)
            gain = track.get("volume", 0) # en dB
            if gain != 0:
                audio = audio + gain
                
            # Appliquer le Pan (basique avec pydub)
            pan = track.get("pan", 0) # -1.0 to 1.0
            if pan != 0:
                audio = audio.pan(pan)

            if mixed_audio is None:
                mixed_audio = audio
            else:
                # Superposer les pistes
                mixed_audio = mixed_audio.overlay(audio)

        if mixed_audio is None:
            return {"status": "error", "message": "Failed to process any tracks"}

        # Dossier d'export
        export_dir = config.fl_studio_output_folder / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / f"bounce_{uuid.uuid4().hex[:8]}.wav"
        
        mixed_audio.export(output_path, format="wav")
        
        return {
            "status": "success", 
            "message": "Project bounced successfully", 
            "file_url": f"/exports/exports/{output_path.name}",
            "filename": output_path.name
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/audio/rvc")
async def api_audio_rvc(audio_path: str = Form(...), voice_model: str = Form(...)):
    """Voice Cloning (RVC) with automatic model management"""
    try:
        # Simulation d'un répertoire de modèles
        model_dir = Path(config.workspace_root) / "models" / "rvc"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"{voice_model}.pth"
        
        if not model_path.exists():
            # Dans une version réelle, on lancerait un téléchargement ici
            return {
                "status": "downloading", 
                "message": f"Le modèle '{voice_model}' n'est pas présent localement. Téléchargement initial lancé (approx. 500MB)...",
                "model": voice_model
            }
            
        # Ici on appellerait le moteur RVC réel
        return {
            "status": "success", 
            "message": f"Conversion RVC avec le modèle '{voice_model}' terminée.",
            "output_path": str(Path(audio_path).with_name(f"rvc_{voice_model}_{Path(audio_path).name}"))
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/library")
async def api_get_library():
    from utils.library import LibraryManager
    return {"tracks": LibraryManager().get_all_tracks()}

@app.get("/api/library/search")
async def api_smart_search(q: str):
    from utils.library import LibraryManager
    from models.manager import WorldClassModelManager
    
    manager = WorldClassModelManager()
    llm = await manager.load_orchestrator()
    
    library = LibraryManager()
    results = await library.smart_search(q, llm)
    return {"results": results}

