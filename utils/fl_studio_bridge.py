"""
FL Studio Bridge
Handles file watching and export integration with FL Studio
"""

import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

from config import config


class FLStudioBridge:
    """Bridge between Studio IA and FL Studio via watch folder"""

    def __init__(self):
        self.watch_folder = config.fl_studio_watch_folder
        self.output_folder = config.fl_studio_output_folder

    async def export_project(self, task_id: str) -> List[str]:
        """Export processed files to FL Studio output folder"""
        logger.info(f"📤 Exporting project {task_id} to FL Studio")

        source_dir = config.temp_folder / task_id
        dest_dir = self.output_folder / task_id

        exported_files = []

        if not source_dir.exists():
            # Try workspace folder
            source_dir = config.workspace_root / task_id

        if not source_dir.exists():
            logger.warning(f"No output directory found for task {task_id}")
            return exported_files

        dest_dir.mkdir(parents=True, exist_ok=True)

        audio_extensions = {".wav", ".mp3", ".flac", ".aiff", ".ogg"}
        for file_path in source_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                dest_path = dest_dir / file_path.name
                shutil.copy2(str(file_path), str(dest_path))
                exported_files.append(str(dest_path))
                logger.info(f"  → Exported: {file_path.name}")

        logger.info(f"✅ Exported {len(exported_files)} files to FL Studio: {dest_dir}")
        return exported_files

    async def open_in_fl_studio(self, path: Path) -> bool:
        """Launch FL Studio 2025 automatically and open the folder"""
        import subprocess
        import os
        fl_path = r"C:\Program Files\Image-Line\FL Studio 2025\FL64.exe"
        if not Path(fl_path).exists():
            logger.warning(f"FL Studio non trouvé : {fl_path}")
            return False
        
        try:
            logger.info(f"🎹 Lancement de FL Studio avec : {path}")
            # Lance FL Studio
            subprocess.Popen([fl_path])
            # Ouvre aussi le dossier dans l'explorateur pour un drag & drop facile
            os.startfile(str(path))
            return True
        except Exception as e:
            logger.error(f"Erreur lancement FL Studio: {e}")
            return False

    async def auto_export_stems(self, stems_dict: Dict[str, str], project_name: str = "Nouveau Projet") -> str:
        """Copie les stems finis dans 'music prete' et lance FL Studio"""
        import shutil
        import datetime
        timestamp = datetime.datetime.now().strftime("%Hh%M")
        safe_name = "".join(c for c in project_name if c.isalnum() or c in " -_").strip()
        dest_dir = self.output_folder / f"{safe_name}_{timestamp}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        for stem_name, stem_path in stems_dict.items():
            if Path(stem_path).exists():
                shutil.copy2(stem_path, dest_dir / f"{stem_name}.wav")
        
        logger.info(f"📤 Stems auto-exportés vers : {dest_dir}")
        
        # Lancement automatique de FL Studio
        success = await self.open_in_fl_studio(dest_dir)
        if not success:
            msg = f"Files were successfully saved to {dest_dir}, but FL Studio couldn't be opened automatically."
            logger.warning(msg)
            return msg

        return str(dest_dir)

    async def watch_for_new_files(self, callback) -> None:
        """Watch FL Studio ingestion folder for new files"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class AudioFileHandler(FileSystemEventHandler):
                def __init__(self, cb):
                    self.cb = cb

                def on_created(self, event):
                    if not event.is_directory:
                        path = Path(event.src_path)
                        if path.suffix.lower() in {".wav", ".mp3", ".flac", ".aiff"}:
                            logger.info(f"🎵 New file detected: {path.name}")
                            asyncio.create_task(self.cb(path))

            observer = Observer()
            observer.schedule(
                AudioFileHandler(callback),
                str(self.watch_folder),
                recursive=False
            )
            observer.start()
            logger.info(f"👁️ Watching for FL Studio files: {self.watch_folder}")

            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                observer.stop()
            observer.join()

        except ImportError:
            logger.warning("watchdog not installed, file watching disabled")

    async def import_from_fl_studio(self, file_path: Path) -> Dict[str, Any]:
        """Import a file from FL Studio's watch folder"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        dest_path = config.temp_folder / "fl_imports" / file_path.name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(str(file_path), str(dest_path))
        logger.info(f"📥 Imported from FL Studio: {file_path.name}")

        return {
            "original_path": str(file_path),
            "imported_path": str(dest_path),
            "file_name": file_path.name,
            "file_size_mb": round(file_path.stat().st_size / 1e6, 2),
        }

    async def create_project_folder(self, project_id: str) -> Path:
        """Create a project output folder for FL Studio"""
        project_dir = self.output_folder / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        for subfolder in ["stems", "mix", "master", "vocals"]:
            (project_dir / subfolder).mkdir(exist_ok=True)

        logger.info(f"📁 Created FL Studio project folder: {project_dir}")
        return project_dir

    def get_status(self) -> Dict[str, Any]:
        """Get current FL Studio integration status"""
        return {
            "watch_folder": str(self.watch_folder),
            "watch_folder_exists": self.watch_folder.exists(),
            "output_folder": str(self.output_folder),
            "output_folder_exists": self.output_folder.exists(),
            "pending_files": self._count_pending_files(),
        }

    def _count_pending_files(self) -> int:
        """Count files waiting in watch folder"""
        if not self.watch_folder.exists():
            return 0
        audio_exts = {".wav", ".mp3", ".flac", ".aiff", ".ogg"}
        return sum(
            1 for f in self.watch_folder.iterdir()
            if f.is_file() and f.suffix.lower() in audio_exts
        )
