import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf
import whisper


class WhisperSTT:
    def __init__(
        self,
        model_name="base",
        sample_rate=16000,
        record_seconds=5.0,
        language="ko",
    ):
        self.model_name = model_name
        self.sample_rate = sample_rate
        self.record_seconds = record_seconds
        self.language = language

        print(f"[WhisperSTT] loading model: {model_name}")
        self.model = whisper.load_model(model_name)

    def listen(self):
        return self._listen()

    def _listen(self):
        print("[WhisperSTT] listening...")

        audio = sd.rec(
            int(self.record_seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        sf.write(str(wav_path), audio, self.sample_rate)

        try:
            result = self.model.transcribe(
                str(wav_path),
                language=self.language,
                fp16=False,
            )
            text = result.get("text", "").strip()
            print(f"[WhisperSTT] text: {text}")
            return text

        finally:
            try:
                wav_path.unlink()
            except FileNotFoundError:
                pass


def main():
    print("=" * 60)
    print("[MAIN] Whisper STT test start")
    print("=" * 60)

    stt = WhisperSTT(
        model_name="base",
        sample_rate=16000,
        record_seconds=5.0,
        language="ko",
    )

    while True:
        print()
        user_input = input("[MAIN] Press Enter to record, or type 'q' to quit: ").strip()

        if user_input.lower() in ["q", "quit", "exit"]:
            print("[MAIN] quit")
            break

        print("=" * 60)
        print("[MAIN] Recording starts now. Speak for 5 seconds.")
        print("=" * 60)

        text = stt.listen()

        print("=" * 60)
        print("[MAIN] STT result")
        print("=" * 60)
        print(f"text: {text}")
        print("=" * 60)


if __name__ == "__main__":
    main()