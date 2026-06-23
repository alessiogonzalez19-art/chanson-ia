#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           Studio IA — Launcher Interactif                    ║
║   Choisissez votre profil et lancez le studio en 1 commande  ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import subprocess
import platform
import json
import time
import shutil
from pathlib import Path

# ── Vérifie que rich est dispo, sinon installe ────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    from rich.columns import Columns
    from rich import box
    from rich.rule import Rule
    from rich.align import Align
except ImportError:
    print("Installation de 'rich' pour l'interface...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"])
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    from rich.columns import Columns
    from rich import box
    from rich.rule import Rule
    from rich.align import Align

console = Console()

# ─────────────────────────────────────────────────────────────
#  PROFILS DE PROJETS
# ─────────────────────────────────────────────────────────────
PROJETS = {
    "1": {
        "nom":         "🏆 Projet 1 — Modèles Ultra-Puissants",
        "description": "GPT-4 class LLMs, Stable Audio 2.0, Whisper Large V3\nRequiert RTX 3090 / 4090 (24+ GB VRAM) et 64 GB RAM",
        "couleur":     "bold yellow",
        "badge":       "[bold red]⚠ PUISSANT[/bold red]",
        "requirements": {
            "vram_gb":  24,
            "ram_gb":   64,
            "disk_gb":  80,
            "compute":  7.0,
        },
        "env_vars": {
            "ORCHESTRATOR_MODEL": "deepseek_v3",
            "MUSIC_MODEL":        "stable_audio_2",
            "SPEECH_MODEL":       "whisper_large_v3",
            "SEPARATION_MODEL":   "demucs_ht",
            "USE_4BIT":           "true",
            "MAX_VRAM_GB":        "24.0",
        },
        "models": {
            "LLM":       "deepseek-ai/DeepSeek-V3 (671B, ~40 GB)",
            "Musique":   "stabilityai/stable-audio-open-1.0 (~8 GB)",
            "Speech":    "openai/whisper-large-v3 (~6 GB)",
            "Séparation":"facebook/demucs htdemucs (~4 GB)",
        },
        "download_script": "scripts/download_models.py",
        "download_args":   ["--all"],
    },
    "2": {
        "nom":         "⚡ Projet 2 — Modèles PC Standard",
        "description": "Mistral 7B, MusicGen Small, Whisper Small, Demucs MDX\nCompatible GTX 960 / 1060 / 1070 (2–8 GB VRAM) et 16 GB RAM",
        "couleur":     "bold cyan",
        "badge":       "[bold green]✅ RECOMMANDÉ pour votre PC[/bold green]",
        "requirements": {
            "vram_gb":  2,
            "ram_gb":   8,
            "disk_gb":  12,
            "compute":  5.0,
        },
        "env_vars": {
            "ORCHESTRATOR_MODEL": "mistral_7b",
            "MUSIC_MODEL":        "musicgen_small",
            "SPEECH_MODEL":       "whisper_small",
            "SEPARATION_MODEL":   "demucs_mdx",
            "USE_4BIT":           "true",
            "MAX_VRAM_GB":        "2.0",
        },
        "models": {
            "LLM":       "mistralai/Mistral-7B-Instruct-v0.3 (~4 GB, 4-bit)",
            "Musique":   "facebook/musicgen-small (~0.3 GB)",
            "Speech":    "openai/whisper-small (~0.5 GB)",
            "Séparation":"demucs mdx_extra (~0.8 GB)",
        },
        "download_script": "scripts/download_projet2.py",
        "download_args":   ["--all"],
    },
}

# ─────────────────────────────────────────────────────────────
#  DÉTECTION HARDWARE
# ─────────────────────────────────────────────────────────────
def detect_hardware() -> dict:
    hw = {
        "gpu_name":    "Inconnu",
        "vram_gb":     0.0,
        "vram_free_gb":0.0,
        "compute":     0.0,
        "ram_gb":      0.0,
        "disk_c_free": 0.0,
        "disk_d_free": 0.0,
        "cuda_ok":     False,
        "driver":      "N/A",
    }

    # RAM
    try:
        import psutil
        hw["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    except ImportError:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=5
            )
            hw["ram_gb"] = round(int(result.stdout.strip()) / 1e9, 1)
        except Exception:
            hw["ram_gb"] = 16.0  # fallback

    # Disque
    try:
        c_free = shutil.disk_usage("C:\\").free / 1e9
        hw["disk_c_free"] = round(c_free, 1)
    except Exception:
        pass
    try:
        d_free = shutil.disk_usage("D:\\").free / 1e9
        hw["disk_d_free"] = round(d_free, 1)
    except Exception:
        pass

    # GPU via nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                hw["gpu_name"]     = parts[0]
                hw["vram_gb"]      = round(float(parts[1].replace(" MiB", "")) / 1024, 1)
                hw["vram_free_gb"] = round(float(parts[2].replace(" MiB", "")) / 1024, 1)
                hw["driver"]       = parts[3]
                hw["compute"]      = float(parts[4])
                hw["cuda_ok"]      = True
    except Exception:
        pass

    return hw


