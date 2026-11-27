import os
from typing import List, Dict, Any, Optional
from app.services.video_service import video_service
from app.services.replicate_service import replicate_service

class VideoAgent:
    """
    Dedicated Video Animation & Assembly Agent:
    - Renders lifelike character animations with facial expressions via Replicate LTX-Video.
    - Applies smooth 1080p cinematic camera movements (Ken Burns) when camera motion is selected.
    - Burns sentence-timed subtitles with precise styling.
    - Concatenates scene clips into the finalized 1080p Full HD MP4.
    """

    def animate_or_motion_clip(
        self,
        image_path: str,
        audio_path: str,
        motion_prompt: str,
        motion_style: str,
        subtitle_text: str,
        narration: str,
        output_clip_path: str,
        scene_title: str,
        scene_index: int = 0,
        speaker_name: Optional[str] = None,
        subtitle_font: str = "Arial",
        subtitle_style: str = "clean_white"
    ) -> Dict[str, Any]:
        """
        Produces an individual animated 1080p video clip synchronized with audio narration and subtitles.
        """
        dur = video_service.get_audio_duration(audio_path)
        animation_clip = None
        method_used = "camera_motion"

        # 1. Try Replicate LTX-Video if configured
        if image_path and motion_prompt and replicate_service.is_configured():
            try:
                replicate_clip = replicate_service.animate_character(
                    image_path=image_path,
                    motion_prompt=motion_prompt,
                    audio_path=audio_path,
                    duration_sec=int(dur)
                )
                if replicate_clip and os.path.exists(replicate_clip):
                    animation_clip = replicate_clip
                    method_used = "replicate_facial_animation"
            except Exception as e:
                print(f"[VideoAgent] Replicate animation notice on scene {scene_index + 1}: {e}")
                animation_clip = None

        # 3. Render final clip
        if animation_clip and os.path.exists(animation_clip):
            video_service.render_motion_clip(
                video_source_path=animation_clip,
                audio_path=audio_path,
                subtitle_text=subtitle_text,
                output_clip_path=output_clip_path,
                header_title=scene_title,
                narration=narration,
                speaker_name=speaker_name,
                subtitle_font=subtitle_font,
                subtitle_style=subtitle_style
            )
        elif image_path and os.path.exists(image_path):
            video_service.render_image_audio_clip(
                image_path=image_path,
                audio_path=audio_path,
                subtitle_text=subtitle_text,
                output_clip_path=output_clip_path,
                narration=narration,
                speaker_name=speaker_name,
                motion_style=motion_style or "zoom_in",
                scene_index=scene_index,
                subtitle_font=subtitle_font,
                subtitle_style=subtitle_style
            )
        else:
            raise ValueError(f"Scene {scene_index + 1} image is missing or invalid ({image_path}). A dedicated image is required to render the video.")

        return {
            "clip_path": output_clip_path,
            "method": method_used,
            "duration": dur
        }

    def assemble_full_video(self, clip_paths: List[str], output_path: str) -> str:
        """Assembles all scene clips into a single 1080p MP4."""
        return video_service.assemble_full_video(clip_paths, output_path)

video_agent = VideoAgent()
