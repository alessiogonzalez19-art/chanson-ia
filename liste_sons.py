"""
Liste et ouvre les fichiers audio générés par le Studio IA
"""

import os
from pathlib import Path
import subprocess
from datetime import datetime
import soundfile as sf

def format_size(bytes):
    """Formate la taille du fichier"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} TB"

def get_audio_info(file_path):
    """Récupère les infos d'un fichier audio"""
    try:
        info = sf.info(file_path)
        duration = info.duration
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes}:{seconds:02d}", info.samplerate
    except:
        return "?:??", "?"

def list_audio_files():
    """Liste tous les fichiers audio du projet"""
    
    print("\n" + "="*60)
    print("  🎵 FICHIERS AUDIO - Studio IA")
    print("="*60 + "\n")
    
    # Dossiers à scanner
    folders = [
        ("Traitement temporaire", Path("temp_processing")),
        ("YouTube téléchargements", Path("D:/studio_ia_temp/youtube_downloads") if Path("D:/").exists() else None),
        ("Sortie FL Studio", Path("FL_Studio_Output")),
    ]
    
    total_files = 0
    all_files = []
    
    for name, folder in folders:
        if folder is None or not folder.exists():
            continue
            
        print(f"📁 {name} ({folder})")
        print("-" * 60)
        
        files = list(folder.rglob("*.wav"))
        if not files:
            print("   Aucun fichier\n")
            continue
        
        for i, file in enumerate(sorted(files, key=lambda x: x.stat().st_mtime, reverse=True), 1):
            stat = file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            size = format_size(stat.st_size)
            duration, sr = get_audio_info(file)
            
            # Nom relatif pour affichage
            try:
                rel_name = file.relative_to(folder)
            except:
                rel_name = file.name
            
            print(f"   {total_files + i}. {rel_name}")
            print(f"      Durée: {duration} | Taille: {size} | Sample Rate: {sr} Hz")
            print(f"      Modifié: {mtime.strftime('%d/%m/%Y %H:%M')}")
            print()
            
            all_files.append(file)
        
        total_files += len(files)
    
    if total_files == 0:
        print("\n❌ Aucun fichier audio trouvé !")
        print("\nTu dois d'abord lancer un remix ou télécharger un son YouTube.\n")
        return []
    
    print("="*60)
    print(f"Total: {total_files} fichiers audio\n")
    
    return all_files

def open_file(file_path):
    """Ouvre un fichier avec le lecteur par défaut"""
    try:
        os.startfile(str(file_path))
        print(f"✅ Ouverture de : {file_path.name}")
    except Exception as e:
        print(f"❌ Erreur : {e}")

def main():
    files = list_audio_files()
    
    if not files:
        input("\nAppuie sur Entrée pour quitter...")
        return
    
    print("Options:")
    print("  1-N  : Ouvrir le fichier numéro N")
    print("  all  : Ouvrir tous les fichiers")
    print("  last : Ouvrir le plus récent")
    print("  dir  : Ouvrir le dossier dans l'explorateur")
    print("  quit : Quitter")
    print()
    
    while True:
        choice = input("Ton choix: ").strip().lower()
        
        if choice == "quit" or choice == "q":
            break
        
        elif choice == "all":
            print("\n🎵 Ouverture de tous les fichiers...")
            for file in files:
                open_file(file)
            break
        
        elif choice == "last":
            print("\n🎵 Ouverture du fichier le plus récent...")
            # Le plus récent est déjà en premier (trié par mtime)
            open_file(files[0])
            break
        
        elif choice == "dir":
            print("\n📁 Ouverture du dossier...")
            os.startfile("temp_processing")
            break
        
        elif choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(files):
                open_file(files[num - 1])
                break
            else:
                print(f"❌ Numéro invalide (1-{len(files)})")
        
        else:
            print("❌ Choix invalide")
    
    print("\n✅ Terminé !\n")

if __name__ == "__main__":
    main()
