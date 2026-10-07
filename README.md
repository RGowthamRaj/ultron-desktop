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

## Connect your AI provider once

1. Open **Connection settings** (or **Connection** in the sidebar), then choose **NVIDIA Nemotron**,
   **OpenAI**, or **Custom compatible API**.
2. Enter that provider's API key, base URL, and model ID.
3. Use **Test connection** to check access without running desktop actions.
4. Choose **Save connection**. Leave **Listen automatically on launch** enabled.

The NVIDIA preset uses `https://integrate.api.nvidia.com/v1` and
`nvidia/nemotron-3.5-lightning-30b-a3b`. The OpenAI preset uses `https://api.openai.com/v1` and
`gpt-4.1-mini`. Both model IDs are editable. Custom APIs must implement OpenAI-compatible
`POST /chat/completions`, bearer authentication, and a compatible response schema. The provider
must permit the selected model. A key for one provider cannot authenticate with another provider.
Native Anthropic or Google APIs need a compatible gateway or a separate adapter.

Switching provider clears the unsaved key field. Changing provider/model settings takes effect after
you save. Some chat models do not support tool calling: disable **Enable desktop tools** to use
conversation only. Local compatible servers can use an HTTP localhost base URL with an optional key;
remote providers require HTTPS. The app does not forward credentials through HTTP redirects.

**Remember encrypted key** stores it encrypted by Windows DPAPI for your current Windows account.
Preferences live at `%APPDATA%\Ultron\settings.json`. Uncheck Remember and save to remove the stored
key. The key is masked in the interface and is not included in source files or GitHub commits.
The optional environment variables `NVIDIA_API_KEY`, `OPENAI_API_KEY`, and `ULTRON_MODEL` supply
initial defaults when no saved configuration exists.

## Things to say

- “Open calculator.”
- “Open Visual Studio Code.”
- “Open file explorer.”
- “Search the web for FIR filter tutorials.”
- “Turn the volume down.”
- “Pause the music.”
- “Explain interrupts and polling in three sentences.”

Supported apps: Notepad, Calculator, Explorer, the default browser, VS Code, Chrome, Edge, Spotify.
They must already be installed. Search opens results in the browser; it does not read their content.
Media controls send Windows media keys; mute toggles the current mute state.

## Audio and privacy

Wake recognition and command transcription use the installed small English Vosk model. Voice replies
use an installed Windows desktop voice, preferring Microsoft David. No OpenAI speech key is needed
when using NVIDIA or a custom provider. The voice is synthetic, not an actor's voice recreation.

Ambient audio and command clips stay on your device and are not saved. Only recognized text, recent
conversation turns, and desktop tool results are sent to the selected AI provider. Provider data
retention and usage charges follow that provider's policies. The conversation is held in memory.

The default wake phrase is **Hey computer** because those words are in the speech model vocabulary.
A dependable “Ultron” or “Jarvis” trigger requires a suitable custom wake model or pronunciation
support. This is phrase recognition, not speaker authentication; nearby voices may activate it.

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

