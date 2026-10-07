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

    def listen(self, handle_command, typed=None):
        import sounddevice as sd
        import vosk
        if self.model is None:
            self.report('status', 'Loading local wake detector…')
            self.load()
        while not self.stopped():
            if typed:
                try:
                    text = typed.get_nowait()
                except queue.Empty:
                    text = None
                if text:
                    self.handle(handle_command, text, 'text')
                    continue
            # Close the input stream before cloud processing and speech playback,
            # so the assistant does not hear its own reply or retain background audio.
            audio = queue.Queue(maxsize=100)
            def callback(indata, frames, timing, status):
                try:
                    audio.put_nowait(bytes(indata))
                except queue.Full:
                    pass
            recognizer = vosk.KaldiRecognizer(self.model, RATE,
                json.dumps([WAKE_PHRASE, '[unk]']))
            command = None
            text_command = None
            with sd.RawInputStream(samplerate=RATE, blocksize=1600, dtype='int16',
                                   channels=1, callback=callback):
                self.report('status', 'Listening locally · say “Hey computer”')
                while not self.stopped():
                    if typed:
                        try:
                            text_command = typed.get_nowait()
                        except queue.Empty:
                            pass
                        if text_command:
                            break
                    try:
                        data = audio.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    self.report('level', min(rms(data) / 6000, 1.0))
                    if recognizer.AcceptWaveform(data):
                        text = json.loads(recognizer.Result()).get('text', '')
                        if is_wake(text):
                            self.report('status', 'Awake · speak your command now')
                            winsound.Beep(740, 100)
                            # Discard pre-command blocks, including the acknowledgement tone.
                            while True:
                                try:
                                    audio.get_nowait()
                                except queue.Empty:
                                    break
                            command = self.capture(audio)
                            break
            if command and not self.stopped():
                self.handle(handle_command, command, 'audio')
            elif text_command and not self.stopped():
                self.handle(handle_command, text_command, 'text')

    def handle(self, handler, command, kind):
        try:
            handler(command, kind)
        except Exception as exc:
            self.report('error', str(exc))

    def capture(self, audio):
        chunks = []
        started = time.monotonic()
        last_voice = started
        heard_voice = False
        while not self.stopped() and time.monotonic() - started < 12:
            try:
                data = audio.get(timeout=0.2)
            except queue.Empty:
                continue
            chunks.append(data)
            now = time.monotonic()
            if rms(data) > 450:
                heard_voice = True
                last_voice = now
            self.report('level', min(rms(data) / 6000, 1.0))
            if heard_voice and now - last_voice > 1.3:
                break
            if not heard_voice and now - started > 5:
                self.report('status', 'No command detected · returning to wake listening')
                return None
        return to_wav(chunks) if heard_voice and not self.stopped() else None
