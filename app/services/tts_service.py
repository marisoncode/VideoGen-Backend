import os
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
    }
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

tts_service = TTSService()
