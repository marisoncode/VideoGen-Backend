import os
from typing import List, Dict, Any, Optional
from app.services.music_service import music_service

class MusicAgent:
    """
    Dedicated Music & Audio Ducking Agent:
    Manages ambient score selection, royalty-free audio tracks, and audio ducking algorithms
    ensuring spoken narration is never drowned out by background music.
    """

    def get_tracks(self) -> List[Dict[str, Any]]:
        return music_service.get_available_tracks()

    def mix_and_duck(
        self,
        voice_audio_path: str,
        music_track_id: Optional[str],
        output_audio_path: str,
        ducking_volume: float = 0.12
    ) -> str:
        """Ducks background music under speech audio."""
        return music_service.mix_audio_with_ducking(
            voice_audio_path=voice_audio_path,
            music_track_id=music_track_id,
            output_audio_path=output_audio_path,
            ducking_volume=ducking_volume
        )

music_agent = MusicAgent()
