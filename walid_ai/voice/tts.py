"""Text-to-speech helper."""
from __future__ import annotations

import threading


class TextToSpeech:
    def __init__(self):
        self.engine = None
        self._lock = threading.Lock()

        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 150)
        except Exception:
            self.engine = None

    @property
    def available(self) -> bool:
        return self.engine is not None

    def speak(self, text: str) -> None:
        if not self.engine:
            return

        def worker() -> None:
            with self._lock:
                try:
                    self.engine.say(text[:1200])
                    self.engine.runAndWait()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()
