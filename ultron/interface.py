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

    def build(self):
        self.root.geometry('1360x860')
        self.root.minsize(1160, 760)
        self.root.configure(bg=BG)
        self.root.title('ULTRON · Personal intelligence')
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        style = ttk.Style(self.root)
        style.configure('Dark.Vertical.TScrollbar', background='#24344b', troughcolor=PANEL,
                        bordercolor=PANEL, arrowcolor=PANEL, gripcount=0, arrowsize=0)
        style.configure('TCombobox', fieldbackground='#111e2e', background=LINE,
                        foreground=TEXT, arrowcolor=CYAN, bordercolor=LINE, padding=8)
        style.map('TCombobox', fieldbackground=[('readonly', '#111e2e')], foreground=[('readonly', TEXT)],
                  selectbackground=[('readonly', '#111e2e')], selectforeground=[('readonly', TEXT)])

        rail = tk.Frame(self.root, bg='#0a101a', width=198, padx=22, pady=28)
        rail.grid(row=0, column=0, sticky='nsew')
        rail.pack_propagate(False)
        brand = tk.Frame(rail, bg=rail.cget('bg'))
        brand.pack(fill='x', pady=(0, 48))
        logo = tk.Canvas(brand, width=36, height=36, bg=rail.cget('bg'), highlightthickness=0)
        logo.pack(side='left', padx=(0, 9))
        logo.create_oval(3, 3, 32, 32, outline=CYAN, width=2)
        logo.create_line(11, 12, 11, 22, 18, 26, 25, 22, 25, 12, fill=CYAN, width=2)
        self.label(brand, 'ULTRON', size=13, color=TEXT, weight='bold').pack(side='left')
        self.label(rail, 'WORKSPACE', size=8, color='#54677f').pack(anchor='w', pady=(0, 14))
        self.button(rail, 'Assistant', self.focus_assistant, True, width=154).pack(fill='x', pady=(0, 10))
        self.button(rail, 'Connection', self.open_settings, width=154).pack(fill='x', pady=(0, 10))
        self.button(rail, 'Privacy & voice', self.open_privacy, width=154).pack(fill='x')
        self.label(rail, 'QUICK ACTIONS', size=8, color='#54677f').pack(anchor='w', pady=(36, 14))
        for text, prompt in [('Calculator', 'Open calculator'), ('Files', 'Open explorer'), ('Browser', 'Open browser')]:
            self.button(rail, text, lambda p=prompt: self.send(p), width=154, height=36).pack(fill='x', pady=4)
        rail_bottom = tk.Frame(rail, bg=rail.cget('bg'))
        rail_bottom.pack(side='bottom', fill='x')
        self.label(rail_bottom, 'YOUR AI', size=8, color='#54677f').pack(anchor='w')
        self.label(rail_bottom, variable=self.provider, size=10, color=TEXT, wraplength=152,
                   justify='left').pack(anchor='w', pady=(7, 5))
        self.label(rail_bottom, variable=self.connection, size=8, color=BLUE).pack(anchor='w')
        self.button(rail_bottom, 'Configure', self.open_settings, width=154, height=36).pack(fill='x', pady=(14, 22))
        tk.Frame(rail_bottom, bg=LINE, height=1).pack(fill='x', pady=(0, 16))
        self.label(rail_bottom, 'G', size=12, color=CYAN, weight='bold').pack(side='left')
        profile = tk.Frame(rail_bottom, bg=rail.cget('bg'))
        profile.pack(side='left', padx=12)
        self.label(profile, 'Gowtham', size=10, color=TEXT).pack(anchor='w')
        self.label(profile, 'Personal workspace', size=8).pack(anchor='w')

        main = tk.Frame(self.root, bg=BG, padx=32, pady=26)
        main.grid(row=0, column=1, sticky='nsew')
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)
        header = tk.Frame(main, bg=BG)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 18))
        title = tk.Frame(header, bg=BG)
        title.pack(side='left')
        self.label(title, 'Assistant', size=21, color=TEXT, weight='bold').pack(anchor='w')
        self.label(title, 'A little ahead of your next thought.', size=10).pack(anchor='w', pady=(5, 0))
        self.label(header, variable=self.clock, size=9).pack(side='right', padx=(16, 0))
        self.button(header, 'Connection settings', self.open_settings, width=160, height=38).pack(side='right')

        content = tk.Frame(main, bg=BG)
        content.grid(row=1, column=0, sticky='nsew')
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        center = tk.Frame(content, bg=BG)
        center.grid(row=0, column=0, sticky='nsew', padx=(0, 28))
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)
        hour = datetime.now().hour
        greeting = 'Good morning' if hour < 12 else 'Good afternoon' if hour < 18 else 'Good evening'
        self.label(center, f'{greeting}, Gowtham.', size=11, color=MUTED).grid(row=0, column=0, pady=(8, 8))
        self.hero_title = self.label(center, 'Ready when you are.', size=28, color=TEXT, weight='bold')
        self.hero_title.grid(row=1, column=0)
        self.hud = tk.Canvas(center, bg=BG, height=340, highlightthickness=0)
        self.hud.grid(row=2, column=0, sticky='nsew', pady=(0, 0))
        state_row = tk.Frame(center, bg=BG)
        state_row.grid(row=3, column=0, pady=(0, 10))
        self.state_label = self.label(state_row, 'STANDBY', size=9, color=CYAN, weight='bold')
        self.state_label.pack()
        self.label(center, variable=self.status, size=10, color=MUTED, wraplength=460).grid(row=4, column=0, pady=(0, 16))
        suggestions = tk.Frame(center, bg=BG)
        suggestions.grid(row=5, column=0, sticky='ew', pady=(0, 12))
        suggestions.columnconfigure((0, 1), weight=1)
        self.button(suggestions, 'Open calculator', lambda: self.send('Open calculator'), width=180, height=38).grid(row=0, column=0, sticky='ew', padx=(0, 6))
        self.button(suggestions, 'Explain a concept', lambda: self.send('Ask me which concept I would like explained.'), width=180, height=38).grid(row=0, column=1, sticky='ew', padx=(6, 0))
        dock = tk.Frame(center, bg=PANEL, padx=14, pady=14, highlightthickness=1, highlightbackground=LINE)
        dock.grid(row=6, column=0, sticky='ew')
        dock.columnconfigure(0, weight=1)
        self.label(dock, 'MESSAGE ULTRON', size=8, color='#61748e').grid(row=0, column=0, sticky='w', pady=(0, 7))
        self.input = tk.Entry(dock, bg=PANEL, fg=TEXT, insertbackground=CYAN, font=('Segoe UI', 12), relief='flat', bd=0)
        self.input.grid(row=1, column=0, sticky='ew', ipady=8, padx=(0, 8))
        self.input.bind('<Return>', lambda event: self.send())
        self.button(dock, 'Send', self.send, True, width=66, height=38).grid(row=1, column=1)
        controls = tk.Frame(center, bg=BG)
        controls.grid(row=7, column=0, sticky='ew', pady=(12, 0))
        self.mute_button = self.button(controls, 'MUTE MICROPHONE', self.toggle_listening, width=150, height=36)
        self.mute_button.pack(side='left')
        self.label(controls, 'Say “Hey computer” to begin', size=9, color=MUTED).pack(side='right')

        stream = tk.Frame(content, bg=PANEL, width=318, padx=20, pady=20, highlightthickness=1, highlightbackground='#142032')
        stream.grid(row=0, column=1, sticky='nsew')
        stream.pack_propagate(False)
        stream_head = tk.Frame(stream, bg=PANEL)
        stream_head.pack(fill='x', pady=(0, 7))
        self.label(stream_head, 'Conversation', size=13, color=TEXT, weight='bold').pack(side='left')
        tk.Button(stream_head, text='Clear', command=self.clear, bg=PANEL, fg=MUTED,
                  activebackground=PANEL, activeforeground=CYAN, bd=0, relief='flat',
                  font=('Segoe UI', 9), cursor='hand2').pack(side='right')
        self.label(stream, 'Your current session', size=9).pack(anchor='w', pady=(0, 18))
        tk.Frame(stream, bg=LINE, height=1).pack(fill='x', pady=(0, 16))
        log_frame = tk.Frame(stream, bg=PANEL)
        log_frame.pack(fill='both', expand=True)
        self.log = tk.Text(log_frame, bg=PANEL, fg=TEXT, font=('Segoe UI', 11), wrap='word',
                           relief='flat', bd=0, highlightthickness=0, padx=0, pady=0, width=25)
        scrollbar = ttk.Scrollbar(log_frame, style='Dark.Vertical.TScrollbar', command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        for name, color in [('SYSTEM', MUTED), ('YOU', CYAN), ('ULTRON', TEXT), ('DESKTOP', BLUE), ('ISSUE', '#efb77c')]:
            self.log.tag_configure(name, foreground=color, spacing1=3, spacing3=6)
            self.log.tag_configure(name+'-title', foreground=color, font=('Segoe UI', 8, 'bold'), spacing1=10, spacing3=7)
        self.log.configure(state='disabled')
        stream_foot = tk.Frame(stream, bg=PANEL)
        stream_foot.pack(fill='x', pady=(14, 0))
        self.label(stream_foot, 'History clears when the app closes.', size=8).pack(anchor='w')
        footer = tk.Frame(main, bg=BG)
        footer.grid(row=2, column=0, sticky='ew', pady=(20, 0))
        self.label(footer, 'LOCAL VOICE  ·  ENCRYPTED KEYS', size=8, color='#536983').pack(side='left')
        self.label(footer, variable=self.uptime, size=8, color='#536983').pack(side='right')
        self.build_settings()

    def focus_assistant(self):
        self.settings_window.withdraw()
        self.input.focus_set()

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

    def write(self, speaker, text):
        self.log.configure(state='normal')
        self.log.insert('end', f'{speaker.title()}  ·  {datetime.now():%H:%M}\n', speaker+'-title')
        self.log.insert('end', str(text)+'\n\n', speaker)
        self.log.see('end')
        self.log.configure(state='disabled')

    def render_orb(self, width, height):
        scale = 2
        radius = min(150, height*0.39, width*0.25)
        cx, cy = width/2, height/2
        key = (width, height, round(radius))
        if getattr(self, '_orb_key', None) != key:
            base = Image.new('RGB', (width*scale, height*scale), BG)
            glow = Image.new('RGB', base.size, '#000000')
            gd = ImageDraw.Draw(glow)
            gd.ellipse(((cx-radius*1.08)*scale, (cy-radius*1.08)*scale,
                        (cx+radius*1.08)*scale, (cy+radius*1.08)*scale), fill='#0b3d63')
            glow = glow.filter(ImageFilter.GaussianBlur(radius*0.35*scale))
            from PIL import ImageChops
            base = ImageChops.add(base, glow)
            draw = ImageDraw.Draw(base)
            # A cached spherical light field gives the live geometry a smooth volume.
            pixels = base.load()
            rpx = radius*scale
            for py in range(int((cy-radius)*scale), int((cy+radius)*scale)):
                ny = (py-cy*scale)/rpx
                for px in range(int((cx-radius)*scale), int((cx+radius)*scale)):
                    nx = (px-cx*scale)/rpx
                    distance = nx*nx+ny*ny
                    if distance < 1:
                        z = math.sqrt(1-distance)
                        light = max(0, -0.38*nx-0.52*ny+0.72*z)
                        highlight = light**12
                        rim = (1-z)**3
                        pixels[px,py] = (int(5+7*z+18*highlight+9*rim),
                                         int(19+17*z+72*highlight+49*rim),
                                         int(35+23*z+103*highlight+71*rim))
            self._orb_base = base
            self._orb_key = key
        image = self._orb_base.copy()
        draw = ImageDraw.Draw(image)
        rotation = math.radians(self.phase)
        tilt = 0.32
        def project(x, y, z):
            x, z = x*math.cos(rotation)+z*math.sin(rotation), -x*math.sin(rotation)+z*math.cos(rotation)
            y, z = y*math.cos(tilt)-z*math.sin(tilt), y*math.sin(tilt)+z*math.cos(tilt)
            perspective = 1+z*0.13
            return ((cx+x*radius*perspective)*scale, (cy+y*radius*perspective)*scale, z)
        segments = []
        for latitude in range(-75, 76, 15):
            b = math.radians(latitude)
            points = [project(math.cos(b)*math.cos(a*math.tau/72), math.sin(b), math.cos(b)*math.sin(a*math.tau/72)) for a in range(73)]
            segments.extend((points[i], points[i+1]) for i in range(72))
        for meridian in range(0, 360, 20):
            a = math.radians(meridian)
            points = [project(math.cos(b*math.pi/48)*math.cos(a), math.sin(b*math.pi/48), math.cos(b*math.pi/48)*math.sin(a)) for b in range(-24, 25)]
            segments.extend((points[i], points[i+1]) for i in range(48))
        segments.sort(key=lambda pair: pair[0][2]+pair[1][2])
        for p, q in segments:
            depth = (p[2]+q[2])/2
            light = max(0, depth)
            color = (int(23+light*96), int(48+light*155), int(73+light*180)) if depth > 0 else (13, 35, 54)
            draw.line((p[0], p[1], q[0], q[1]), fill=color, width=scale)
        for index in range(36):
            a = index*math.tau/36+rotation*0.5
            b = math.sin(index*2.4)*1.12
            p = project(math.cos(b)*math.cos(a), math.sin(b), math.cos(b)*math.sin(a))
            if p[2] > 0.15:
                r = 1.2*scale
                draw.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r), fill='#bcefff')
        for index in range(420):
            y = 1-2*(index+0.5)/420
            belt = math.sqrt(1-y*y)
            a = index*2.39996323
            p = project(belt*math.cos(a), y, belt*math.sin(a))
            if p[2] > 0.05:
                r = (0.3+0.35*p[2])*scale
                color = (int(35+75*p[2]), int(94+112*p[2]), int(130+120*p[2]))
                draw.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r), fill=color)
        orbit_layer = Image.new('RGBA', image.size)
        od = ImageDraw.Draw(orbit_layer)
        for orbit, angle in [(1.40, 0.22), (1.52, -0.4)]:
            points = []
            for i in range(145):
                a = i*math.tau/144
                x, y = math.cos(a)*radius*orbit, math.sin(a)*radius*0.37
                points.append(((cx+x*math.cos(angle)-y*math.sin(angle))*scale,
                               (cy+x*math.sin(angle)+y*math.cos(angle))*scale))
            od.line(points, fill=(70, 146, 205, 105), width=scale)
            position = points[int(self.phase*(0.7 if angle>0 else -0.6)) % 144]
            r = 2*scale
            od.ellipse((position[0]-r,position[1]-r,position[0]+r,position[1]+r), fill=(168,234,255,255))
        aura = orbit_layer.filter(ImageFilter.GaussianBlur(3*scale))
        image = Image.alpha_composite(image.convert('RGBA'), aura)
        image = Image.alpha_composite(image, orbit_layer)
        return image.resize((width,height), Image.Resampling.LANCZOS)

    def animate(self):
        if self.closing:
            return
        started = time.monotonic()
        self.phase += 1.2 if self.state in ('THINKING', 'SPEAKING') else 0.6
        self.clock.set(datetime.now().strftime('%H:%M  ·  %d %b'))
        seconds = int(time.monotonic()-self.started)
        self.uptime.set(f'Session {seconds//60:02d}:{seconds%60:02d}  ·  {self.commands} commands')
        self.state_label.configure(text={'LISTENING': '●  Listening', 'MUTED': 'Microphone paused',
            'CAPTURING': '●  Voice detected', 'THINKING': 'Processing your request',
            'SPEAKING': 'Ultron is speaking', 'PROCESSING': 'Preparing', 'STANDBY': 'Ready'}.get(self.state, self.state))
        self.hero_title.configure(text={'CAPTURING': 'I’m listening.', 'THINKING': 'Connecting the dots.',
            'SPEAKING': 'Consider it handled.', 'MUTED': 'A moment of quiet.'}.get(self.state, 'Ready when you are.'))
        width = max(self.hud.winfo_width(), 260)
        height = max(self.hud.winfo_height(), 220)
        image = self.render_orb(width, height)
        if getattr(self, '_orb_photo', None) and getattr(self, '_photo_size', None) == image.size:
            self._orb_photo.paste(image)
        else:
            self._orb_photo = ImageTk.PhotoImage(image)
            self._photo_size = image.size
            self.hud.delete('all')
            self.hud.create_image(0, 0, anchor='nw', image=self._orb_photo)
        self.hud.delete('meter')
        self.levels = self.levels[1:]+[self.level if self.state in ('LISTENING','CAPTURING') else 0.0]
        for i, level in enumerate(self.levels):
            bar = max(2, level*18)
            x = width/2-62+i*4
            self.hud.create_line(x, height-13-bar/2, x, height-13+bar/2,
                                  width=2, fill=CYAN if level>0.07 else '#263e55', tags='meter')
        elapsed = int((time.monotonic()-started)*1000)
        self.root.after(max(15, 80-elapsed), self.animate)
