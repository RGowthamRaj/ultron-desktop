"""Local wake phrase recognition and bounded command capture."""
import array
import io
import json
import math
import queue
import time
import wave
import winsound
from pathlib import Path


MODEL_PATH = Path(__file__).resolve().parent.parent / 'models/vosk-model-small-en-us-0.15'
RATE = 16000
WAKE_PHRASE = 'hey computer'


def is_wake(text):
    return text.strip().lower() == WAKE_PHRASE


def rms(data):
    samples = array.array('h', data)
    return math.sqrt(sum(s * s for s in samples) / max(len(samples), 1))


def to_wav(chunks):
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(RATE)
        writer.writeframes(b''.join(chunks))
    return output.getvalue()


class Listener:
    def __init__(self, stopped, report):
        self.stopped = stopped
        self.report = report
        self.model = None

    def transcribe(self, wav):
        import vosk
        if self.model is None:
            self.load()
        recognizer = vosk.KaldiRecognizer(self.model, RATE)
        parts = []
        with wave.open(io.BytesIO(wav), 'rb') as reader:
            while data := reader.readframes(4000):
                if self.stopped():
                    return ''
                if recognizer.AcceptWaveform(data):
                    parts.append(json.loads(recognizer.Result()).get('text', ''))
        parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
        return ' '.join(part for part in parts if part).strip()

    def load(self):
        import vosk
        if not MODEL_PATH.is_dir():
            raise RuntimeError('Wake model missing. Run: python -m ultron.setup_model')
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(str(MODEL_PATH))