# ─────────────────────────────────────────────────────────────
#  AFFICHAGE
# ─────────────────────────────────────────────────────────────
def print_banner():
    console.clear()
    banner = Text(justify="center")
    banner.append("\n")
    banner.append("  ███████╗████████╗██╗   ██╗██████╗ ██╗ ██████╗     ██╗ █████╗ \n", style="bold magenta")
    banner.append("  ██╔════╝╚══██╔══╝██║   ██║██╔══██╗██║██╔═══██╗    ██║██╔══██╗\n", style="bold magenta")
    banner.append("  ███████╗   ██║   ██║   ██║██║  ██║██║██║   ██║    ██║███████║\n", style="bold blue")
    banner.append("  ╚════██║   ██║   ██║   ██║██║  ██║██║██║   ██║    ██║██╔══██║\n", style="bold blue")
    banner.append("  ███████║   ██║   ╚██████╔╝██████╔╝██║╚██████╔╝    ██║██║  ██║\n", style="bold cyan")
    banner.append("  ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝    ╚═╝╚═╝  ╚═╝\n", style="bold cyan")
    banner.append("\n")
    banner.append("           🎹 Local AI Music Production Studio v2.0\n", style="bold white")
    banner.append("      World-Class AI · 10 Agents Spécialisés · 100% Local\n", style="dim white")
    console.print(banner)
    console.print(Rule(style="dim magenta"))


def print_hardware(hw: dict):
    table = Table(
        title="🖥️  Votre Configuration",
        box=box.ROUNDED,
        border_style="dim blue",
        show_header=True,
        header_style="bold white",
        title_style="bold white",
    )
    table.add_column("Composant", style="cyan", width=20)
    table.add_column("Valeur", style="white", width=35)
    table.add_column("Status", width=15, justify="center")

    def badge(ok): return "✅" if ok else "❌"

    table.add_row(
        "GPU",
        hw["gpu_name"],
        badge(hw["cuda_ok"])
    )
    table.add_row(
        "VRAM",
        f"{hw['vram_gb']} GB total  /  {hw['vram_free_gb']} GB libre",
        badge(hw["vram_gb"] >= 4)
    )
    table.add_row(
        "CUDA Compute",
        str(hw["compute"]),
        badge(hw["compute"] >= 5.0)
    )
    table.add_row(
        "RAM",
        f"{hw['ram_gb']} GB",
        badge(hw["ram_gb"] >= 8)
    )
    table.add_row(
        "Disque C: libre",
        f"{hw['disk_c_free']} GB",
        badge(hw["disk_c_free"] >= 5)
    )
    table.add_row(
        "Disque D: libre",
        f"{hw['disk_d_free']} GB",
        badge(hw["disk_d_free"] >= 10)
    )
    table.add_row(
        "Driver NVIDIA",
        hw["driver"],
        badge(hw["cuda_ok"])
    )

    console.print()
    console.print(Align.center(table))
    console.print()


