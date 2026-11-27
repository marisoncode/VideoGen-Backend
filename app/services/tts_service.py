import os
import re
import socket
import asyncio
import subprocess
from typing import Dict, List, Optional
import imageio_ffmpeg
import edge_tts
from app.core.config import settings

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

AVAILABLE_VOICES = [
    {
        "id": "cloned-reference-voice",
        "name": "Reference Voice Clone (100% Match)",
        "gender": "Female",
        "locale": "en-IN (Cloned)"
    },
    {
        "id": "en-IN-NeerjaNeural",
        "name": "Neerja (Warm Indian English Female)",
        "gender": "Female",
        "locale": "en-IN"
    },
    {
        "id": "en-IN-PrabhatNeural",
        "name": "Prabhat (Articulate Indian English Male)",
        "gender": "Male",
        "locale": "en-IN"
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Warm & Natural Storyteller Female)",
        "gender": "Female",
        "locale": "en-US"
    },
    {
        "id": "en-US-AvaNeural",
        "name": "Ava (Studio Conversational Female)",
        "gender": "Female",
        "locale": "en-US"
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy (Clear Educational Male)",
        "gender": "Male",
        "locale": "en-US"
    },
    {
        "id": "en-GB-RyanNeural",
        "name": "Ryan (Expressive British Male)",
        "gender": "Male",
        "locale": "en-GB"
    },
    {
        "id": "en-US-ChristopherNeural",
        "name": "Christopher (Deep Story Narrator Male)",
        "gender": "Male",
        "locale": "en-US"
    },
    {
        "id": "en-US-AnaNeural",
        "name": "Ana (Young Child / Kid Character)",
        "gender": "Female",
        "locale": "en-US"
    }
]

MALE_CHARACTER_VOICES = [
    "en-US-GuyNeural",
    "en-IN-PrabhatNeural",
    "en-GB-RyanNeural",
    "en-US-ChristopherNeural",
]

FEMALE_CHARACTER_VOICES = [
    "en-US-JennyNeural",
    "en-IN-NeerjaNeural",
    "en-US-AvaNeural",
    "en-US-AnaNeural",
]

def is_online() -> bool:
    """Check connectivity without relying on UDP port 53 (which many routers block)."""
    # Try connecting to standard HTTP/HTTPS endpoints
    for host in [("edge.microsoft.com", 443), ("1.1.1.1", 443), ("8.8.8.8", 53)]:
        try:
            s = socket.create_connection(host, timeout=0.8)
            s.close()
            return True
        except Exception:
            continue
    return False

