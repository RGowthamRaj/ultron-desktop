"""Polished native presentation layer; assistant behavior lives in App."""
import math
import time
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter, ImageTk
from .cloud import PRESETS

BG = '#070b12'
PANEL = '#0c131e'
LINE = '#1b293a'
CYAN = '#7de7ff'
BLUE = '#54b7ed'
TEXT = '#ecf4fc'
MUTED = '#8595ab'


def round_rect(draw, box, radius, fill, outline=None):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)


class SoftButton(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=160, height=42):
        super().__init__(parent, width=width, height=height, bg=parent.cget('bg'),
                         highlightthickness=0, bd=0, cursor='hand2')
        self.caption = text
        self.command = command
        self.primary = primary
        self.enabled = True
        self.hover = False
        self.bind('<Configure>', lambda e: self.paint())
        self.bind('<Enter>', lambda e: self.roll(True))
        self.bind('<Leave>', lambda e: self.roll(False))
        self.bind('<Button-1>', lambda e: self.invoke())
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.configure(takefocus=1)

    def invoke(self):
        if self.enabled:
            self.command()

    def roll(self, hover):
        self.hover = hover
        self.paint()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if 'text' in kwargs:
            self.caption = kwargs.pop('text')
        if 'state' in kwargs:
            self.enabled = kwargs.pop('state') != 'disabled'
        if kwargs:
            super().configure(**kwargs)
        if hasattr(self, 'caption'):
            self.paint()

    config = configure

    def paint(self):
        self.delete('all')
        w, h = max(20, self.winfo_width()), max(20, self.winfo_height())
        scale = 2
        image = Image.new('RGB', (w*scale, h*scale), self.cget('bg'))
        draw = ImageDraw.Draw(image)
        fill = ('#62d8fa' if self.hover else '#8ae6ff') if self.primary else ('#1a2b40' if self.hover else '#111e2e')
        if not self.enabled:
            fill = '#152130'
        round_rect(draw, (0, 0, w*scale-1, h*scale-1), 12*scale, fill)
        self._photo = ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS))
        self.create_image(0, 0, anchor='nw', image=self._photo)
        caption = {'MUTE MICROPHONE': 'Pause listening', 'RESUME LISTENING': 'Resume listening'}.get(self.caption, self.caption)
        self.create_text(w/2, h/2, text=caption, fill=BG if self.primary and self.enabled else TEXT,
                         font=('Segoe UI', 10, 'bold' if self.primary else 'normal'))


class Interface:
    def label(self, parent, text='', variable=None, size=10, color=MUTED, weight='normal', **kwargs):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size, weight), **kwargs)

    def button(self, parent, text, command, primary=False, width=160, height=42):
        return SoftButton(parent, text, command, primary, width, height)



    def open_settings(self):
        window = self.settings_window
        window.deiconify()
        window.lift()
        window.focus_set()

    def open_privacy(self):
        self.open_settings()

    def build_settings(self):
        self.settings_window = tk.Toplevel(self.root)
        window = self.settings_window
        window.title('Ultron · Connection & preferences')
        window.geometry('790x660')
        window.minsize(790, 660)
        window.configure(bg=BG)
        window.transient(self.root)
        window.protocol('WM_DELETE_WINDOW', window.withdraw)
        frame = tk.Frame(window, bg=BG, padx=32, pady=28)
        frame.pack(fill='both', expand=True)
        self.label(frame, 'Your intelligence. Your choice.', size=23, color=TEXT, weight='bold').pack(anchor='w')
        self.label(frame, 'Connect your provider once. Ultron takes it from there.', size=11).pack(anchor='w', pady=(7, 24))
        body = tk.Frame(frame, bg=BG)
        body.pack(fill='both', expand=True)
        form = tk.Frame(body, bg=BG, width=410)
        form.pack(side='left', fill='both', expand=True, padx=(0, 26))
        options = tk.Frame(body, bg=PANEL, width=245, padx=18, pady=20)
        options.pack(side='right', fill='y')
        options.pack_propagate(False)
        self.label(form, 'AI provider', size=10, color=TEXT).pack(anchor='w', pady=(0, 8))
        select = ttk.Combobox(form, textvariable=self.provider, values=list(PRESETS), state='readonly')
        select.pack(fill='x')
        select.bind('<<ComboboxSelected>>', self.change_provider)
        for title, variable, mask in [('API key', self.key, '•'), ('Base URL', self.endpoint, ''), ('Model ID', self.model, '')]:
            self.label(form, title, size=10, color=TEXT).pack(anchor='w', pady=(19, 8))
            entry = tk.Entry(form, textvariable=variable, show=mask, bg='#111e2e', fg=TEXT,
                             insertbackground=CYAN, font=('Segoe UI', 11), relief='flat', bd=0)
            entry.pack(fill='x', ipady=11)
        self.label(form, variable=self.connection, size=9, color=BLUE).pack(anchor='w', pady=(17, 0))
        self.label(options, 'YOUR PREFERENCES', size=8, color=BLUE, weight='bold').pack(anchor='w', pady=(0, 16))
        for text, variable in [('Remember encrypted key', self.remember), ('Speak replies', self.voice),
                               ('Desktop actions', self.tools), ('Listen automatically', self.auto)]:
            tk.Checkbutton(options, text=text, variable=variable, bg=PANEL, fg=TEXT, selectcolor='#15283b',
                           activebackground=PANEL, activeforeground=CYAN, font=('Segoe UI', 10),
                           bd=0, anchor='w', command=lambda: setattr(self, 'speech_enabled', self.voice.get())
                           ).pack(fill='x', pady=8)
        tk.Frame(options, bg=LINE, height=1).pack(fill='x', pady=22)
        self.label(options, 'Private by design', size=12, color=TEXT, weight='bold').pack(anchor='w')
        self.label(options, 'Audio is processed on your PC.\nOnly recognized text goes to\nyour chosen AI provider.\n\nRemembered keys are encrypted\nfor your Windows account.',
                   size=9, justify='left', wraplength=210).pack(anchor='w', pady=(10, 0))
        self.label(frame, 'Supports OpenAI-compatible chat APIs. Your key must match the provider.', size=9).pack(anchor='w', pady=(18, 16))
        actions = tk.Frame(frame, bg=BG)
        actions.pack(fill='x')
        self.test_button = self.button(actions, 'Test connection', self.test_connection, width=155)
        self.test_button.pack(side='left')
        self.button(actions, 'Save connection', self.save_and_close, True, width=165).pack(side='right')
        self.button(actions, 'Cancel', window.withdraw, width=90).pack(side='right', padx=10)
        window.withdraw()

    def save_and_close(self):
        if self.apply():
            self.settings_window.withdraw()



