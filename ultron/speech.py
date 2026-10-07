"""Local, interruptible Windows speech. No voice-provider key required."""
import os
import subprocess

SCRIPT = '''$ErrorActionPreference = 'Stop';
[Console]::InputEncoding = [System.Text.Encoding]::UTF8;
Add-Type -AssemblyName System.Speech;
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer;
try {
  $voices = $speaker.GetInstalledVoices();
  if ($voices.Count -eq 0) { throw 'No Windows desktop voices are installed.'; }
  $david = $voices | Where-Object { $_.VoiceInfo.Name -like '*David*' } | Select-Object -First 1;
  if ($david) { $speaker.SelectVoice($david.VoiceInfo.Name); }
  $speaker.Rate = -1;
  $speaker.Speak([Console]::In.ReadToEnd());
} finally { $speaker.Dispose(); }'''


def speak(text, stopped):
    if stopped():
        return
    executable = os.path.join(os.environ.get('WINDIR', r'C:\Windows'),
                              'System32/WindowsPowerShell/v1.0/powershell.exe')
    process = subprocess.Popen([executable, '-NoProfile', '-NonInteractive', '-Command', SCRIPT],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW)
    process.stdin.write(text[:3000].encode('utf-8'))
    process.stdin.close()
    try:
        while process.poll() is None:
            if stopped():
                process.terminate()
                break
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
        if process.returncode and not stopped():
            raise RuntimeError('Windows speech is unavailable. Install a desktop voice in Windows settings.')
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        process.stderr.close()
