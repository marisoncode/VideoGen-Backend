import os
import time
import base64
import requests
from typing import Optional, Dict, Any
from app.core.config import settings

class ReplicateService:
    BASE_URL = "https://api.replicate.com/v1"

    def __init__(self):
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "").strip()

    def is_configured(self) -> bool:
        """Checks if Replicate API token is configured."""
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "").strip()
        return bool(self.api_token and self.api_token.startswith("r8_"))

    def get_headers(self, wait_seconds: int = 60) -> Dict[str, str]:
        """Returns authorization and request headers for Replicate API."""
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "").strip()
        if not self.is_configured():
            raise ValueError("Replicate API token (r8_...) is not configured in backend/.env")
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        if wait_seconds > 0:
            headers["Prefer"] = f"wait={wait_seconds}"
        return headers

    def _log_debug(self, msg: str):
        """Appends timestamped debug messages to backend/storage/replicate_debug.log."""
        log_path = os.path.join(settings.STORAGE_DIR, "replicate_debug.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {msg}\n"
        print(f"[Replicate] {msg}")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def _file_to_data_uri(self, filepath: str, default_mime: str = "image/jpeg") -> str:
        """Converts a local file into a Base64 Data-URI for Replicate file upload."""
        if filepath.startswith("http://") or filepath.startswith("https://"):
            return filepath

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        mime = "image/png" if ext == ".png" else ("image/jpeg" if ext in [".jpg", ".jpeg"] else default_mime)
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    def _prepare_image_input(self, filepath: str) -> str:
        """Uploads local image to Replicate files API or returns Data URI."""
        if filepath.startswith("http://") or filepath.startswith("https://"):
            return filepath

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Local image not found: {filepath}")

        # Attempt Replicate File Upload endpoint (handles any file size natively)
        try:
            headers = {"Authorization": f"Bearer {self.api_token}"}
            ext = os.path.splitext(filepath)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            with open(filepath, "rb") as f:
                files = {"content": (os.path.basename(filepath), f, mime)}
                res = requests.post(f"{self.BASE_URL}/files", headers=headers, files=files, timeout=60)
                if res.status_code in [200, 201]:
                    file_url = res.json().get("urls", {}).get("get")
                    if file_url:
                        self._log_debug(f"Image uploaded to Replicate storage: {file_url[:60]}...")
                        return file_url
        except Exception as e:
            self._log_debug(f"File upload notice: {e}, using Data-URI fallback.")

        # Fallback to Data URI
        return self._file_to_data_uri(filepath, "image/jpeg")

    def animate_character(
        self,
        image_path: str,
        motion_prompt: str,
        audio_path: Optional[str] = None,
        duration_sec: int = 5,
        output_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Animates a character image using Replicate's cloud video models (LTX-Video).
        Produces lifelike movement, facial expressions, and natural eye blinking.
        """
        if not self.is_configured():
            self._log_debug("Warning: REPLICATE_API_TOKEN not configured.")
            return None

        # Prepare image (either Replicate file URL or Data-URI)
        image_input = self._prepare_image_input(image_path)

        # Ensure prompt emphasizes facial movement and blinking
        enhanced_prompt = motion_prompt
        lp = motion_prompt.lower()
        if not any(k in lp for k in ["blink", "smile", "expression", "facial", "face", "talking"]):
            enhanced_prompt = f"{motion_prompt}, highly expressive facial expressions, natural eye blinking, gentle smile, lifelike character animation"

        endpoint = f"{self.BASE_URL}/predictions"
        headers = self.get_headers(wait_seconds=60)
        
        # Lightricks LTX-Video official active version hash on Replicate
        ltx_version = "8c47da666861d081eeb4d1261853087de23923a268a69b63febdf5dc1dee08e4"

        payload = {
            "version": ltx_version,
            "input": {
                "image": image_input,
                "prompt": enhanced_prompt,
                "frame_rate": 25
            }
        }

        self._log_debug(f"Submitting prediction to {endpoint} with prompt: '{enhanced_prompt[:60]}...'")
        res = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        
        # Handle free-tier burst rate limit throttling
        if res.status_code == 429:
            retry_sec = 2
            try:
                retry_sec = int(res.json().get("retry_after", 2))
            except Exception:
                pass
            self._log_debug(f"Throttled (429). Waiting {retry_sec + 2}s before retrying...")
            time.sleep(retry_sec + 2)
            res = requests.post(endpoint, headers=headers, json=payload, timeout=90)

        if res.status_code not in [200, 201]:
            err_text = res.text
            self._log_debug(f"API Error ({res.status_code}): {err_text}")
            raise RuntimeError(f"Replicate API error HTTP {res.status_code}: {err_text}")

        res_json = res.json()
        prediction_id = res_json.get("id")
        status = res_json.get("status")
        output = res_json.get("output")
        get_url = res_json.get("urls", {}).get("get") or f"{self.BASE_URL}/predictions/{prediction_id}"

        self._log_debug(f"Prediction {prediction_id} created with status: '{status}'")

        # Poll until complete if not completed in initial response
        start_time = time.time()
        max_wait = 600  # 10 minutes max
        poll_interval = 4

        while status not in ["succeeded", "failed", "canceled"]:
            if time.time() - start_time > max_wait:
                raise TimeoutError("Replicate video generation timed out.")
            
            time.sleep(poll_interval)
            headers_poll = self.get_headers(wait_seconds=0)
            poll_res = requests.get(get_url, headers=headers_poll, timeout=30)
            if poll_res.status_code == 200:
                p_data = poll_res.json()
                status = p_data.get("status")
                output = p_data.get("output")
                self._log_debug(f"Prediction {prediction_id} status: {status} ({int(time.time() - start_time)}s elapsed)")
            else:
                self._log_debug(f"Polling HTTP {poll_res.status_code}, retrying...")

        if status != "succeeded" or not output:
            err_detail = res_json.get("error") or "Unknown error"
            self._log_debug(f"Prediction {prediction_id} failed with status '{status}': {err_detail}")
            raise RuntimeError(f"Replicate prediction {prediction_id} failed: {err_detail}")

        video_url = output if isinstance(output, str) else output[0]
        self._log_debug(f"Animation complete! Downloading: {video_url[:60]}...")

        # Download rendered MP4 to local visual cache
        out_folder = output_dir or os.path.join(settings.BASE_DIR, "storage", "visual_cache", "replicate_clips")
        os.makedirs(out_folder, exist_ok=True)
        local_mp4 = os.path.join(out_folder, f"replicate_{prediction_id}.mp4")

        vid_res = requests.get(video_url, stream=True, timeout=120)
        with open(local_mp4, "wb") as f:
            for chunk in vid_res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        self._log_debug(f"Video saved successfully to: {local_mp4}")
        return local_mp4

replicate_service = ReplicateService()
