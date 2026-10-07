"""Fixed desktop capabilities: no model-generated shell commands."""
import ctypes
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlencode


APP_NAMES = ['notepad', 'calculator', 'explorer', 'browser', 'vscode', 'chrome', 'edge', 'spotify']


def tool(name, description, property_name, property_schema):
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': {property_name: property_schema},
                           'required': [property_name], 'additionalProperties': False}}


TOOLS = [
    tool('open_app', 'Open a supported desktop application.', 'app', {'type': 'string', 'enum': APP_NAMES}),
    tool('search_web', 'Open web search results in the default browser. This does not read results.',
         'query', {'type': 'string'}),
    tool('media_control', 'Control system volume or media playback.', 'action',
         {'type': 'string', 'enum': ['volume_up', 'volume_down', 'mute_toggle', 'play_pause', 'next_track']}),
]


def execute(name, arguments):
    if name == 'search_web':
        query = arguments.get('query')
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise ValueError('Search query must contain 1–500 characters.')
        opened = webbrowser.open('https://www.google.com/search?' + urlencode({'q': query}))
        if not opened:
            raise RuntimeError('Windows could not open the browser.')
        return 'Opened search results. Their contents have not been read.'
    if name == 'open_app':
        app = arguments.get('app')
        if app not in APP_NAMES:
            raise ValueError('Unsupported application.')
        if app == 'browser':
            if not webbrowser.open('https://www.google.com'):
                raise RuntimeError('Windows could not open the browser.')
        elif app == 'spotify':
            os.startfile('spotify:')
        else:
            system = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32'
            local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
            program = Path(os.environ.get('PROGRAMFILES', r'C:\Program Files'))
            program_x86 = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'))
            candidates = {
                'notepad': [system / 'notepad.exe'],
                'calculator': [system / 'calc.exe'],
                'explorer': [system.parent / 'explorer.exe'],
                'vscode': [local / 'Programs/Microsoft VS Code/Code.exe', program / 'Microsoft VS Code/Code.exe'],
                'chrome': [program / 'Google/Chrome/Application/chrome.exe', local / 'Google/Chrome/Application/chrome.exe'],
                'edge': [program_x86 / 'Microsoft/Edge/Application/msedge.exe', program / 'Microsoft/Edge/Application/msedge.exe'],
            }[app]
            executable = next((str(p) for p in candidates if p.is_file()), None)
            if not executable:
                raise FileNotFoundError(f'{app} is not installed in a supported location.')
            subprocess.Popen([executable])
        return f'Requested opening {app}.'
    if name == 'media_control':
        keys = {'volume_up': 0xAF, 'volume_down': 0xAE, 'mute_toggle': 0xAD,
                'play_pause': 0xB3, 'next_track': 0xB0}
        action = arguments.get('action')
        if action not in keys:
            raise ValueError('Unsupported media action.')
        ctypes.windll.user32.keybd_event(keys[action], 0, 0, 0)
        ctypes.windll.user32.keybd_event(keys[action], 0, 2, 0)
        return f'Sent {action} media key; response depends on the active player.'
    raise ValueError('Unknown desktop action.')