def print_project_cards(hw: dict):
    console.print(Rule("[bold white]Choisissez votre profil[/bold white]", style="magenta"))
    console.print()

    for key, proj in PROJETS.items():
        req = proj["requirements"]

        # Compatibilité
        compat = (
            hw["vram_gb"]  >= req["vram_gb"] and
            hw["ram_gb"]   >= req["ram_gb"]  and
            hw["compute"]  >= req["compute"]
        )

        compat_text = "[bold green]✅ Compatible avec votre PC[/bold green]" if compat else "[bold red]❌ PC insuffisant[/bold red]"

        # Table modèles
        mod_table = Table(box=None, show_header=False, padding=(0, 1))
        mod_table.add_column("cat", style="dim")
        mod_table.add_column("val", style="white")
        for cat, val in proj["models"].items():
            mod_table.add_row(f"  {cat}:", val)

        content = (
            f"\n[bold]{proj['badge']}[/bold]\n"
            f"[dim]{proj['description']}[/dim]\n\n"
            f"[bold white]Modèles inclus :[/bold white]"
        )

        panel_color = "green" if compat else "red"
        border_color = "bright_green" if compat else "bright_red"

        console.print(Panel(
            f"{content}",
            title=f"[bold white] [{key}] {proj['nom']} [/bold white]",
            border_style=border_color,
            subtitle=compat_text,
            padding=(0, 2),
        ))

        # Afficher les modèles
        for cat, val in proj["models"].items():
            console.print(f"    [dim cyan]{cat}:[/dim cyan]  {val}")

        # Requirments vs hardware
        req_table = Table(box=None, show_header=False, padding=(0, 1))
        req_table.add_column("item", style="dim")
        req_table.add_column("req")
        req_table.add_column("yours")
        req_table.add_row(
            "  VRAM:",
            f"[yellow]{req['vram_gb']} GB[/yellow]",
            f"{'[green]' if hw['vram_gb'] >= req['vram_gb'] else '[red]'}{hw['vram_gb']} GB{'[/green]' if hw['vram_gb'] >= req['vram_gb'] else '[/red]'}"
        )
        req_table.add_row(
            "  RAM:",
            f"[yellow]{req['ram_gb']} GB[/yellow]",
            f"{'[green]' if hw['ram_gb'] >= req['ram_gb'] else '[red]'}{hw['ram_gb']} GB{'[/green]' if hw['ram_gb'] >= req['ram_gb'] else '[/red]'}"
        )
        req_table.add_row(
            "  Stockage modèles:",
            f"[yellow]~{req['disk_gb']} GB[/yellow]",
            f"{'[green]' if hw['disk_d_free'] >= req['disk_gb'] else '[red]'}D: {hw['disk_d_free']} GB libres{'[/green]' if hw['disk_d_free'] >= req['disk_gb'] else '[/red]'}"
        )
        console.print(req_table)
        console.print()


# ─────────────────────────────────────────────────────────────
#  VÉRIFICATION PYTHON
# ─────────────────────────────────────────────────────────────
def check_python() -> tuple[bool, str]:
    """Retourne (ok, message)"""
    exe = sys.executable
    version = sys.version_info

    # Vérifie que c'est un vrai Python (pas l'alias MS Store)
    if "WindowsApps" in exe:
        return False, (
            "Python détecté est un alias Microsoft Store !\n"
            "Installez Python 3.10+ depuis https://www.python.org/downloads/\n"
            "⚠️  Cochez 'Add Python to PATH' lors de l'installation."
        )

    if version.major < 3 or (version.major == 3 and version.minor < 10):
        return False, f"Python 3.10+ requis (vous avez {version.major}.{version.minor})"

    return True, f"Python {version.major}.{version.minor}.{version.micro} ✅"


# ─────────────────────────────────────────────────────────────
#  TÉLÉCHARGEMENT DES MODÈLES
# ─────────────────────────────────────────────────────────────
def download_models(projet_key: str):
    proj = PROJETS[projet_key]
    script = proj["download_script"]
    args   = proj["download_args"]

    if not Path(script).exists():
        console.print(f"[red]Script introuvable : {script}[/red]")
        return False

    console.print()
    console.print(Panel(
        f"[bold white]Téléchargement des modèles pour[/bold white] [yellow]{proj['nom']}[/yellow]\n"
        f"[dim]Cela peut prendre du temps selon votre connexion...[/dim]",
        border_style="yellow",
    ))

    cmd = [sys.executable, script] + args

    # Set env vars avant de lancer
    env = os.environ.copy()
    env.update(proj["env_vars"])
    # Modèles sur disque D: si disponible
    if Path("D:\\").exists():
        env["MODELS_CACHE"] = "D:\\studio_ia_models"
        console.print(f"[dim]📁 Modèles seront sauvegardés dans D:\\studio_ia_models[/dim]")
    else:
        env["MODELS_CACHE"] = str(Path.home() / "studio_ia_models")

    try:
        process = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        with console.status("[bold green]Téléchargement en cours...[/bold green]", spinner="dots"):
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    if "✅" in line or "downloaded" in line.lower() or "complete" in line.lower():
                        console.print(f"  [green]{line}[/green]")
                    elif "❌" in line or "error" in line.lower() or "fail" in line.lower():
                        console.print(f"  [red]{line}[/red]")
                    elif "%" in line or "downloading" in line.lower():
                        console.print(f"  [cyan]{line}[/cyan]")
                    else:
                        console.print(f"  [dim]{line}[/dim]")

        process.wait()
        if process.returncode == 0:
            console.print("[bold green]✅ Téléchargements terminés ![/bold green]")
            return True
        else:
            console.print("[yellow]⚠️ Certains modèles ont échoué (voir logs ci-dessus)[/yellow]")
            return True  # On continue quand même

    except FileNotFoundError:
        console.print(f"[red]Impossible de lancer : {' '.join(cmd)}[/red]")
        return False


