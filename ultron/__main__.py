"""A blue, animated desktop HUD with continuous local wake listening."""
import math
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, scrolledtext
from urllib.parse import urlsplit

from .audio import Listener
from .cloud import Cloud, PRESETS
from . import settings
from .speech import speak
from .interface import Interface, BG, PANEL, LINE, CYAN, BLUE, TEXT, MUTED, GEMINI, SUCCESS



class App(Interface):
    def __init__(self, root, autostart=True):
        self.root = root
        self.events = queue.Queue()
        self.typed = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.worker = None
        self.mode = None
        self.pending_cloud = None
        self.closing = False
        self.testing = False
        self.started = time.monotonic()
        self.phase = 0.0
        self.level = 0.0
        self.levels = [0.0] * 32
        self.commands = 0
        self.state = 'STANDBY'
        config = settings.load()
        self.provider = tk.StringVar(value=config['provider'])
        self.endpoint = tk.StringVar(value=config['base_url'])
        self.model = tk.StringVar(value=config['model'])
        self.key = tk.StringVar(value=config['key'])
        self.remember = tk.BooleanVar(value=config['remember'])
        self.voice = tk.BooleanVar(value=config['speech'])
        self.tools = tk.BooleanVar(value=config['tools'])
        self.auto = tk.BooleanVar(value=config['autolisten'])
        self.status = tk.StringVar(value='Waking up…')
        self.connection = tk.StringVar(value='CONFIGURED' if config['key'] else 'KEY REQUIRED')
        self.clock = tk.StringVar()
        self.uptime = tk.StringVar()
        self.want_listen = bool(config['autolisten'])
        self.speech_enabled = bool(config['speech'])
        self.cloud = None
        try:
            self.cloud = self.make_cloud()
        except ValueError:
            pass
        root.title('ULTRON · Personal Intelligence')
        root.geometry('1280x880')
        root.minsize(1160, 850)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TCombobox', fieldbackground='#0b2133', background=LINE, foreground=TEXT,
                        arrowcolor=CYAN, bordercolor=LINE, padding=8)
        style.map('TCombobox', fieldbackground=[('readonly', '#0b2133')], foreground=[('readonly', TEXT)],
                  selectbackground=[('readonly', '#0b2133')], selectforeground=[('readonly', TEXT)])
        root.option_add('*TCombobox*Listbox.background', PANEL)
        root.option_add('*TCombobox*Listbox.foreground', TEXT)
        self.build()
        self._refresh_provider_badge()
        self.write('SYSTEM', 'Welcome back. Say “Hey computer”, wait for the tone, then speak.')
        self.write('SYSTEM', 'Use Connection to choose your AI provider. Listening resumes automatically after each reply.')
        if config.get('notice'):
            self.write('ISSUE', config['notice'])
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(60, self.animate)
        root.after(80, self.poll)
        if autostart and self.want_listen:
            root.after(700, self.start)




    def change_provider(self, event=None):
        base, model = PRESETS[self.provider.get()]
        self.endpoint.set(base)
        self.model.set(model)
        self.key.set('')  # Never send one provider's key to another provider by accident.
        self.connection.set('SAVE NEW CONNECTION')
        self._refresh_provider_badge()

    def _refresh_provider_badge(self):
        """Update the sidebar provider badge letter and color to reflect the active provider."""
        if not hasattr(self, 'provider_badge'):
            return
        prov = self.provider.get()
        if 'Gemini' in prov:
            letter, bg, fg = 'G', '#1a3a5c', GEMINI
        elif 'NVIDIA' in prov or 'Nemotron' in prov:
            letter, bg, fg = 'N', '#1a2d1a', SUCCESS
        elif 'OpenAI' in prov:
            letter, bg, fg = 'O', '#1a2530', CYAN
        else:
            letter, bg, fg = '\u2699', '#252525', MUTED
        self.provider_badge.configure(text=letter, bg=bg, fg=fg)

    def config(self):
        return {'provider': self.provider.get(), 'base_url': self.endpoint.get(), 'model': self.model.get(),
                'key': self.key.get(), 'remember': self.remember.get(), 'speech': self.voice.get(),
                'tools': self.tools.get(), 'autolisten': self.auto.get()}

    def make_cloud(self):
        return Cloud(self.key.get(), self.model.get(), self.endpoint.get(), self.tools.get())

    def ready(self):
        return self.cloud and (self.cloud.key or urlsplit(self.cloud.base_url).hostname in ('localhost', '127.0.0.1', '::1'))

    def apply(self):
        try:
            cloud = self.make_cloud()
            settings.save(self.config())
        except Exception as exc:
            self.write('ISSUE', str(exc))
            return False
        self.speech_enabled = self.voice.get()
        self.want_listen = self.auto.get()
        self.connection.set('CONFIGURED' if cloud.key else 'KEY REQUIRED')
        self.write('SYSTEM', 'Connection saved. Continuous listening follows your launch preference.')
        if self.mode:
            self.pending_cloud = cloud
            self.stop_event.set()
        else:
            self.cloud = cloud
            if self.want_listen:
                self.start()
        return True

    def test_connection(self):
        if self.testing:
            return
        try:
            cloud = self.make_cloud()
        except ValueError as exc:
            self.write('ISSUE', str(exc))
            return
        self.testing = True
        self.connection.set('CHECKING…')
        self.test_button.configure(state='disabled')
        def check():
            try:
                self.report('connection', cloud.check())
            except Exception as exc:
                self.report('connection_error', str(exc))
        threading.Thread(target=check, daemon=True).start()

    def report(self, kind, message):
        self.events.put((kind, message))


    def run_worker(self, target, mode):
        if self.mode or self.closing:
            return
        self.stop_event.clear()
        self.mode = mode
        def run():
            try:
                target()
            except Exception as exc:
                self.report('error', str(exc))
            finally:
                self.report('finished', '')
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def start(self):
        if self.mode or self.closing or not self.want_listen:
            return
        self.mute_button.configure(text='MUTE MICROPHONE')
        self.listener = Listener(self.stop_event.is_set, self.report)
        self.run_worker(lambda: self.listener.listen(self.handle_command, self.typed), 'voice')

    def handle_command(self, command, kind):
        if kind == 'audio':
            self.report('status', 'Transcribing locally…')
            text = self.listener.transcribe(command)
        else:
            text = command
        if not text:
            self.report('error', 'I did not catch that. Say the wake phrase and try again.')
            return
        self.respond(text)

    def respond(self, text):
        self.report('user', text)
        if not self.ready():
            self.report('error', 'Add your provider key in Connection and choose Save connection.')
            return
        self.report('status', 'Thinking…')
        answer = self.cloud.reply(text, self.stop_event.is_set, self.report)
        if not answer or self.stop_event.is_set():
            return
        self.report('assistant', answer)
        if self.speech_enabled:
            self.report('status', 'Speaking…')
            try:
                speak(answer, self.stop_event.is_set)
            except Exception as exc:
                self.report('error', str(exc))

    def send(self, text=None):
        text = text or self.input.get().strip()
        if not text:
            return
        self.input.delete(0, 'end')
        if self.mode == 'voice' and not self.stop_event.is_set():
            try:
                self.typed.put_nowait(text)
            except queue.Full:
                self.write('ISSUE', 'Two commands are already queued. Please wait for a reply.')
        elif not self.mode:
            self.run_worker(lambda: self.respond(text), 'text')
        else:
            self.write('ISSUE', 'Finishing the current operation. Please wait a moment.')

    def toggle_listening(self):
        self.want_listen = not self.want_listen
        if self.want_listen:
            self.start()
        else:
            self.stop_event.set()
            self.state = 'MUTED'
            self.status.set('Microphone muted · text commands remain available')
            self.mute_button.configure(text='RESUME LISTENING')
            while True:
                try:
                    self.typed.get_nowait()
                except queue.Empty:
                    break

    def clear(self):
        if self.mode and self.state not in ('LISTENING', 'MUTED'):
            self.write('ISSUE', 'Wait for the current response before clearing the conversation.')
            return
        if self.cloud:
            self.cloud.history.clear()
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'level':
                    self.level = float(value)
                elif kind == 'status' and not self.stop_event.is_set():
                    self.status.set(value)
                    lower = value.lower()
                    self.state = ('LISTENING' if 'listening locally' in lower else 'CAPTURING' if 'awake' in lower
                                  else 'THINKING' if 'thinking' in lower else 'SPEAKING' if 'speaking' in lower
                                  else 'PROCESSING')
                elif kind == 'finished':
                    self.mode = None
                    self.level = 0.0
                    if self.pending_cloud:
                        self.cloud, self.pending_cloud = self.pending_cloud, None
                    if self.want_listen:
                        self.root.after(1000, self.start)
                    else:
                        self.state = 'MUTED'
                        self.mute_button.configure(text='RESUME LISTENING')
                        self.status.set('Microphone muted · text commands remain available')
                elif kind in ('connection', 'connection_error'):
                    self.testing = False
                    self.test_button.configure(state='normal')
                    self.connection.set('VERIFIED' if kind == 'connection' else 'CHECK FAILED')
                    self.write('SYSTEM' if kind == 'connection' else 'ISSUE', value)
                elif kind != 'status':
                    self.write({'user': 'YOU', 'assistant': 'ULTRON', 'action': 'DESKTOP', 'error': 'ISSUE'}.get(kind, 'SYSTEM'), value)
                    if kind == 'user':
                        self.commands += 1
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(80, self.poll)


    def close(self):
        self.closing = True
        self.stop_event.set()
        self.root.after(250, self.root.destroy)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
