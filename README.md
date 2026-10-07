# ULTRON · JARVIS interface

A Windows voice assistant with a luminous animated sphere, smooth blue controls, a dedicated
conversation panel, local wake detection, local transcription, local synthetic speech, and
configurable cloud intelligence. Connection and privacy preferences live in a separate settings window.

## Open

From this project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m ultron
```

The app starts listening automatically. Say **Hey computer**, wait for the acknowledgement tone,
then speak your command. It returns to wake listening after every response, including after a failed
cloud request. You do not need to press a button for each conversation. The microphone closes while
processing and speaking so the app does not hear its own response.

**Pause listening** stops listening and cancels queued commands. **Resume listening** enables it
again. Text input and quick commands remain available when muted; typed commands can also be queued
while the voice listener is running. Closing the window exits the assistant. This version does not
register itself to start at Windows login.

## Fresh installation

Requires Windows x64, Python with Tkinter, a microphone supporting 16 kHz mono, and a Windows desktop
speech voice. The local installation uses Python 3.14.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ultron.setup_model
.\.venv\Scripts\python.exe -m ultron
```

If you have UV, you can install with:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt
```

