import os
import json
import re
import time
import subprocess
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.services.pipeline_service import pipeline_service
from app.services.replicate_service import replicate_service
from app.agents import (
    script_agent,
    design_agent,
    image_agent,
    voice_agent,
    music_agent,
    video_agent,
    director_agent
)

app = FastAPI(
    title="AI Animated Explainer Video Studio",
    description="Multi-Agent AI Studio for 1080p Explainer Video Production",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_INPUT_JSON = os.path.join(settings.STORAGE_DIR, "project_input.json")
MUSIC_DIR = os.path.join(settings.STORAGE_DIR, "music")
os.makedirs(MUSIC_DIR, exist_ok=True)

# Static mounts
app.mount("/static/outputs", StaticFiles(directory=settings.OUTPUTS_DIR), name="outputs")
app.mount("/static/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")
app.mount("/static/music", StaticFiles(directory=MUSIC_DIR), name="music")

@app.on_event("startup")
def cleanup_obsolete_files():
    """Removes deprecated files from disk on startup."""
    obsolete = [
        os.path.join(settings.BASE_DIR, "app", "services", "kling_service.py"),
        os.path.join(settings.BASE_DIR, "app", "services", "free_motion_service.py"),
        os.path.join(settings.BASE_DIR, "app", "services", "did_service.py"),
        os.path.join(settings.BASE_DIR, "app", "services", "image_gen_service.py"),
        os.path.join(settings.BASE_DIR, "app", "services", "storyboard_agent.py"),
        os.path.join(settings.PROJECT_ROOT, "frontend", "src", "components", "KlingApiKeyModal.jsx"),
        os.path.join(settings.PROJECT_ROOT, "frontend", "src", "components", "DidApiKeyModal.jsx"),
    ]
    for p in obsolete:
        try:
            if os.path.exists(p):
                os.remove(p)
                print(f"[Cleanup] Removed obsolete file: {os.path.basename(p)}")
        except Exception:
            pass

# Schemas
class ReplicateConfigPayload(BaseModel):
    api_token: str

class CloudflareConfigPayload(BaseModel):
    account_id: str
    api_token: str

class RegenerateImagePayload(BaseModel):
    scene_index: int
    image_prompt: str

class CustomVideoPayload(BaseModel):
    title: Optional[str] = ""
    introduction: Optional[str] = ""
    target_audience: Optional[str] = "Middle School (Grade 6-8)"
    voice: Optional[str] = "Reference Voice Clone (100% Match)"
    background_music: Optional[str] = "inspiring_educational"
    design_style: Optional[str] = "pixar_3d"
    target_duration: Optional[int] = 120
    scenes: Optional[List[Dict[str, Any]]] = []
    demonstration_scenes: Optional[List[Dict[str, Any]]] = None
    subtitle_font: Optional[str] = "Arial"
    subtitle_style: Optional[str] = "clean_white"

# Root
@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "AI Animated Explainer Video Studio",
        "agents": [
            "ScriptAgent",
            "DesignAgent",
            "ImageAgent",
            "VoiceAgent",
            "MusicAgent",
            "VideoAgent",
            "DirectorAgent"
        ],
        "version": "2.1.0"
    }

# Voices
@app.get("/api/v1/voices")
def get_voices():
    """Returns catalog of educator voices from VoiceAgent."""
    return voice_agent.get_available_voices()

# Reference Audio File Upload & In-Browser Audio Retrieval
@app.post("/api/v1/studio/upload-reference-audio")
async def upload_reference_audio(file: UploadFile = File(...)):
    """
    Uploads user reference voice audio (.wav, .mp3, .m4a), normalizes it to 24kHz WAV,
    and returns public audio preview URL for in-browser playback and cloning.
    """
    file_bytes = await file.read()
    filename = file.filename or "reference_voice.wav"
    result = voice_agent.save_and_normalize_reference_audio(file_bytes, filename)
    return result

# Visual Design Styles
@app.get("/api/v1/studio/design-styles")
def get_design_styles():
    """Returns available visual design styles from DesignAgent."""
    return design_agent.get_available_styles()

# Background Music
@app.get("/api/v1/studio/music-tracks")
def get_music_tracks():
    """Returns available royalty-free background music tracks from MusicAgent."""
    return music_agent.get_tracks()

# Groq AI Status (High-Speed LLM Storyboard Screenwriter)
@app.get("/api/v1/groq/status")
def get_groq_status():
    """Returns Groq LLM status for scriptwriting."""
    token = os.getenv("GROQ_API_KEY", "").strip() or getattr(settings, "GROQ_API_KEY", "").strip()
    is_conf = bool(token and token.startswith("gsk_"))
    masked = (token[:6] + "..." + token[-4:]) if len(token) > 10 else ("Configured" if is_conf else "")
    return {
        "configured": is_conf,
        "token_preview": masked,
        "model": "openai/gpt-oss-120b"
    }

