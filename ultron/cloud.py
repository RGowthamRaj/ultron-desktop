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


class Cloud:
    def __init__(self, key, model='gpt-4.1-mini', base_url='https://api.openai.com/v1', tools_enabled=True):
        self.key = key.strip()
        self.model = model.strip()
        self.base_url = validate_endpoint(base_url)
        if not self.model:
            raise ValueError('Enter the model ID provided by your API provider.')
        self.tools_enabled = tools_enabled
        self.history = []

    def request(self, payload):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        request = Request(self.base_url + '/chat/completions', data=json.dumps(payload).encode(), headers=headers)
        try:
            with build_opener(NoRedirect()).open(request, timeout=60) as response:
                if response.status != 200:
                    raise RuntimeError(f'Provider returned HTTP {response.status}; request was not completed.')
                return json.loads(response.read())
        except HTTPError as exc:
            messages = {401: 'API key rejected. Select the matching provider and check the key.',
                        429: 'Provider usage limit reached. Check your allowance or try later.',
                        403: 'This key does not have access to the selected model.',
                        404: 'Model or endpoint not found. Check the base URL and model ID.',
                        400: 'Provider rejected the request. Check the model, or disable desktop tools if unsupported.',
                        422: 'Provider rejected the request format or model. Try disabling desktop tools.'}
            raise RuntimeError(messages.get(exc.code, f'Provider request failed (HTTP {exc.code}).')) from None
        except (URLError, TimeoutError):
            raise RuntimeError('Cannot reach the AI provider. Listening will continue; try again later.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError('The endpoint did not return compatible JSON. Check its base URL.') from None

    def payload(self, messages):
        result = {'model': self.model, 'messages': messages, 'stream': False, 'max_tokens': 1024}
        if self.tools_enabled:
            result['tools'] = [{'type': 'function', 'function': {key: value for key, value in tool.items()
                                      if key not in ('type', 'strict')}} for tool in TOOLS]
            result['tool_choice'] = 'auto'
        if urlsplit(self.base_url).hostname == 'integrate.api.nvidia.com' and 'nemotron' in self.model:
            result['chat_template_kwargs'] = {'enable_thinking': False}
        return result


