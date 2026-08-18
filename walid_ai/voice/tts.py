class TextToSpeech:
 def __init__(self):
  self.engine=None
  try:
   import pyttsx3
   self.engine=pyttsx3.init()
  except Exception:pass
 def speak(self,text):
  if self.engine:self.engine.say(text);self.engine.runAndWait()
