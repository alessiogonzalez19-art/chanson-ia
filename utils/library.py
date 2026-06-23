"""
Gestion de la bibliothèque musicale.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from config import config

class LibraryManager:
    def __init__(self):
        self.library_dir = config.workspace_root / "library"
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.library_dir / "metadata.json"
        self._init_metadata()

    def _init_metadata(self):
        if not self.metadata_file.exists():
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load_metadata(self) -> List[Dict]:
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            return []

    def _save_metadata(self, data: List[Dict]):
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def add_track(self, filename: str, source: str, genre: str, bpm: Optional[int] = None, duration: Optional[float] = None) -> Dict:
        metadata = self._load_metadata()
        track_info = {
            "id": filename,
            "filename": filename,
            "source": source, # "generated" ou "scraped"
            "genre": genre,
            "bpm": bpm,
            "duration": duration,
            "url": f"/api/library/stream/{filename}"
        }
        
        # Check if already exists
        for idx, t in enumerate(metadata):
            if t["id"] == filename:
                metadata[idx] = track_info
                self._save_metadata(metadata)
                return track_info
                
        metadata.append(track_info)
        self._save_metadata(metadata)
        return track_info

    def get_all_tracks(self) -> List[Dict]:
        return self._load_metadata()

    def get_track(self, track_id: str) -> Optional[Dict]:
        metadata = self._load_metadata()
        for t in metadata:
            if t["id"] == track_id:
                return t
        return None

    def delete_track(self, track_id: str) -> bool:
        metadata = self._load_metadata()
        new_metadata = [t for t in metadata if t["id"] != track_id]
        if len(new_metadata) != len(metadata):
            self._save_metadata(new_metadata)
            file_path = self.library_dir / track_id
            if file_path.exists():
                file_path.unlink()
            return True
        return False