# ─────────────────────────────────────────────────────────────
#  APPLICATION DU PROFIL (variables d'environnement)
# ─────────────────────────────────────────────────────────────
def apply_profile(projet_key: str):
    """Écrit le fichier .env actif pour le projet choisi"""
    proj = PROJETS[projet_key]
    env_vars = proj["env_vars"].copy()

    # Chemin modèles sur D: si disponible
    if Path("D:\\").exists():
        env_vars["MODELS_CACHE"] = "D:\\studio_ia_models"
    else:
        env_vars["MODELS_CACHE"] = str(Path.home() / "studio_ia_models")

    # Injecter config_lite.py pour Projet 2
    if projet_key == "2":
        env_vars["STUDIO_PROFILE"] = "lite"

    # Écrire .env
    env_path = Path(".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"# Studio IA — Profil actif : {proj['nom']}\n")
        f.write(f"# Généré automatiquement par launcher.py\n\n")
        for key, val in env_vars.items():
            f.write(f"{key}={val}\n")

    console.print(f"[dim]✅ Profil sauvegardé dans .env[/dim]")
    return env_vars


# ─────────────────────────────────────────────────────────────
#  LANCEMENT DES SERVICES
# ─────────────────────────────────────────────────────────────
def launch_services(env_vars: dict, projet_key: str):
    proj = PROJETS[projet_key]

    console.print()
    console.print(Panel(
        f"[bold white]Lancement de Studio IA[/bold white]\n"
        f"[dim]Profil : {proj['nom']}[/dim]",
        border_style="green",
    ))

    env = os.environ.copy()
    env.update(env_vars)

    # Injecter config_lite si Projet 2
    if projet_key == "2":
        lite_path = str(Path(__file__).parent)
        if lite_path not in env.get("PYTHONPATH", ""):
            env["PYTHONPATH"] = lite_path + os.pathsep + env.get("PYTHONPATH", "")

    processes = []

    # 1. Base de données Celery
    console.print("\n[bold cyan]1/3 — Préparation de la base de données locale...[/bold cyan]")
    console.print("  [green]✅ Utilisation de SQLite (100% local, pas de Redis requis)[/green]")

    # 2. FastAPI backend
    console.print("\n[bold cyan]2/3 — Démarrage du backend FastAPI...[/bold cyan]")
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "api.routes:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--no-use-colors",
    ]
    try:
        p_backend = subprocess.Popen(
            backend_cmd, env=env,
            cwd=str(Path(__file__).parent),
        )
        processes.append(("Backend FastAPI", p_backend))
        time.sleep(2)
        console.print(f"  [green]✅ Backend PID {p_backend.pid} démarré[/green]")
    except Exception as e:
        console.print(f"  [red]❌ Erreur backend : {e}[/red]")

    # 3. Celery worker
    console.print("\n[bold cyan]3/3 — Démarrage du worker Celery...[/bold cyan]")
    celery_cmd = [
        sys.executable, "-m", "celery",
        "-A", "workers.celery_app",
        "worker",
        "--loglevel=warning",
        "--concurrency=1",
        "--pool=solo",
    ]
    try:
        p_celery = subprocess.Popen(
            celery_cmd, env=env,
            cwd=str(Path(__file__).parent),
        )
        processes.append(("Celery Worker", p_celery))
        time.sleep(2)
        console.print(f"  [green]✅ Celery PID {p_celery.pid} démarré[/green]")
    except Exception as e:
        console.print(f"  [red]❌ Erreur Celery : {e}[/red]")

    # 4. Frontend (optionnel)
    frontend_pkg = Path("frontend") / "package.json"
    if frontend_pkg.exists():
        console.print("\n[bold cyan]✨ — Démarrage du frontend Vue.js...[/bold cyan]")
        try:
            p_front = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(Path("frontend")),
                env=env,
            )
            processes.append(("Frontend Vue.js", p_front))
            console.print(f"  [green]✅ Frontend PID {p_front.pid} démarré[/green]")
        except Exception as e:
            console.print(f"  [yellow]  Frontend ignoré : {e}[/yellow]")

    frontend_pkg = Path("frontend") / "package.json"
    if frontend_pkg.exists():
        frontend_label = "[white]🎨 Frontend    :[/white]  [link=http://localhost:3000]http://localhost:3000[/link]\n\n"
    else:
        frontend_label = "[white]🎨 Interface   :[/white]  [link=http://localhost:8000]http://localhost:8000[/link]\n\n"

    # Résumé
    console.print()
    console.print(Rule(style="green"))
    console.print(Panel(
        "[bold green]✅  Studio IA démarré avec succès ![/bold green]\n\n"
        f"[white]🌐 API Backend :[/white]  [link=http://localhost:8000]http://localhost:8000[/link]\n"
        f"[white]📖 API Docs    :[/white]  [link=http://localhost:8000/docs]http://localhost:8000/docs[/link]\n"
        f"{frontend_label}"
        f"[dim]Profil actif : {proj['nom']}[/dim]\n"
        f"[dim]Appuyez sur Ctrl+C pour tout arrêter[/dim]",
        border_style="bright_green",
    ))

    failed_process = None
    try:
        while True:
            time.sleep(1)
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    failed_process = (name, code)
                    console.print(f"[red]⚠️  {name} s'est arrêté (code {code})[/red]")
                    raise RuntimeError(f"{name} arrêté")
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⏹️  Arrêt en cours...[/yellow]")
    except RuntimeError:
        if failed_process:
            name, code = failed_process
            console.print(f"[yellow]Arrêt de sécurité après crash de {name} (code {code}).[/yellow]")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
            console.print(f"  [dim]{name} arrêté[/dim]")
        console.print("[bold green]Au revoir ! 👋[/bold green]")


