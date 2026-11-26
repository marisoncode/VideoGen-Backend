import os
import time
import base64
import requests
from typing import Dict, Any, List, Optional
from app.core.config import settings

class ImageAgent:
    """
    Dedicated AI Image Generation Agent:
    - Primary: Cloudflare Workers AI (@cf/black-forest-labs/flux-1-schnell, 10,000 free neurons/day).
    - Secondary: Replicate FLUX.1-schnell for fast, 16:9 widescreen educational visuals.
    - Prevents redundant regeneration if scene image already exists or was uploaded.
    """

    REPLICATE_FLUX_MODEL = "black-forest-labs/flux-schnell"
    REPLICATE_FLUX_VERSION = "c846a69991daf4c0e5d016514849d14ee5b2e6846ce6b9d6f21369e564cfe51e"
    CLOUDFLARE_FLUX_MODEL = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(self):
        self.uploads_dir = settings.UPLOADS_DIR
        os.makedirs(self.uploads_dir, exist_ok=True)

    def _log(self, msg: str):
        log_path = os.path.join(settings.STORAGE_DIR, "image_agent.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [ImageAgent] {msg}\n"
        print(f"[ImageAgent] {msg}")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def generate_scene_image(self, prompt: str, scene_idx: int = 1, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Renders a dedicated 16:9 scene visual:
        1. Cloudflare Workers AI FLUX (Free 10,000 neurons/day)
        2. Replicate FLUX.1-schnell
        """
        timestamp = int(time.time() * 1000)
        img_bytes = None
        used_provider = None
        errors = []

        # 1. Try Cloudflare Workers AI FLUX (Free daily quota)
        try:
            img_bytes = self._try_cloudflare_flux(prompt, scene_idx)
            if img_bytes:
                used_provider = "cloudflare_flux"
        except Exception as e:
            errors.append(f"Cloudflare: {e}")
            self._log(f"Cloudflare notice on scene {scene_idx}: {e}")

        # 2. Try Replicate FLUX
        if not img_bytes:
            try:
                img_bytes = self._try_replicate_flux(prompt, scene_idx)
                if img_bytes:
                    used_provider = "replicate_flux"
            except Exception as e:
                errors.append(f"Replicate: {e}")
                self._log(f"Replicate notice on scene {scene_idx}: {e}")

        if not img_bytes:
            err_summary = "; ".join(errors) if errors else "Image generation unfulfilled."
            raise ValueError(f"Scene {scene_idx} image generation failed: {err_summary}")

        # Save image to uploads directory
        filename = f"ai_scene_{scene_idx}_{timestamp}.jpg"
        save_path = os.path.join(self.uploads_dir, filename)

        with open(save_path, "wb") as f:
            f.write(img_bytes)
        self._log(f"Scene {scene_idx} image saved: {filename} ({used_provider})")

        return {
            "filename": filename,
            "local_path": save_path,
            "preview_url": f"/static/uploads/{filename}",
            "provider": used_provider
        }

    def _sanitize_prompt_for_safety(self, prompt: str) -> str:
        """
        Sanitizes prompts that trigger automated cloud NSFW false positives.
        Replaces sensitive physical context with wholesome educational phrasing.
        """
        import re
        s = prompt
        patterns = [
            (r'\b(undress|bare|naked|flesh|sensual|intimate|chest)\b', 'clothed'),
            (r'\b(subsurface scattering)\b', 'smooth stylized lighting'),
        ]
        for pat, rep in patterns:
            s = re.sub(pat, rep, s, flags=re.IGNORECASE)
        s = re.sub(r'\s*,\s*', ', ', s)
        s = re.sub(r',\s*,+', ', ', s)
        return s.strip()

    def _try_cloudflare_flux(self, prompt: str, scene_idx: int) -> Optional[bytes]:
        """
        Renders a 16:9 FLUX.1-schnell image via Cloudflare Workers AI (10,000 free neurons/day).
        """
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip() or getattr(settings, "CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip() or getattr(settings, "CLOUDFLARE_API_TOKEN", "").strip()

        # Dynamically reload .env if empty to catch credentials added while server is running
        if not account_id or not api_token:
            from dotenv import load_dotenv
            env_file = os.path.join(settings.BASE_DIR, ".env")
            if os.path.exists(env_file):
                load_dotenv(env_file, override=True)
                account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
                api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

        if not account_id or not api_token:
            return None

        self._log(f"Generating Scene {scene_idx} via Cloudflare Workers AI ({self.CLOUDFLARE_FLUX_MODEL})...")

        clean_prompt = prompt.strip()
        if "16:9" not in clean_prompt and "widescreen" not in clean_prompt.lower():
            clean_prompt = f"{clean_prompt}, 16:9 widescreen composition, realistic educational photography, clean, sharp focus, no text, no words"

        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{self.CLOUDFLARE_FLUX_MODEL}"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": clean_prompt,
            "steps": 4
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=75)
            if res.status_code == 200:
                data = res.json()
                b64_img = data.get("result", {}).get("image")
                if b64_img:
                    return base64.b64decode(b64_img)
            elif res.status_code == 400 and "NSFW" in res.text:
                self._log(f"Cloudflare safety false-positive on scene {scene_idx}. Auto-sanitizing prompt and retrying...")
                sanitized_prompt = self._sanitize_prompt_for_safety(clean_prompt)
                self._log(f"Scene {scene_idx} sanitized retry prompt: {sanitized_prompt[:90]}...")
                retry_res = requests.post(url, headers=headers, json={"prompt": sanitized_prompt, "steps": 4}, timeout=75)
                if retry_res.status_code == 200:
                    data = retry_res.json()
                    b64_img = data.get("result", {}).get("image")
                    if b64_img:
                        self._log(f"Scene {scene_idx} successfully recovered via sanitized prompt!")
                        return base64.b64decode(b64_img)
                else:
                    self._log(f"Cloudflare sanitized retry failed (HTTP {retry_res.status_code}): {retry_res.text[:120]}")
            else:
                self._log(f"Cloudflare HTTP {res.status_code}: {res.text[:120]}")
        except Exception as e:
            self._log(f"Cloudflare Workers AI notice on scene {scene_idx}: {e}")

        return None

    def _try_replicate_flux(self, prompt: str, scene_idx: int) -> Optional[bytes]:
        """
        Renders a 16:9 FLUX.1-schnell image via Replicate API.
        """
        token = os.getenv("REPLICATE_API_TOKEN", "").strip() or getattr(settings, "REPLICATE_API_TOKEN", "").strip()
        if not token or not token.startswith("r8_"):
            return None

        self._log(f"Generating Scene {scene_idx} via Replicate FLUX.1-schnell...")

        clean_prompt = prompt.strip()
        if "16:9" not in clean_prompt and "widescreen" not in clean_prompt.lower():
            clean_prompt = f"{clean_prompt}, 16:9 widescreen composition, realistic educational photography, clean, no text, no words"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "wait=60"
        }

        # Try model endpoint first
        url = f"https://api.replicate.com/v1/models/{self.REPLICATE_FLUX_MODEL}/predictions"
        payload = {
            "input": {
                "prompt": clean_prompt,
                "aspect_ratio": "16:9",
                "num_outputs": 1,
                "output_format": "jpg",
                "disable_safety_checker": True
            }
        }

        res = requests.post(url, headers=headers, json=payload, timeout=75)

        # Fallback to version predictions endpoint if model route returns 404
        if res.status_code == 404:
            url = "https://api.replicate.com/v1/predictions"
            payload = {
                "version": self.REPLICATE_FLUX_VERSION,
                "input": {
                    "prompt": clean_prompt,
                    "aspect_ratio": "16:9",
                    "num_outputs": 1,
                    "output_format": "jpg"
                }
            }
            res = requests.post(url, headers=headers, json=payload, timeout=75)

        if res.status_code in [200, 201]:
            data = res.json()
            status = data.get("status")
            output = data.get("output")

            # Poll if not immediately finished
            if status not in ["succeeded", "failed", "canceled"]:
                poll_url = data.get("urls", {}).get("get") or f"https://api.replicate.com/v1/predictions/{data.get('id')}"
                for _ in range(30):
                    time.sleep(2)
                    poll_res = requests.get(poll_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
                    if poll_res.status_code == 200:
                        p_data = poll_res.json()
                        status = p_data.get("status")
                        output = p_data.get("output")
                        if status in ["succeeded", "failed", "canceled"]:
                            break

            if status == "succeeded" and output:
                img_url = output if isinstance(output, str) else output[0]
                dl_res = requests.get(img_url, timeout=30)
                if dl_res.status_code == 200 and len(dl_res.content) > 1000:
                    return dl_res.content
        elif res.status_code == 402:
            self._log("Replicate notice: Account credit required (HTTP 402).")
        else:
            self._log(f"Replicate HTTP {res.status_code}: {res.text[:120]}")

        return None

    def generate_storyboard_images(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Renders scene images sequentially. Reuses existing or user-uploaded images if already present.
        """
        updated = []
        for i, s in enumerate(scenes):
            s_num = s.get("scene_number", i + 1)
            existing_path = s.get("image_path")
            existing_preview = s.get("preview_url")

            # Check if an image is already validly associated
            if existing_path and os.path.exists(existing_path) and os.path.getsize(existing_path) > 1000:
                print(f"[ImageAgent] Scene {s_num} already has valid image: {os.path.basename(existing_path)}")
                updated.append(s)
                continue

            if existing_preview and existing_preview.startswith("/static/uploads/"):
                clean_fn = os.path.basename(existing_preview)
                check_path = os.path.join(self.uploads_dir, clean_fn)
                if os.path.exists(check_path) and os.path.getsize(check_path) > 1000:
                    s["image_path"] = check_path
                    updated.append(s)
                    continue

            prompt = s.get("image_prompt") or f"Visual scene {s_num}"
            try:
                res = self.generate_scene_image(prompt, scene_idx=s_num)
                s["image_path"] = res["local_path"]
                s["preview_url"] = res["preview_url"]
                s["image_provider"] = res["provider"]
                s["image_error"] = None
            except Exception as e:
                self._log(f"Scene {s_num} image generation notice: {e}")
                s["image_path"] = None
                s["preview_url"] = None
                s["image_provider"] = "replicate_flux"
                s["image_error"] = str(e)
            updated.append(s)
        return updated

    def regenerate_scene_image(self, scene_index: int, custom_prompt: str) -> Dict[str, Any]:
        return self.generate_scene_image(custom_prompt, scene_idx=scene_index)

image_agent = ImageAgent()
