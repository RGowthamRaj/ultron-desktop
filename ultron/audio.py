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


