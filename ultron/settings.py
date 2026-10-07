"""Preferences with optional Windows-account-encrypted credentials."""
import base64
import ctypes
import json
import os
from pathlib import Path
from .cloud import PRESETS
SETTINGS_PATH = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming'))) / 'Ultron/settings.json'


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    fn.restype = ctypes.c_int
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('Windows could not access encrypted credentials.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def load(path=SETTINGS_PATH):
    provider = 'OpenAI' if os.environ.get('OPENAI_API_KEY') else 'NVIDIA Nemotron'
    base, model = PRESETS[provider]
    config = {'provider': provider, 'base_url': base, 'model': os.environ.get('ULTRON_MODEL', model),
              'key': os.environ.get('OPENAI_API_KEY', '') if provider == 'OpenAI' else os.environ.get('NVIDIA_API_KEY', ''),
              'remember': True, 'speech': True, 'tools': True, 'autolisten': True}
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        for key in ('provider', 'base_url', 'model', 'remember', 'speech', 'tools', 'autolisten'):
            if key in saved:
                config[key] = saved[key]
        if saved.get('encrypted_key'):
            config['key'] = protect(base64.b64decode(saved['encrypted_key']), decrypt=True).decode()
    except FileNotFoundError:
        pass
    except Exception:
        config['notice'] = 'Saved settings could not be loaded. Please enter your connection again.'
        config['key'] = ''
    return config


def save(config, path=SETTINGS_PATH):
    saved = {key: config[key] for key in ('provider', 'base_url', 'model', 'remember', 'speech', 'tools', 'autolisten')}
    if config['remember'] and config['key']:
        saved['encrypted_key'] = base64.b64encode(protect(config['key'].encode())).decode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(saved, indent=2), encoding='utf-8')
    temporary.replace(path)
