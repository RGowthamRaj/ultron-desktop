"""Provider-neutral OpenAI-compatible chat; speech stays on the desktop."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .actions import TOOLS, execute

PRESETS = {
    'Gemini 4 Argon': ('https://generativelanguage.googleapis.com/v1beta/openai', 'gemini-4-argon'),
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
        hostname = urlsplit(self.base_url).hostname or ''
        is_gemini = 'generativelanguage.googleapis.com' in hostname
        is_nemotron = hostname == 'integrate.api.nvidia.com' and 'nemotron' in self.model
        # Gemini 4 Argon supports larger context; give it more room
        max_tokens = 2048 if is_gemini else 1024
        result = {'model': self.model, 'messages': messages, 'stream': False, 'max_tokens': max_tokens}
        if self.tools_enabled and not is_gemini:
            # Gemini's OpenAI-compat layer doesn't always support tool_choice=auto; skip it
            result['tools'] = [{'type': 'function', 'function': {key: value for key, value in tool.items()
                                      if key not in ('type', 'strict')}} for tool in TOOLS]
            result['tool_choice'] = 'auto'
        elif self.tools_enabled and is_gemini:
            result['tools'] = [{'type': 'function', 'function': {key: value for key, value in tool.items()
                                      if key not in ('type', 'strict')}} for tool in TOOLS]
            # Gemini infers tool use from context; tool_choice omitted intentionally
        if is_nemotron:
            result['chat_template_kwargs'] = {'enable_thinking': False}
        return result

    def check(self):
        response = self.request({'model': self.model, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
                                 'stream': False, 'max_tokens': 128})
        if not response.get('choices'):
            raise RuntimeError('Provider returned no chat choices. Check model compatibility.')
        return 'Connection verified. Model is reachable.'

    def reply(self, text, stopped, report):
        messages = [{'role': 'system', 'content': INSTRUCTIONS}]
        messages += [item for turn in self.history[-6:] for item in turn]
        turn = [{'role': 'user', 'content': text}]
        messages += turn

        def record_partial_turn():
            if any(item.get('role') == 'tool' for item in turn) and turn not in self.history:
                self.history.append(turn)
                self.history = self.history[-6:]

        try:
            for _ in range(4):
                if stopped():
                    record_partial_turn()
                    return ''
                response = self.request(self.payload(messages))
                if stopped():
                    record_partial_turn()
                    return ''
                try:
                    raw = response['choices'][0]['message']
                    message = {'role': 'assistant', 'content': raw.get('content') or ''}
                    calls = raw.get('tool_calls') or []
                    if calls:
                        message['tool_calls'] = calls
                except (KeyError, IndexError, TypeError):
                    raise RuntimeError('Provider returned an incompatible chat response.') from None
                turn.append(message)
                messages.append(message)
                if not calls:
                    answer = re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', message['content'], flags=re.S).strip()
                    if not answer or '<think' in answer:
                        raise RuntimeError('Model produced no final answer. Use an instruct model or a larger output budget.')
                    self.history.append(turn)
                    self.history = self.history[-6:]
                    return answer
                for call in calls:
                    if stopped():
                        record_partial_turn()
                        return ''
                    if not call.get('id'):
                        raise RuntimeError('Provider returned a tool call without an ID.')
                    try:
                        if not self.tools_enabled:
                            raise ValueError('Desktop tools are disabled.')
                        function = call['function']
                        args = json.loads(function['arguments'])
                        if not isinstance(args, dict):
                            raise ValueError('Invalid tool arguments.')
                        result = execute(function['name'], args)
                    except Exception as exc:
                        result = f'Action failed: {exc}'
                    report('action', result)
                    item = {'role': 'tool', 'tool_call_id': call['id'], 'content': result}
                    messages.append(item)
                    turn.append(item)
            record_partial_turn()
            return 'That sequence is too long. Please request one task at a time.'
        except Exception:
            record_partial_turn()
            raise
