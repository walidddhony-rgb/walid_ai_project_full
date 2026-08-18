class SpeechToText:
 def __init__(self):
  self.model=None
  try:
   from faster_whisper import WhisperModel
   self.model=WhisperModel("base",device="cpu",compute_type="int8")
  except Exception:pass
 @property
 def available(self):return self.model is not None
