"""Render only this app window for visual QA; never activate microphone or cloud."""
from pathlib import Path
import tkinter as tk
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
from ultron.__main__ import App

root = tk.Tk()
app = App(root, autostart=False)
root.geometry('1360x860+30+30')
root.attributes('-topmost', True)
root.update()
output = Path(__file__).resolve().parents[1] / ('output/ui-settings.png' if '--settings' in sys.argv else 'output/ui-preview.png')
output.parent.mkdir(exist_ok=True)


def capture():
    window = root
    if '--settings' in sys.argv:
        app.open_settings()
        window = app.settings_window
        window.attributes('-topmost', True)
    root.update()
    x, y = window.winfo_rootx(), window.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x+window.winfo_width(), y+window.winfo_height())).save(output)
    print('Saved app preview. Microphone and cloud remained off.')
    root.destroy()


root.after(1000, capture)
root.mainloop()
