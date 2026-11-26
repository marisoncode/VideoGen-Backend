import os
import time
from typing import Optional, Dict, Any
from app.core.config import settings

class MagicHourService:
    def __init__(self):
        self.api_key = os.getenv("MAGIC_HOUR_API_KEY", "").strip() or getattr(settings, "MAGIC_HOUR_API_KEY", "").strip()

    def is_configured(self) -> bool:
        """Checks if Magic Hour API token is configured."""
        self.api_key = os.getenv("MAGIC_HOUR_API_KEY", "").strip() or getattr(settings, "MAGIC_HOUR_API_KEY", "").strip()
        return bool(self.api_key and self.api_key.startswith("mhk_"))

    def get_client(self):
        from magic_hour import Client
        self.api_key = os.getenv("MAGIC_HOUR_API_KEY", "").strip() or getattr(settings, "MAGIC_HOUR_API_KEY", "").strip()
        return Client(token=self.api_key)

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Returns account credits and tier status."""
        if not self.is_configured():
            return None
        try:
            client = self.get_client()
            acc = client.v1.account.list()
            return {
                "id": getattr(acc, "id", ""),
                "email": getattr(acc, "email", ""),
                "credits": getattr(acc, "credits", 0),
                "tier": getattr(acc, "tier", "free")
            }
        except Exception as e:
            self._log_debug(f"Account check error: {e}")
            return None

    def _log_debug(self, msg: str):
        """Appends timestamped debug messages to backend/storage/magic_hour_debug.log."""
        log_path = os.path.join(settings.STORAGE_DIR, "magic_hour_debug.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {msg}\n"
        print(f"[MagicHour] {msg}")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def animate_character(
        self,
        image_path: str,
        motion_prompt: str,
        duration_sec: int = 5,
        output_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Animates a scene keyframe image into video using Magic Hour Image-to-Video API (LTX-2.5).
        Produces natural character movement, eye blinking, and expressive facial motion.
        """
        if not self.is_configured():
            self._log_debug("Warning: MAGIC_HOUR_API_KEY not configured.")
            return None

        if not os.path.exists(image_path):
            self._log_debug(f"Error: image file not found at {image_path}")
            return None

        client = self.get_client()

        # Enhance motion prompt for natural Pixar character animation
        enhanced_prompt = motion_prompt
        lp = motion_prompt.lower()
        if not any(k in lp for k in ["blink", "smile", "expression", "facial", "face", "talking", "movement"]):
            enhanced_prompt = f"{motion_prompt}, subtle expressive facial expressions, natural eye blinking, gentle smile, lifelike Pixar character movement, smooth cinematic motion"

        out_folder = output_dir or os.path.join(settings.BASE_DIR, "storage", "visual_cache", "magic_hour_clips")
        os.makedirs(out_folder, exist_ok=True)

        clip_seconds = min(10.0, max(3.0, float(duration_sec)))

        self._log_debug(f"Submitting Image-to-Video to Magic Hour (model=ltx-2.5, duration={clip_seconds}s)...")
        self._log_debug(f"Prompt: {enhanced_prompt[:80]}...")

        try:
            # client.v1.image_to_video.generate handles upload, creation, polling, and downloading automatically
            res = client.v1.image_to_video.generate(
                assets={
                    "image_file_path": os.path.abspath(image_path),
                },
                style={"prompt": enhanced_prompt},
                end_seconds=clip_seconds,
                model="ltx-2.5",
                resolution="480p",
                audio=False,
                wait_for_completion=True,
                download_outputs=True,
                download_directory=out_folder,
            )

            status = getattr(res, "status", None)
            downloaded = getattr(res, "downloaded_paths", [])

            self._log_debug(f"Magic Hour completed with status='{status}', downloaded={downloaded}")

            if status == "complete" and downloaded and len(downloaded) > 0:
                local_video = downloaded[0]
                if os.path.exists(local_video):
                    self._log_debug(f"Magic Hour video ready at: {local_video}")
                    return local_video

            # Fallback: if download_outputs didn't download locally, fetch from direct URL
            downloads = getattr(res, "downloads", [])
            if status == "complete" and downloads and len(downloads) > 0:
                first_dl = downloads[0]
                dl_url = getattr(first_dl, "url", None)
                if dl_url:
                    import requests
                    vid_name = f"mh_{int(time.time()*1000)}.mp4"
                    local_video = os.path.join(out_folder, vid_name)
                    r = requests.get(dl_url, stream=True, timeout=120)
                    with open(local_video, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    self._log_debug(f"Downloaded from URL to: {local_video}")
                    return local_video

            err = getattr(res, "error", "Unknown error")
            self._log_debug(f"Magic Hour video generation unfulfilled. Error: {err}")
            return None

        except Exception as e:
            self._log_debug(f"Magic Hour generation exception: {e}")
            return None

magic_hour_service = MagicHourService()
