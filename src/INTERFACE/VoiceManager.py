import asyncio
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
    ):
        self.tts_voice = tts_voice
        self.tts_output_path = Path(tts_output_path)
        self.tts_wav_path = Path(tts_wav_path)
        self.tts_player_cmd = tts_player_cmd

        self.stt_model_name = stt_model_name
        self.stt_sample_rate = stt_sample_rate
        self.stt_record_seconds = stt_record_seconds
        self.stt_language = stt_language
        self.stt_model = None

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
        import sounddevice as sd
        import soundfile as sf
        import whisper

        if self.stt_model is None:
            print(f"[VoiceManager] loading STT model: {self.stt_model_name}")
            self.stt_model = whisper.load_model(self.stt_model_name)

        print("[VoiceManager] listening...")

        audio = sd.rec(
            int(self.stt_record_seconds * self.stt_sample_rate),
            samplerate=self.stt_sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        sf.write(str(wav_path), audio, self.stt_sample_rate)

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
