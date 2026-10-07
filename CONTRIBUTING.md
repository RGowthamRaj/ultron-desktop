# Contributing to Ultron

Use Windows and Python 3.14 with Tkinter. Follow the fresh installation steps in
the README, then run the assistant with `python -m ultron` in your virtual environment.
The downloaded Vosk model is needed for a microphone session, but not for the tests.

## Before submitting a change

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Keep changes focused and describe the behavior they change. Include a regression
test for changes to provider requests, cancellation, desktop actions, or listener
recovery. Tests must mock provider calls and desktop actions; they must not require
an API key, spend credits, or open applications.

For interface changes, inspect both the default and minimum window sizes, including
the connection dialog. Run `tests/ui_preview.py` with the virtual environment's
Python to generate a local preview; add `--settings` for the connection dialog.
Preview images go into the ignored `output` folder. Check screenshots for personal
information before attaching them to an issue or pull request.

## Implementation boundaries

- Keep wake detection, transcription, and speech local. Document any change to
  the data sent to the selected provider.
- Add desktop capabilities through fixed, validated actions in `ultron/actions.py`.
  Never execute model-generated shell commands.
- Check cancellation before dispatching a desktop action. Preserve the return to
  wake listening after a reply or a failed provider request.
- Keep microphone and network work off the Tkinter thread. Deliver UI updates
  through the existing event queue.
- Never commit credentials, recordings, saved settings, downloaded models, or
  virtual environments. Use obviously fake values in tests.
- Preserve HTTPS for remote providers and refuse credential-bearing redirects.

Report bugs with your Windows/Python versions, provider and model names (without
keys), steps to reproduce, and the visible error message. Avoid posting raw saved
configuration files or private conversation transcripts.
