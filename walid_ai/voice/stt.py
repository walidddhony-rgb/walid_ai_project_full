"""Speech-to-text helper using faster-whisper."""
from __future__ import annotations

from pathlib import Path


class SpeechToText:
    def __init__(self, model_name: str = "base"):
        self.model = None
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
        except Exception:
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def transcribe_file(self, audio_path: str | Path, language: str = "ar") -> str:
        if not self.model:
            raise RuntimeError("Speech-to-text model is not available.")

        segments, _ = self.model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        return " ".join(segment.text for segment in segments).strip()