# ─────────────────────────────────────────────────────────────
#  POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────
def main():
    print_banner()

    # ── Vérification Python ───────────────────────────────────
    python_ok, python_msg = check_python()
    if not python_ok:
        console.print(Panel(
            f"[bold red]❌ Python non valide[/bold red]\n\n{python_msg}",
            title="Erreur Python",
            border_style="red",
        ))
        sys.exit(1)
    else:
        console.print(f"  [dim]🐍 {python_msg}[/dim]")

    # ── Détection hardware ────────────────────────────────────
    console.print()
    with console.status("[dim]Analyse du matériel...[/dim]", spinner="dots"):
        hw = detect_hardware()

    print_hardware(hw)
    print_project_cards(hw)

    # ── Choix du projet ───────────────────────────────────────
    console.print(Rule("[bold white]Votre choix[/bold white]", style="dim"))
    console.print()

    # Suggestion automatique
    if hw["vram_gb"] >= 24 and hw["ram_gb"] >= 32:
        suggestion = "[dim](votre PC est compatible avec Projet 1 et 2)[/dim]"
    else:
        suggestion = "[bold cyan]→ Projet 2 recommandé pour votre configuration[/bold cyan]"
    console.print(f"  {suggestion}\n")

    choix = Prompt.ask(
        "  Entrez [bold yellow]1[/bold yellow] pour Projet 1 "
        "ou [bold cyan]2[/bold cyan] pour Projet 2",
        choices=["1", "2"],
        default="2" if hw["vram_gb"] < 24 else "1",
    )

    proj = PROJETS[choix]
    console.print()
    console.print(Panel(
        f"[bold white]Profil sélectionné :[/bold white] {proj['nom']}\n"
        f"[dim]{proj['description']}[/dim]",
        border_style="magenta",
    ))

    # ── Téléchargement ────────────────────────────────────────
    console.print()
    already_downloaded = Confirm.ask(
        "  Les modèles sont-ils déjà téléchargés ?",
        default=False
    )

    if not already_downloaded:
        do_download = Confirm.ask(
            f"  Télécharger automatiquement les modèles pour [bold]{proj['nom']}[/bold] ?",
            default=True
        )
        if do_download:
            ok = download_models(choix)
            if not ok:
                console.print("[red]Téléchargement échoué. Vérifiez votre connexion.[/red]")
                if not Confirm.ask("  Continuer quand même ?", default=False):
                    sys.exit(1)

    # ── Application du profil ─────────────────────────────────
    env_vars = apply_profile(choix)

    # ── Lancement ─────────────────────────────────────────────
    do_launch = Confirm.ask(
        "  Lancer Studio IA maintenant ?",
        default=True
    )

    if do_launch:
        launch_services(env_vars, choix)
    else:
        console.print()
        console.print(Panel(
            f"[bold white]Profil '{proj['nom']}' configuré dans [cyan].env[/cyan][/bold white]\n\n"
            "Pour lancer manuellement :\n"
            "[bold yellow]  uvicorn api.routes:app --reload[/bold yellow]\n"
            "[bold yellow]  celery -A workers.celery_app worker --pool=solo[/bold yellow]",
            border_style="cyan",
        ))


if __name__ == "__main__":
    main()
