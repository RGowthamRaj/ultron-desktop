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