# Cloudflare Workers AI Status & Configuration (10,000 Free Neurons/Day)
@app.get("/api/v1/cloudflare/status")
def get_cloudflare_status():
    """Returns whether Cloudflare Workers AI credentials are configured."""
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip() or getattr(settings, "CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip() or getattr(settings, "CLOUDFLARE_API_TOKEN", "").strip()
    is_conf = bool(account_id and api_token)
    masked_token = (api_token[:6] + "..." + api_token[-4:]) if len(api_token) > 10 else ("Configured" if is_conf else "")
    return {
        "configured": is_conf,
        "account_id_preview": (account_id[:8] + "...") if len(account_id) > 10 else account_id,
        "token_preview": masked_token,
        "model": "@cf/black-forest-labs/flux-1-schnell",
        "free_allowance": "10,000 Neurons/day (~50-70 images/day for $0)"
    }

@app.post("/api/v1/cloudflare/config")
def update_cloudflare_config(payload: CloudflareConfigPayload):
    """Saves Cloudflare Workers AI credentials into environment and .env file."""
    account_id = payload.account_id.strip()
    api_token = payload.api_token.strip()

    os.environ["CLOUDFLARE_ACCOUNT_ID"] = account_id
    os.environ["CLOUDFLARE_API_TOKEN"] = api_token
    settings.CLOUDFLARE_ACCOUNT_ID = account_id
    settings.CLOUDFLARE_API_TOKEN = api_token

    env_file = os.path.join(settings.BASE_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "CLOUDFLARE_ACCOUNT_ID=" in content:
                content = re.sub(r'CLOUDFLARE_ACCOUNT_ID=.*', f'CLOUDFLARE_ACCOUNT_ID={account_id}', content)
            else:
                content += f"\nCLOUDFLARE_ACCOUNT_ID={account_id}\n"
            if "CLOUDFLARE_API_TOKEN=" in content:
                content = re.sub(r'CLOUDFLARE_API_TOKEN=.*', f'CLOUDFLARE_API_TOKEN={api_token}', content)
            else:
                content += f"CLOUDFLARE_API_TOKEN={api_token}\n"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    return {
        "status": "success",
        "configured": bool(account_id and api_token),
        "message": "Cloudflare Workers AI credentials updated successfully."
    }

# Replicate Status & Configuration
@app.get("/api/v1/replicate/status")
def get_replicate_status():
    """Returns whether Replicate credentials are configured."""
    is_conf = replicate_service.is_configured()
    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    masked = (token[:6] + "..." + token[-4:]) if len(token) > 10 else ("Configured" if is_conf else "")
    return {
        "configured": is_conf,
        "token_preview": masked
    }

@app.post("/api/v1/replicate/config")
def update_replicate_config(payload: ReplicateConfigPayload):
    """Saves Replicate API token into environment and .env file."""
    env_file = os.path.join(settings.BASE_DIR, ".env")
    env_content = ""
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                env_content = f.read()
        except Exception:
            pass

    t = payload.api_token.strip()
    if "..." not in t and "***" not in t and t.startswith("r8_"):
        os.environ["REPLICATE_API_TOKEN"] = t
        replicate_service.api_token = t
        if "REPLICATE_API_TOKEN=" in env_content:
            env_content = re.sub(r'REPLICATE_API_TOKEN=.*', f'REPLICATE_API_TOKEN={t}', env_content)
        else:
            env_content += f"\nREPLICATE_API_TOKEN={t}\n"

        if env_content and os.path.exists(env_file):
            try:
                with open(env_file, "w", encoding="utf-8") as f:
                    f.write(env_content)
            except Exception as e:
                print(f"Error persisting .env: {e}")

    return {"status": "ok", "configured": replicate_service.is_configured()}

# Studio Endpoints: Autonomous Creation via DirectorAgent
@app.post("/api/v1/studio/create-storyboard")
async def create_storyboard(
    input_mode: str = Form("prompt"),
    topic_prompt: Optional[str] = Form(None),
    script_text: Optional[str] = Form(None),
    live_url: Optional[str] = Form(None),
    chapter_topic: Optional[str] = Form(None),
    target_audience: Optional[str] = Form("Middle School (Grade 6-8)"),
    design_style: Optional[str] = Form("pixar_3d"),
    custom_character: Optional[str] = Form(None),
    custom_environment: Optional[str] = Form(None),
    custom_design_prompt: Optional[str] = Form(None),
    voice: Optional[str] = Form("Reference Voice Clone (100% Match)"),
    background_music: Optional[str] = Form("inspiring_educational"),
    target_duration: int = Form(120),
    generate_images: bool = Form(False),
    file: Optional[UploadFile] = File(None)
):
    """
    Autonomous Multi-Agent Creation:
    Orchestrated by DirectorAgent delegating to ScriptAgent, DesignAgent, and ImageAgent.
    Calibrates scene segmentation, narration pacing, and visual prompts to target_duration (2-5 mins).
    Supports PDF, DOCX, XLSX, CSV, live Google Docs, and live Google Sheets.
    """
    file_bytes = None
    filename = None
    if input_mode == "document" and file:
        file_bytes = await file.read()
        filename = file.filename

    try:
        project_config = director_agent.create_autonomous_storyboard(
            input_mode=input_mode,
            topic_prompt=topic_prompt,
            script_text=script_text,
            file_bytes=file_bytes,
            filename=filename,
            live_url=live_url,
            chapter_topic=chapter_topic,
            target_audience=target_audience,
            design_style=design_style or "pixar_3d",
            custom_character=custom_character,
            custom_environment=custom_environment,
            custom_design_prompt=custom_design_prompt,
            voice=voice or "Reference Voice Clone (100% Match)",
            background_music=background_music or "inspiring_educational",
            target_duration=target_duration,
            generate_images=generate_images
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storyboard generation failed: {e}")

    return {
        "status": "success",
        **project_config
    }

@app.post("/api/v1/studio/regenerate-image")
def regenerate_scene_image_endpoint(payload: RegenerateImagePayload):
    """Regenerates AI visual for a single scene via ImageAgent."""
    try:
        img_res = director_agent.regenerate_scene_visual(
            scene_index=payload.scene_index,
            custom_prompt=payload.image_prompt
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image regeneration failed: {e}")

    return {
        "status": "regenerated",
        "scene_index": payload.scene_index,
        "image_path": img_res["local_path"],
        "preview_url": img_res["preview_url"],
        "provider": img_res["provider"],
        "image_history": img_res.get("image_history", [])
    }

def _ensure_scene_history(scene_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = scene_dict.get("image_history")
    if history and isinstance(history, list) and len(history) > 0:
        return history
    cur_url = scene_dict.get("preview_url")
    if cur_url:
        return [{
            "preview_url": cur_url,
            "image_path": scene_dict.get("image_path") or "",
            "image_prompt": scene_dict.get("image_prompt") or "",
            "label": "Version 1",
            "timestamp": time.time()
        }]
    return []

# Storyboard Config Persistence
@app.get("/api/v1/custom/config")
def get_custom_config():
    """Loads current storyboard project input."""
    if os.path.exists(PROJECT_INPUT_JSON):
        try:
            with open(PROJECT_INPUT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "scenes" not in data and "demonstration_scenes" in data:
                    data["scenes"] = data["demonstration_scenes"]
                if "background_music" not in data:
                    data["background_music"] = "inspiring_educational"
                if "design_style" not in data:
                    data["design_style"] = "pixar_3d"
                if "subtitle_font" not in data:
                    data["subtitle_font"] = "Arial"
                if "subtitle_style" not in data:
                    data["subtitle_style"] = "clean_white"

                # Ensure image_history is strictly scoped to this storyboard project
                for idx, s in enumerate(data.get("scenes", [])):
                    s["image_history"] = _ensure_scene_history(s)

                return data
        except Exception:
            pass

    return {
        "title": "New Video Project",
        "voice": "Reference Voice Clone (100% Match)",
        "background_music": "inspiring_educational",
        "design_style": "pixar_3d",
        "subtitle_font": "Arial",
        "subtitle_style": "clean_white",
        "scenes": []
    }

@app.post("/api/v1/custom/config")
def save_custom_config(payload: CustomVideoPayload):
    """Saves updated project input to storage."""
    data = payload.model_dump()
    os.makedirs(os.path.dirname(PROJECT_INPUT_JSON), exist_ok=True)
    with open(PROJECT_INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"status": "saved", "config": data}

@app.post("/api/v1/custom/upload-image")
async def upload_custom_image(file: UploadFile = File(...)):
    """Uploads an image directly from browser into backend/storage/uploads/."""
    filename = file.filename or "image.jpg"
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    save_path = os.path.join(settings.UPLOADS_DIR, safe_name)
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "status": "uploaded",
        "filename": safe_name,
        "local_path": save_path,
        "preview_url": f"/static/uploads/{safe_name}"
    }

@app.post("/api/v1/custom/generate")
@app.post("/api/v1/custom/render")
def start_custom_video_generation(payload: CustomVideoPayload, background_tasks: BackgroundTasks):
    """Triggers custom storyboard video generation (supports both /generate and /render)."""
    config_dict = payload.model_dump()
    job_id = pipeline_service.create_custom_job(config_dict)
    background_tasks.add_task(pipeline_service.run_custom_pipeline, job_id)
    scene_cnt = len(payload.scenes or payload.demonstration_scenes or [])
    return {
        "job_id": job_id,
        "status": "QUEUED",
        "message": f"Custom video job with {scene_cnt} scenes queued successfully.",
        "check_status_url": f"/api/v1/videos/status/{job_id}"
    }

@app.get("/api/v1/videos/status/{job_id}")
def check_job_status(job_id: str):
    """Polls live progress of generation job."""
    job = pipeline_service.get_job(job_id)
    if not job:
        out_filename = f"video_{job_id}.mp4"
        final_out_path = os.path.join(settings.OUTPUTS_DIR, out_filename)
        if os.path.exists(final_out_path):
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "progress_pct": 100,
                "step_message": "Video complete! Produced with multi-agent orchestration, ducked music & synced subtitles.",
                "output_path": final_out_path,
                "output_filename": out_filename,
                "download_url": f"/api/v1/videos/download/{out_filename}",
                "error": None
            }
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/v1/videos/download/{filename}")
def download_video(filename: str):
    """Streams or downloads rendered MP4 file."""
    file_path = os.path.join(settings.OUTPUTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)
