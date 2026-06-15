import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


class VoiceManager:
    """Unified voice I/O manager for TTS and STT."""

    def __init__(
        self,
        tts_voice="ko-KR-HyunsuMultilingualNeural",
        tts_output_path="/tmp/robot_tts.mp3",
        tts_wav_path="/tmp/robot_tts.wav",
        tts_player_cmd=None,
        stt_model_name="base",
        stt_sample_rate=16000,
        stt_record_seconds=5.0,
        stt_language="ko",
        stt_device=None,
        stt_gain=1.0,
    ):
        self.tts_voice = tts_voice
        self.tts_output_path = Path(tts_output_path)
        self.tts_wav_path = Path(tts_wav_path)
        self.tts_player_cmd = tts_player_cmd

        self.stt_model_name = os.getenv("ROBOT_STT_MODEL", stt_model_name)
        self.stt_sample_rate = int(os.getenv("ROBOT_STT_SAMPLE_RATE", stt_sample_rate))
        self.stt_record_seconds = float(
            os.getenv("ROBOT_STT_RECORD_SECONDS", stt_record_seconds)
        )
        self.stt_language = os.getenv("ROBOT_STT_LANGUAGE", stt_language)
        self.stt_device = os.getenv("ROBOT_STT_DEVICE", stt_device or "auto")
        self.stt_gain = float(os.getenv("ROBOT_STT_GAIN", stt_gain))
        self.stt_model = None
        self._reported_audio_devices = False

    def speak(self, text):
        """Text-to-speech: synthesize and play audio."""
        text = self._clean_text(text)

        if text == "":
            return

        asyncio.run(self._speak_async(text))

    async def _speak_async(self, text):
        communicate = edge_tts.Communicate(text, self.tts_voice)
        await communicate.save(str(self.tts_output_path))

        play_path = self.tts_output_path

        if self._has_command("ffmpeg") and self._has_command("pw-play"):
            self._convert_mp3_to_wav()
            play_path = self.tts_wav_path

        command = self._make_play_command(play_path)

        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def listen(self):
        """Speech-to-text: record and transcribe audio."""
        return self._listen()

    def _listen(self):
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        import whisper

        if self.stt_model is None:
            print(f"[VoiceManager] loading STT model: {self.stt_model_name}")
            self.stt_model = whisper.load_model(self.stt_model_name)

        self._report_audio_devices_once(sd)
        device = self._select_input_device(sd)
        record_sample_rate = self._get_device_sample_rate(sd, device)
        print(
            "[VoiceManager] listening... "
            f"seconds={self.stt_record_seconds} "
            f"device={device} "
            f"sample_rate={record_sample_rate}",
            flush=True,
        )

        audio = sd.rec(
            int(self.stt_record_seconds * record_sample_rate),
            samplerate=record_sample_rate,
            channels=1,
            dtype="float32",
            device=device,
        )
        sd.wait()

        audio = np.asarray(audio, dtype=np.float32)

        if self.stt_gain != 1.0:
            audio = np.clip(audio * self.stt_gain, -1.0, 1.0)

        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        print(
            f"[VoiceManager] audio level rms={rms:.6f} peak={peak:.6f}",
            flush=True,
        )

        if peak < 0.003:
            print(
                "[VoiceManager] audio is too quiet. Check microphone input device.",
                flush=True,
            )
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        sf.write(str(wav_path), audio, record_sample_rate)

        try:
            result = self.stt_model.transcribe(
                str(wav_path),
                language=self.stt_language,
                fp16=False,
            )
            text = result.get("text", "").strip()
            print(f"[VoiceManager] text: {text}")
            return text

        finally:
            try:
                wav_path.unlink()
            except FileNotFoundError:
                pass

    def _convert_mp3_to_wav(self):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(self.tts_output_path),
                str(self.tts_wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def _make_play_command(self, play_path):
        if self.tts_player_cmd is not None:
            return [self.tts_player_cmd, str(play_path)]

        if play_path.suffix.lower() == ".wav" and self._has_command("pw-play"):
            return ["pw-play", str(play_path)]

        if self._has_command("ffplay"):
            return [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                str(play_path),
            ]

        if self._has_command("mpg123"):
            return ["mpg123", str(play_path)]

        raise RuntimeError("No available audio player: install pw-play, ffplay, or mpg123")

    def _clean_text(self, text):
        if text is None:
            return ""

        return str(text).strip()

    def _has_command(self, command):
        return shutil.which(command) is not None

    def _report_audio_devices_once(self, sd):
        if self._reported_audio_devices:
            return

        self._reported_audio_devices = True

        try:
            default_input = sd.default.device[0]
            print(f"[VoiceManager] default input device: {default_input}", flush=True)

            devices = sd.query_devices()
            print("[VoiceManager] input devices:", flush=True)

            for index, device in enumerate(devices):
                if int(device.get("max_input_channels", 0)) <= 0:
                    continue

                print(
                    "  "
                    f"{index}: {device.get('name')} "
                    f"inputs={device.get('max_input_channels')} "
                    f"rate={device.get('default_samplerate')}",
                    flush=True,
                )

            if self.stt_device:
                print(
                    f"[VoiceManager] ROBOT_STT_DEVICE={self.stt_device}",
                    flush=True,
                )

        except Exception as exc:
            print(f"[VoiceManager] failed to query audio devices: {exc}", flush=True)

    def _select_input_device(self, sd):
        if self.stt_device == "":
            return None

        if self.stt_device.lower() == "auto":
            return self._select_auto_input_device(sd)

        try:
            return int(self.stt_device)
        except ValueError:
            pass

        devices = sd.query_devices()
        target = self.stt_device.lower()

        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) <= 0:
                continue

            name = str(device.get("name", "")).lower()

            if target in name:
                return index

        raise RuntimeError(
            "ROBOT_STT_DEVICE did not match an input device: "
            f"{self.stt_device}"
        )

    def _select_auto_input_device(self, sd):
        devices = sd.query_devices()
        preferred_keywords = [
            "usb",
            "microphone",
            "mic",
        ]

        for keyword in preferred_keywords:
            for index, device in enumerate(devices):
                if int(device.get("max_input_channels", 0)) <= 0:
                    continue

                name = str(device.get("name", "")).lower()

                if keyword in name and "default" not in name:
                    return index

        default_input = sd.default.device[0]

        if default_input is None or int(default_input) < 0:
            return None

        return int(default_input)

    def _get_device_sample_rate(self, sd, device):
        if device is None:
            device = sd.default.device[0]

        try:
            info = sd.query_devices(device, "input")
            return int(float(info.get("default_samplerate", self.stt_sample_rate)))
        except Exception:
            return int(self.stt_sample_rate)


# Backward compatibility: expose individual classes
class TTS:
    """Backward-compatible wrapper for VoiceManager TTS functionality."""

    def __init__(
        self,
        voice="ko-KR-HyunsuMultilingualNeural",
        output_path="/tmp/robot_tts.mp3",
        wav_path="/tmp/robot_tts.wav",
        player_cmd=None,
    ):
        self._manager = VoiceManager(
            tts_voice=voice,
            tts_output_path=output_path,
            tts_wav_path=wav_path,
            tts_player_cmd=player_cmd,
        )

    def speak(self, text):
        self._manager.speak(text)


class WhisperSTT:
    """Backward-compatible wrapper for VoiceManager STT functionality."""

    def __init__(
        self,
        model_name="base",
        sample_rate=16000,
        record_seconds=5.0,
        language="ko",
    ):
        self._manager = VoiceManager(
            stt_model_name=model_name,
            stt_sample_rate=sample_rate,
            stt_record_seconds=record_seconds,
            stt_language=language,
        )

    def listen(self):
        return self._manager.listen()
