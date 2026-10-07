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









