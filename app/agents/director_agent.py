import os
import time
import json
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.agents.script_agent import script_agent
from app.agents.design_agent import design_agent
from app.agents.image_agent import image_agent
from app.agents.voice_agent import voice_agent
from app.agents.music_agent import music_agent
from app.agents.video_agent import video_agent

PROJECT_INPUT_JSON = os.path.join(settings.STORAGE_DIR, "project_input.json")

class DirectorAgent:
    """
    Master Production Director Agent:
    Orchestrates the entire AI video generation pipeline by delegating tasks to:
      1. ScriptAgent   -> Ingests PDF/Script/Prompt, segments scenes & narration
      2. DesignAgent   -> Applies visual art styles, character design, environment
      3. ImageAgent    -> Renders 16:9 images using FLUX cloud/fallback
      4. VoiceAgent    -> Manages reference audio uploads, cloning, and Edge-TTS synthesis
      5. MusicAgent    -> Curates ambient music and applies audio ducking
      6. VideoAgent    -> Handles character facial animation, camera motion, and 1080p assembly
    """

    def create_autonomous_storyboard(
        self,
        input_mode: str,
        topic_prompt: Optional[str] = None,
        script_text: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        live_url: Optional[str] = None,
        chapter_topic: Optional[str] = None,
        target_audience: Optional[str] = None,
        design_style: str = "cinematic_realistic",
        custom_character: Optional[str] = None,
        custom_environment: Optional[str] = None,
        custom_design_prompt: Optional[str] = None,
        voice: str = "Reference Voice Clone (100% Match)",
        background_music: str = "inspiring_educational",
        target_duration: int = 120,
        generate_images: bool = False
    ) -> Dict[str, Any]:
        """
        Stage 1: Autonomous creation flow up to the interactive approval board.
        Paces and calculates scenes according to target_duration.
        Supports textbook chapter extraction and target educational audience.
        """
        print(f"[DirectorAgent] Starting creation with style='{design_style}', target_duration={target_duration}s, audience='{target_audience}'...")

        # 1. Script Agent handles text/document processing calibrated to target_duration
        script_output = script_agent.process_input(
            input_mode=input_mode,
            topic_prompt=topic_prompt,
            script_text=script_text,
            file_bytes=file_bytes,
            filename=filename,
            live_url=live_url,
            chapter_topic=chapter_topic,
            target_audience=target_audience,
            target_duration=target_duration
        )
        raw_scenes = script_output["scenes"]
        project_title = script_output["title"]
        introduction = script_output.get("introduction", "")
        est_total = script_output.get("estimated_total_duration", target_duration)

        # 2. Design Agent infuses visual art direction and character prompts
        designed_scenes = design_agent.design_scenes(
            scenes=raw_scenes,
            style_id=design_style or "cinematic_realistic",
            custom_character=custom_character,
            custom_environment=custom_environment,
            custom_design_prompt=custom_design_prompt
        )

        # Preserve estimated_duration, concept_summary, source_reference
        for idx, ds in enumerate(designed_scenes):
            if idx < len(raw_scenes):
                if "estimated_duration" in raw_scenes[idx]:
                    ds["estimated_duration"] = raw_scenes[idx]["estimated_duration"]
                if "concept_summary" in raw_scenes[idx]:
                    ds["concept_summary"] = raw_scenes[idx]["concept_summary"]
                if "source_reference" in raw_scenes[idx]:
                    ds["source_reference"] = raw_scenes[idx]["source_reference"]

        # 3. Image Agent renders 16:9 visuals (only if generate_images is requested)
        if generate_images:
            scenes_with_images = image_agent.generate_storyboard_images(designed_scenes)
            for s in scenes_with_images:
                if s.get("preview_url"):
                    s["image_history"] = [{
                        "preview_url": s["preview_url"],
                        "image_path": s.get("image_path", ""),
                        "image_prompt": s.get("image_prompt", ""),
                        "label": "Version 1",
                        "timestamp": time.time()
                    }]
        else:
            scenes_with_images = designed_scenes
            for s in scenes_with_images:
                s["preview_url"] = None
                s["image_path"] = ""
                s["image_history"] = []

        # 4. Save to project_input.json for persistent state
        project_config = {
            "title": project_title,
            "introduction": introduction,
            "target_duration": target_duration,
            "target_audience": target_audience or "Middle School (Grade 6-8)",
            "estimated_total_duration": est_total,
            "voice": voice,
            "background_music": background_music,
            "design_style": design_style,
            "subtitle_font": "Arial",
            "subtitle_style": "clean_white",
            "custom_character": custom_character or "",
            "custom_environment": custom_environment or "",
            "scenes": scenes_with_images
        }
        try:
            with open(PROJECT_INPUT_JSON, "w", encoding="utf-8") as f:
                json.dump(project_config, f, indent=2)
        except Exception as e:
            print(f"[DirectorAgent] Error persisting project_input.json: {e}")

        return project_config

    def regenerate_scene_visual(self, scene_index: int, custom_prompt: str) -> Dict[str, Any]:
        """Delegates image regeneration to ImageAgent with prompt clarification."""
        clarified_prompt = design_agent._disambiguate_and_clarify_visual(custom_prompt)
        img_res = image_agent.regenerate_scene_image(scene_index, clarified_prompt)

        # Update in project_input.json
        image_history = []
        if os.path.exists(PROJECT_INPUT_JSON):
            try:
                with open(PROJECT_INPUT_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for s in data.get("scenes", []):
                    if s.get("scene_number") == scene_index:
                        # Initialize or read history
                        if "image_history" not in s or not isinstance(s["image_history"], list):
                            s["image_history"] = []
                        # Ensure current image is in history before changing
                        if s.get("preview_url") and not any(h.get("preview_url") == s.get("preview_url") for h in s["image_history"]):
                            s["image_history"].append({
                                "preview_url": s["preview_url"],
                                "image_path": s.get("image_path", ""),
                                "image_prompt": s.get("image_prompt", ""),
                                "label": f"Version {len(s['image_history']) + 1}",
                                "timestamp": time.time()
                            })
                        # Add newly regenerated version
                        new_item = {
                            "preview_url": img_res["preview_url"],
                            "image_path": img_res["local_path"],
                            "image_prompt": clarified_prompt,
                            "label": f"Version {len(s['image_history']) + 1}",
                            "timestamp": time.time()
                        }
                        s["image_history"].append(new_item)
                        image_history = s["image_history"]
                        s["image_path"] = img_res["local_path"]
                        s["preview_url"] = img_res["preview_url"]
                        s["image_prompt"] = clarified_prompt
                        s["image_provider"] = img_res["provider"]
                        s["image_error"] = None
                with open(PROJECT_INPUT_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[DirectorAgent] Error updating project_input.json: {e}")

        img_res["image_history"] = image_history
        return img_res

director_agent = DirectorAgent()