class TTSService:
    @staticmethod
    def get_available_voices() -> List[Dict[str, str]]:
        return AVAILABLE_VOICES

    @classmethod
    def _generate_cloned_voice(cls, text: str, output_path: str, ref_audio_path: Optional[str] = None) -> Optional[str]:
        """
        Zero-Shot Voice Cloning using any clean audio sample (uploaded or default)
        via cloud F5-TTS / E2-TTS.
        """
        if not ref_audio_path or not os.path.exists(ref_audio_path):
            ref_audio_path = os.path.join(settings.TEMP_DIR, "ref_voice_clean.wav")

        if not os.path.exists(ref_audio_path):
            return None

        try:
            from gradio_client import Client, handle_file
            client = Client("mrfakename/E2-F5-TTS")
            ref_text = "Hi welcome, today we are going to show you three wonderful sensory activities to engage with your baby."
            res = client.predict(
                ref_audio=handle_file(ref_audio_path),
                ref_text=ref_text,
                gen_text=text,
                remove_silence=False,
                api_name="/predict"
            )
            audio_file = res[0] if isinstance(res, (tuple, list)) else res
            if audio_file and os.path.exists(audio_file):
                conv_cmd = [
                    FFMPEG_BIN, "-y", "-i", audio_file,
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                    output_path
                ]
                subprocess.run(conv_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    return output_path
        except Exception as e:
            print(f"[Cloned Voice Notice] Cloud voice cloning attempt: {e}. Falling back to Neerja Neural.")
            return None
        return None

    @classmethod
    async def _generate_edge_tts(cls, text: str, output_path: str, voice: str):
        communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
        await asyncio.wait_for(communicate.save(output_path), timeout=6.0)

    @classmethod
    def generate_speech(cls, text: str, output_path: str, voice: str = "cloned-reference-voice") -> str:
        """
        Generates brand-new audible voice narration matching the reference video:
        - Primary: Cloned Reference Voice via free F5-TTS or Microsoft Edge Neural TTS.
        - Fallback: Windows SpeechSynthesizer or audio generator if offline.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        clean_text = text.strip()
        if not clean_text:
            # Generate 3 seconds of silence for scenes with no spoken words
            cmd = [
                FFMPEG_BIN, "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "3.0",
                "-c:a", "libmp3lame", "-b:a", "192k",
                output_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_path

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

        # 1. Primary Option: Zero-Shot Voice Clone (custom uploaded audio or default reference voice)
        is_clone_target = (
            voice in ["cloned-reference-voice", "Reference Voice Clone (100% Match)"]
            or voice.startswith("custom_voice:")
            or (isinstance(voice, str) and os.path.exists(voice) and voice.lower().endswith(('.wav', '.mp3', '.m4a')))
        )
        if is_clone_target and is_online():
            ref_file = None
            if voice.startswith("custom_voice:"):
                ref_file = voice.split("custom_voice:", 1)[1].strip()
            elif os.path.exists(voice):
                ref_file = voice

            cloned = cls._generate_cloned_voice(clean_text, output_path, ref_audio_path=ref_file)
            if cloned and os.path.exists(output_path):
                return cloned
            voice = "en-IN-NeerjaNeural"

        # 2. Microsoft Edge Neural TTS
        if is_online():
            try:
                asyncio.run(cls._generate_edge_tts(clean_text, output_path, voice))
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    return output_path
            except Exception as e:
                if voice != "en-US-JennyNeural":
                    try:
                        asyncio.run(cls._generate_edge_tts(clean_text, output_path, "en-US-JennyNeural"))
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                            return output_path
                    except Exception:
                        pass
                print(f"[TTS Notice] Edge-TTS API attempt: {e}. Switching to local synthesizer.")

        # 2. Local Fallback: Windows SpeechSynthesizer (Always speaks text aloud)
        temp_wav = output_path + ".wav"
        sanitized_script = clean_text.replace("'", "").replace('"', '').replace('\n', ' ')
        ps_code = f"""
Add-Type -AssemblyName System.Speech;
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$synth.SetOutputToWaveFile('{temp_wav}');
$synth.Speak('{sanitized_script}');
$synth.Dispose();
"""
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, timeout=8)
            if os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 1000:
                conv_cmd = [
                    FFMPEG_BIN, "-y", "-i", temp_wav,
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                    output_path
                ]
                subprocess.run(conv_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    return output_path
        except Exception:
            pass

        # 3. Failsafe audio generation if SAPI unavailable
        words = len(clean_text.split())
        est_duration = max(3.5, round(words / 2.3, 1))
        cmd = [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(est_duration),
            "-c:a", "libmp3lame", "-b:a", "192k",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path

    @classmethod
    def _resolve_character_voice(
        cls,
        speaker: str,
        default_voice: str,
        speaker_voice_map: Dict[str, str]
    ) -> str:
        """Assigns a consistent, distinct free Edge-TTS voice to each named character."""
        key = speaker.strip().lower()
        if key in speaker_voice_map:
            return speaker_voice_map[key]

        # Narrator / Host uses the project's default voice (fallback to Jenny/Christopher if cloned)
        if any(w in key for w in ["narrator", "storyteller", "host", "maya", "presenter"]):
            resolved = default_voice
            if resolved in ["cloned-reference-voice", "Reference Voice Clone (100% Match)"] or resolved.startswith("custom_voice:"):
                resolved = "en-IN-NeerjaNeural" if "maya" in key else "en-US-JennyNeural"
            speaker_voice_map[key] = resolved
            return resolved

        used = set(speaker_voice_map.values())
        is_female = any(w in key for w in ["girl", "woman", "mother", "mom", "sister", "aunt", "queen", "princess", "grandma", "dadi", "priya", "ananya", "sita", "emma", "maya"])
        is_child = any(w in key for w in ["child", "kid", "baby", "little"])

        if is_child and "en-US-AnaNeural" not in used:
            speaker_voice_map[key] = "en-US-AnaNeural"
            return "en-US-AnaNeural"

        pool = FEMALE_CHARACTER_VOICES if is_female else MALE_CHARACTER_VOICES
        for v in pool:
            if v not in used:
                speaker_voice_map[key] = v
                return v

        # Secondary pool if primary pool exhausted
        all_pool = MALE_CHARACTER_VOICES + FEMALE_CHARACTER_VOICES
        for v in all_pool:
            if v not in used:
                speaker_voice_map[key] = v
                return v

        chosen = pool[len(speaker_voice_map) % len(pool)]
        speaker_voice_map[key] = chosen
        return chosen

    @classmethod
    def generate_multi_speaker_speech(
        cls,
        text: str,
        output_path: str,
        default_voice: str = "en-US-JennyNeural",
        speaker_voice_map: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Parses 'Speaker: Dialogue' lines and synthesizes each character with a distinct
        free Edge Neural TTS voice, stitching turns together seamlessly via FFmpeg.
        Falls back to standard single-voice generate_speech if no speaker tags exist.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return cls.generate_speech("", output_path, voice=default_voice)

        # Split lines or inline 'Speaker: ...' turns
        line_pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 _\-\.]{0,24}?)\s*:\s*(.+)$')
        raw_lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]

        turns = []
        for ln in raw_lines:
            m = line_pattern.match(ln)
            if m:
                spk, dlg = m.group(1).strip(), m.group(2).strip()
                # Avoid treating URLs or timestamps (e.g. "http:", "10:") as speakers
                if spk.lower() not in ["http", "https", "note", "tip"] and dlg:
                    turns.append((spk, dlg))
            elif turns:
                # Continuation of previous speaker's line
                prev_spk, prev_dlg = turns[-1]
                turns[-1] = (prev_spk, f"{prev_dlg} {ln}")

        # If fewer than 1 tagged speaker turn, use standard single-voice synthesis
        if not turns:
            return cls.generate_speech(clean_text, output_path, voice=default_voice)

        if speaker_voice_map is None:
            speaker_voice_map = {}

        # Single tagged turn (just strip the 'Speaker:' prefix so TTS doesn't read it)
        if len(turns) == 1:
            spk, dlg = turns[0]
            v = cls._resolve_character_voice(spk, default_voice, speaker_voice_map)
            return cls.generate_speech(dlg, output_path, voice=v)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        seg_dir = os.path.dirname(output_path)
        seg_files = []
        pause_file = os.path.join(seg_dir, f"_pause_{os.path.basename(output_path)}.mp3")

        try:
            # Create a crisp 0.25s silence pause between character turns
            subprocess.run([
                FFMPEG_BIN, "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "0.25",
                "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                pause_file
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            for idx, (spk, dlg) in enumerate(turns):
                v = cls._resolve_character_voice(spk, default_voice, speaker_voice_map)
                seg_path = os.path.join(seg_dir, f"_seg_{idx}_{os.path.basename(output_path)}")
                cls.generate_speech(dlg, seg_path, voice=v)
                if os.path.exists(seg_path) and os.path.getsize(seg_path) > 500:
                    seg_files.append(seg_path)
                    if idx < len(turns) - 1 and os.path.exists(pause_file):
                        seg_files.append(pause_file)

            if not seg_files:
                return cls.generate_speech(clean_text, output_path, voice=default_voice)

            # Concatenate all speaker segments cleanly
            cmd = [FFMPEG_BIN, "-y"]
            for sf in seg_files:
                cmd.extend(["-i", sf])
            filter_inputs = "".join(f"[{i}:a]" for i in range(len(seg_files)))
            cmd.extend([
                "-filter_complex", f"{filter_inputs}concat=n={len(seg_files)}:v=0:a=1[outa]",
                "-map", "[outa]",
                "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                output_path
            ])
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_path
        finally:
            for sf in set(seg_files + [pause_file]):
                if sf != output_path and os.path.exists(sf):
                    try:
                        os.remove(sf)
                    except Exception:
                        pass

tts_service = TTSService()
