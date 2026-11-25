import os
import time
import subprocess
from typing import Dict, Any, List, Optional
import imageio_ffmpeg
from app.core.config import settings
from app.services.tts_service import tts_service

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

class VoiceAgent:
    """
    Dedicated Voice & Audio Agent:
    - Handles reference audio file uploads, normalization, and audio waveform/duration extraction.
    - Provides real-time preview of uploaded reference audio files.
    - Synthesizes spoken voice narration with Edge Neural TTS or zero-shot reference voice cloning.
    """

    AVAILABLE_VOICES = [
        {
            "id": "Reference Voice Clone (100% Match)",
            "name": "Reference Voice Clone (Cloned Voice)",
            "locale": "Warm Cloned Teacher",
            "gender": "Female"
        },
        {
            "id": "en-IN-NeerjaNeural",
            "name": "Indian English (Neerja)",
            "locale": "Studio Indian English",
            "gender": "Female"
        },
        {
            "id": "en-US-JennyNeural",
            "name": "Jenny (Natural Storyteller)",
            "locale": "US English Warm",
            "gender": "Female"
        },
        {
            "id": "en-US-GuyNeural",
            "name": "Guy (Educational Lecturer)",
            "locale": "US English Clear",
            "gender": "Male"
        }
    ]

    def __init__(self):
        self.uploads_dir = settings.UPLOADS_DIR
        os.makedirs(self.uploads_dir, exist_ok=True)

    def get_available_voices(self) -> List[Dict[str, str]]:
        return self.AVAILABLE_VOICES

    def save_and_normalize_reference_audio(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Saves user-uploaded reference audio file, normalizes to 24kHz mono WAV,
        and returns audio details including public preview URL for in-browser playback.
        """
        timestamp = int(time.time())
        safe_fn = "".join(c for c in filename if c.isalnum() or c in "._- ")
        raw_path = os.path.join(self.uploads_dir, f"ref_raw_{timestamp}_{safe_fn}")

        with open(raw_path, "wb") as f:
            f.write(file_bytes)

        # Normalize to 24000Hz mono WAV
        norm_name = f"voice_ref_{timestamp}.wav"
        norm_path = os.path.join(self.uploads_dir, norm_name)

        duration = 5.0
        try:
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", raw_path,
                "-ac", "1",
                "-ar", "24000",
                norm_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            target_path = norm_path
            target_name = norm_name
            duration = self._get_audio_duration(norm_path)
        except Exception as e:
            print(f"[VoiceAgent] Audio normalization notice: {e}")
            target_path = raw_path
            target_name = os.path.basename(raw_path)

        voice_id = f"custom_voice:{target_path}"
        voice_label = f"Uploaded Reference Audio ({filename})"

        return {
            "status": "success",
            "voice_id": voice_id,
            "voice_name": voice_label,
            "filename": target_name,
            "local_path": target_path,
            "preview_url": f"/static/uploads/{target_name}",
            "duration_seconds": round(duration, 2)
        }

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            import re
            cmd = [FFMPEG_BIN, "-i", audio_path]
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if match:
                h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
                return h * 3600 + m * 60 + s
        except Exception:
            pass
        return 5.0

    def synthesize_speech(self, text: str, output_path: str, voice: str) -> str:
        """Synthesizes voice narration audio file."""
        return tts_service.generate_speech(text, output_path, voice=voice)

voice_agent = VoiceAgent()
