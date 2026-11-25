import os
import re
import subprocess
from typing import List, Optional
import imageio_ffmpeg

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

class VideoService:
    @classmethod
    def create_scene_srt(cls, narration: str, total_duration: float, output_srt_path: str) -> str:
        """
        Splits the spoken narration into sentences and maps them across the total duration
        proportional to word count, ensuring the subtitle on screen exactly matches the words being spoken.
        """
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', narration) if s.strip()]
        if not sentences:
            sentences = [narration.strip()] if narration.strip() else [""]

        word_counts = [len(s.split()) for s in sentences]
        total_words = sum(word_counts)
        if total_words == 0:
            total_words = 1
            word_counts = [1]

        def format_time(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int(round((seconds - int(seconds)) * 1000))
            if millis >= 1000:
                millis = 999
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        srt_blocks = []
        cur_t = 0.0
        for i, (sent, wc) in enumerate(zip(sentences, word_counts)):
            seg_dur = (wc / total_words) * total_duration
            t_start = cur_t
            t_end = min(cur_t + seg_dur, total_duration)
            cur_t += seg_dur

            srt_blocks.append(f"{i + 1}\n{format_time(t_start)} --> {format_time(t_end)}\n{sent}\n")

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_blocks))

        return output_srt_path

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """Extracts the exact duration of an audio file in seconds."""
        try:
            cmd = [FFMPEG_BIN, "-i", audio_path]
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if match:
                h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
                return h * 3600 + m * 60 + s
        except Exception:
            pass
        return 5.0

    @classmethod
    def _get_subtitle_style_filter(cls, srt_filter_arg: str, font: str = "Arial", style: str = "clean_white") -> str:
        """
        Builds the FFmpeg subtitle filter with user-chosen typography and clean, shadow-free presentation.
        Completely eliminates dark background boxes and harsh drop shadows.
        """
        font_name = font.strip() if font and font.strip() else "Arial"
        style_key = (style or "clean_white").lower().strip()

        if style_key in ["disabled", "none", "off"]:
            return ""

        if style_key == "cinema_yellow":
            # Movie classic yellow, zero background box, zero drop shadow
            return (
                f",subtitles='{srt_filter_arg}':force_style="
                f"'FontName={font_name},FontSize=16,Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H90000000,"
                f"BackColour=&H00000000,BorderStyle=1,Outline=1.2,Shadow=0,MarginV=35,Alignment=2'"
            )
        else:
            # Default Clean Crisp White: zero background box, zero drop shadow, thin crisp outline for contrast
            return (
                f",subtitles='{srt_filter_arg}':force_style="
                f"'FontName={font_name},FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,"
                f"BackColour=&H00000000,BorderStyle=1,Outline=1.2,Shadow=0,MarginV=35,Alignment=2'"
            )

    @classmethod
    def render_motion_clip(
        cls,
        video_source_path: str,
        audio_path: str,
        subtitle_text: str,
        output_clip_path: str,
        header_title: Optional[str] = None,
        narration: Optional[str] = None,
        speaker_name: Optional[str] = None,
        width: int = 1920,
        height: int = 1080,
        subtitle_font: str = "Arial",
        subtitle_style: str = "clean_white"
    ) -> str:
        """
        Renders an animated moving 1080p video clip synchronized with audio narration
        and clean shadow-free subtitles in user's chosen font.
        """
        os.makedirs(os.path.dirname(output_clip_path), exist_ok=True)
        dur = cls.get_audio_duration(audio_path)
        speech_text = narration.strip() if (narration and narration.strip()) else subtitle_text.strip()
        srt_path = output_clip_path + ".srt"
        cls.create_scene_srt(speech_text, dur, srt_path)

        srt_filter_arg = srt_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = cls._get_subtitle_style_filter(srt_filter_arg, font=subtitle_font, style=subtitle_style)

        drawtext_filter = ""
        if speaker_name and speaker_name.strip():
            safe_text = speaker_name.strip().replace('\\', '\\\\').replace("'", "’").replace(':', '\\:').replace('%', '％')
            badge_end = min(dur, 6.0)
            drawtext_filter = f",drawtext=text='{safe_text}':fontsize=28:fontcolor=white:box=1:boxcolor=0x0f172a@0.85:boxborderw=14:x=60:y=60:enable='between(t,0.6,{badge_end})'"

        if os.path.exists(video_source_path):
            filter_complex = (
                f"[0:v]scale={width}:{height},setsar=1,fps=30"
                f"{sub_filter}"
                f"{drawtext_filter}[v]"
            )
            cmd = [
                FFMPEG_BIN, "-y",
                "-stream_loop", "-1", "-i", video_source_path,
                "-i", audio_path,
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "1:a",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p",
                output_clip_path
            ]
        else:
            filter_complex = (
                f"[0:v]scale={width}:{height},setsar=1"
                f"{sub_filter}"
                f"{drawtext_filter}[v]"
            )
            cmd = [
                FFMPEG_BIN, "-y",
                "-f", "lavfi", "-i", f"color=c=0x0f172a:s={width}x{height}:r=30",
                "-i", audio_path,
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "1:a",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p",
                output_clip_path
            ]

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(srt_path):
            os.remove(srt_path)

        return output_clip_path

    @classmethod
    def render_image_audio_clip(
        cls,
        image_path: str,
        audio_path: str,
        subtitle_text: str,
        output_clip_path: str,
        narration: Optional[str] = None,
        speaker_name: Optional[str] = None,
        motion_style: str = "auto",
        scene_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        subtitle_font: str = "Arial",
        subtitle_style: str = "clean_white"
    ) -> str:
        """
        Renders a cinematic 1080p video clip from a slide image with dynamic camera motion
        (Ken Burns zoom-in, pull-back, pan) and speech-synchronized burned subtitles (zero shadow, custom font).
        """
        os.makedirs(os.path.dirname(output_clip_path), exist_ok=True)
        dur = cls.get_audio_duration(audio_path)
        fps = 30
        d_frames = max(30, int(dur * fps))

        speech_text = narration.strip() if (narration and narration.strip()) else subtitle_text.strip()
        srt_path = output_clip_path + ".srt"
        cls.create_scene_srt(speech_text, dur, srt_path)
        srt_filter_arg = srt_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = cls._get_subtitle_style_filter(srt_filter_arg, font=subtitle_font, style=subtitle_style)

        # Resolve motion style
        resolved_style = motion_style.lower() if motion_style else "auto"
        if resolved_style == "auto":
            auto_sequence = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
            resolved_style = auto_sequence[scene_index % len(auto_sequence)]

        # Define dynamic motion expressions for zoompan
        if resolved_style in ["zoom_in", "push_in"]:
            z_expr = "min(zoom+0.0006,1.18)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
            has_motion = True
        elif resolved_style in ["zoom_out", "pull_back"]:
            z_expr = "if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0006))"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
            has_motion = True
        elif resolved_style in ["pan_right", "dolly_right"]:
            z_expr = "1.12"
            x_expr = "min(iw-iw/zoom,on*0.6)"
            y_expr = "ih/2-(ih/zoom/2)"
            has_motion = True
        elif resolved_style in ["pan_left", "dolly_left"]:
            z_expr = "1.12"
            x_expr = "max(0,(iw-iw/zoom)-on*0.6)"
            y_expr = "ih/2-(ih/zoom/2)"
            has_motion = True
        else:
            has_motion = False

        drawtext_filter = ""
        if speaker_name and speaker_name.strip():
            safe_text = speaker_name.strip().replace('\\', '\\\\').replace("'", "’").replace(':', '\\:').replace('%', '％')
            badge_end = min(dur, 6.0)
            drawtext_filter = f",drawtext=text='{safe_text}':fontsize=28:fontcolor=white:box=1:boxcolor=0x0f172a@0.85:boxborderw=14:x=60:y=60:enable='between(t,0.6,{badge_end})'"

        if has_motion:
            filter_complex = (
                f"[0:v]scale=2560:1440,setsar=1,"
                f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={d_frames}:s={width}x{height}:fps={fps}"
                f"{sub_filter}"
                f"{drawtext_filter}[v]"
            )
            cmd = [
                FFMPEG_BIN, "-y",
                "-loop", "1", "-i", image_path,
                "-i", audio_path,
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "1:a",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p",
                output_clip_path
            ]
        else:
            # Static fallback with centered aspect framing
            filter_complex = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
                f"{sub_filter}"
                f"{drawtext_filter}[v]"
            )
            cmd = [
                FFMPEG_BIN, "-y",
                "-loop", "1", "-i", image_path,
                "-i", audio_path,
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "1:a",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p",
                output_clip_path
            ]

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(srt_path):
            os.remove(srt_path)

        return output_clip_path

    @classmethod
    def assemble_full_video(cls, clip_paths: List[str], output_path: str) -> str:
        """
        Concatenates all scene clips into a finalized 1080p Full HD MP4 video.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        input_args = []
        filter_inputs_v = []
        filter_inputs_a = []

        for i, clip in enumerate(clip_paths):
            input_args.extend(["-i", clip])
            filter_inputs_v.append(f"[{i}:v]scale=1920:1080,setsar=1,fps=30[v{i}]")
            filter_inputs_a.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")

        n = len(clip_paths)
        # Interleave video and audio streams: [v0][a0][v1][a1]... for FFmpeg concat filter
        concat_interleaved = "".join([f"[v{i}][a{i}]" for i in range(n)])
        concat_filter = f"{concat_interleaved}concat=n={n}:v=1:a=1[outv][outa]"

        full_filter = ";".join(filter_inputs_v + filter_inputs_a + [concat_filter])

        cmd = [
            FFMPEG_BIN, "-y",
            *input_args,
            "-filter_complex", full_filter,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path

video_service = VideoService()
