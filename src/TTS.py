import asyncio
import shutil
import subprocess
from pathlib import Path

import edge_tts

"ko-KR-SunHiNeural"

class TTS:
    def __init__(
        self,
        voice="ko-KR-HyunsuMultilingualNeural",
        output_path="/tmp/robot_tts.mp3",
        wav_path="/tmp/robot_tts.wav",
        player_cmd=None,
    ):
        self.voice = voice
        self.output_path = Path(output_path)
        self.wav_path = Path(wav_path)
        self.player_cmd = player_cmd

    def speak(self, text):
        text = self._clean_text(text)

        if text == "":
            return

        asyncio.run(self._speak_async(text))

    async def _speak_async(self, text):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(self.output_path))

        play_path = self.output_path

        if self._has_command("ffmpeg") and self._has_command("pw-play"):
            self._convert_mp3_to_wav()
            play_path = self.wav_path

        command = self._make_play_command(play_path)

        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def _convert_mp3_to_wav(self):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(self.output_path),
                str(self.wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def _make_play_command(self, play_path):
        if self.player_cmd is not None:
            return [self.player_cmd, str(play_path)]

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
