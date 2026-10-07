"""Provider-neutral OpenAI-compatible chat; speech stays on the desktop."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .actions import TOOLS, execute

PRESETS = {
    'NVIDIA Nemotron': ('https://integrate.api.nvidia.com/v1', 'nvidia/nemotron-3.5-lightning-30b-a3b'),
    'OpenAI': ('https://api.openai.com/v1', 'gpt-4.1-mini'),
    'Custom compatible API': ('https://your-provider.example/v1', ''),
}
INSTRUCTIONS = '''You are Ultron, a personal Windows assistant with a JARVIS-inspired manner:
calm, intelligent, concise, lightly witty, and respectful. Keep spoken replies brief.
Use supplied tools for desktop actions and report only what their results support.
You can open supported apps, open browser search results, and control media keys.
You cannot read screens or search results, send messages, modify files, or run arbitrary commands.
Ask for clarification when needed. Never invent actions or capabilities. Your voice is synthetic.
Do not include internal reasoning or think tags in the final response.'''


def validate_endpoint(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.scheme not in ('http', 'https')):
        raise ValueError('Use a base URL such as https://integrate.api.nvidia.com/v1.')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use HTTPS for remote providers; HTTP is supported only on localhost.')
    if value.endswith('/chat/completions'):
        value = value[:-len('/chat/completions')]
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('The API redirected the request. Check the configured base URL.')


