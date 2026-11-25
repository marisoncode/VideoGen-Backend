import os
import subprocess
from typing import List, Dict, Any, Optional
import imageio_ffmpeg
from app.core.config import settings

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

class MusicService:
    """
    Royalty-free Background Music & Audio Ducking Engine:
    Provides built-in ambient educational music tracks and seamlessly
    ducks background music underneath the spoken AI voice narration.
    """

    def __init__(self):
        self.music_dir = os.path.join(settings.STORAGE_DIR, "music")
        os.makedirs(self.music_dir, exist_ok=True)
        self._ensure_default_tracks()

    def _ensure_default_tracks(self):
        """Generates procedural high-quality ambient MP3 tracks if not present."""
        presets = [
            {
                "id": "inspiring_educational",
                "filename": "inspiring_educational.mp3",
                "filter": (
                    "[1:a]volume=0.07[a1];[2:a]volume=0.05[a2];[3:a]volume=0.05[a3];"
                    "[a1][a2][a3][0:a]amix=inputs=4,lowpass=f=1200,aecho=0.8:0.88:80:0.3[out]"
                ),
                "inputs": [
                    ["-f", "lavfi", "-i", "anoisesrc=c=pink:r=44100:a=0.008"],
                    ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=277.18:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=329.63:sample_rate=44100"],
                ]
            },
            {
                "id": "gentle_lofi",
                "filename": "gentle_lofi.mp3",
                "filter": (
                    "[1:a]volume=0.08[a1];[2:a]volume=0.06[a2];[3:a]volume=0.05[a3];"
                    "[a1][a2][a3][0:a]amix=inputs=4,lowpass=f=750,aecho=0.7:0.8:120:0.35[out]"
                ),
                "inputs": [
                    ["-f", "lavfi", "-i", "anoisesrc=c=brown:r=44100:a=0.012"],
                    ["-f", "lavfi", "-i", "sine=frequency=196.00:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=246.94:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=293.66:sample_rate=44100"],
                ]
            },
            {
                "id": "playful_curiosity",
                "filename": "playful_curiosity.mp3",
                "filter": (
                    "[1:a]volume=0.07[a1];[2:a]volume=0.06[a2];[3:a]volume=0.06[a3];"
                    "[a1][a2][a3][0:a]amix=inputs=4,highpass=f=200,lowpass=f=2400,aecho=0.75:0.85:50:0.25[out]"
                ),
                "inputs": [
                    ["-f", "lavfi", "-i", "anoisesrc=c=pink:r=44100:a=0.006"],
                    ["-f", "lavfi", "-i", "sine=frequency=261.63:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=329.63:sample_rate=44100"],
                    ["-f", "lavfi", "-i", "sine=frequency=392.00:sample_rate=44100"],
                ]
            }
        ]

        for p in presets:
            out_file = os.path.join(self.music_dir, p["filename"])
            if not os.path.exists(out_file) or os.path.getsize(out_file) < 5000:
                input_args = []
                for inp in p["inputs"]:
                    input_args.extend(inp)
                cmd = [
                    FFMPEG_BIN, "-y",
                    *input_args,
                    "-filter_complex", p["filter"],
                    "-map", "[out]",
                    "-t", "45",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    out_file
                ]
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"[MusicService] Generated ambient track: {p['filename']}")
                except Exception as e:
                    print(f"[MusicService] Failed generating {p['filename']}: {e}")

    def get_available_tracks(self) -> List[Dict[str, Any]]:
        """Returns the available royalty-free background music tracks."""
        return [
            {
                "id": "inspiring_educational",
                "name": "Inspiring Educational",
                "description": "Warm, uplifting acoustic resonance for clear learning",
                "preview_url": "/static/music/inspiring_educational.mp3"
            },
            {
                "id": "gentle_lofi",
                "name": "Gentle Lofi Study",
                "description": "Smooth, relaxed, focused ambient warmth",
                "preview_url": "/static/music/gentle_lofi.mp3"
            },
            {
                "id": "playful_curiosity",
                "name": "Playful Curiosity",
                "description": "Bright, cheerful, engaging atmosphere",
                "preview_url": "/static/music/playful_curiosity.mp3"
            },
            {
                "id": "none",
                "name": "No Background Music",
                "description": "Crisp teacher speech narration only",
                "preview_url": ""
            }
        ]

    def mix_audio_with_ducking(
        self,
        voice_audio_path: str,
        music_track_id: Optional[str],
        output_audio_path: str,
        ducking_volume: float = 0.12
    ) -> str:
        """
        Ducks background music under spoken narration:
        Voice plays at full volume (100%), background music plays at ducking_volume (12-15%).
        """
        os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)

        if not music_track_id or music_track_id.lower() in ["none", ""]:
            # Just copy or convert voice audio
            cmd = [FFMPEG_BIN, "-y", "-i", voice_audio_path, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_audio_path

        music_filename = f"{music_track_id}.mp3"
        music_path = os.path.join(self.music_dir, music_filename)

        if not os.path.exists(music_path):
            # Fallback to copy voice
            cmd = [FFMPEG_BIN, "-y", "-i", voice_audio_path, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_audio_path

        # FFmpeg amix with volume ducking and looped background music
        filter_complex = (
            f"[0:a]volume=1.0,aformat=sample_rates=44100:channel_layouts=stereo[v];"
            f"[1:a]volume={ducking_volume},aformat=sample_rates=44100:channel_layouts=stereo[bg];"
            f"[v][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            FFMPEG_BIN, "-y",
            "-i", voice_audio_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output_audio_path
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[MusicService] Audio ducking error: {e}, falling back to speech only.")
            cmd_fallback = [FFMPEG_BIN, "-y", "-i", voice_audio_path, "-c:a", "libmp3lame", output_audio_path]
            subprocess.run(cmd_fallback, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return output_audio_path

music_service = MusicService()
