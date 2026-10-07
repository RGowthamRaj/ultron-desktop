import io
import json
import threading
import queue
import sys
from types import SimpleNamespace
import unittest
import wave
from unittest.mock import Mock, patch

from ultron.actions import execute, TOOLS
from ultron.audio import Listener, is_wake, rms, to_wav
from ultron.cloud import Cloud, validate_endpoint, PRESETS


class AudioTests(unittest.TestCase):
    def test_wake_requires_exact_phrase(self):
        self.assertTrue(is_wake(' Hey Computer '))
        for text in ['computer', 'hey', 'turn on the computer', 'hey computer open calculator', '[unk]']:
            self.assertFalse(is_wake(text))

    def test_wav_is_mono_pcm_16khz(self):
        samples = b'\x00\x00' * 1600
        self.assertEqual(rms(samples), 0)
        with wave.open(io.BytesIO(to_wav([samples])), 'rb') as result:
            self.assertEqual((result.getnchannels(), result.getsampwidth(), result.getframerate()), (1, 2, 16000))
            self.assertEqual(result.readframes(1600), samples)


class ActionTests(unittest.TestCase):
    def test_arbitrary_commands_rejected(self):
        for name in ['shell', 'delete_file', 'send_email']:
            with self.assertRaises(ValueError):
                execute(name, {'command': 'anything'})
        with self.assertRaises(ValueError):
            execute('open_app', {'app': 'cmd.exe /c anything'})

    @patch('ultron.actions.webbrowser.open', return_value=True)
    def test_search_is_encoded_as_query_not_executable(self, browser):
        execute('search_web', {'query': 'a & b / $(anything)'})
        self.assertIn('q=a+%26+b+%2F+%24%28anything%29', browser.call_args.args[0])

    def test_invalid_media_and_queries_rejected(self):
        for query in ['', 'x' * 501, None]:
            with self.assertRaises(ValueError):
                execute('search_web', {'query': query})
        with self.assertRaises(ValueError):
            execute('media_control', {'action': 'shutdown'})

    def test_tool_schemas_are_strict(self):
        for tool in TOOLS:
            self.assertTrue(tool['strict'])
            self.assertFalse(tool['parameters']['additionalProperties'])


def message(text):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}}]}


def call(name='open_app', args='{"app":"calculator"}'):
    return {'choices': [{'message': {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': 'call1', 'type': 'function',
                            'function': {'name': name, 'arguments': args}}]}}]}


class CloudTests(unittest.TestCase):
    @patch('ultron.cloud.execute', return_value='Opened calculator.')
    def test_tool_result_is_returned_before_reply(self, action):
        cloud = Cloud('test-key')
        cloud.request = Mock(side_effect=[call(), message('Calculator opened.')])
        self.assertEqual(cloud.reply('Open calculator', lambda: False, lambda *args: None), 'Calculator opened.')
        action.assert_called_once_with('open_app', {'app': 'calculator'})
        second = cloud.request.call_args_list[1].args[0]['messages']
        self.assertTrue(any(item.get('role') == 'tool' for item in second))
        self.assertEqual(cloud.request.call_args.args[0]['tool_choice'], 'auto')


    @patch('ultron.cloud.execute', side_effect=ValueError('Unsupported action'))
    def test_action_failure_is_reported_to_model(self, action):
        cloud = Cloud('test-key')
        cloud.request = Mock(side_effect=[call('shell', '{}'), message('I cannot run that command.')])
        cloud.reply('Run a command', lambda: False, lambda *args: None)
        payload = cloud.request.call_args.args[0]['messages']
        self.assertIn('Action failed', next(item['content'] for item in payload if item.get('role') == 'tool'))

    def test_nvidia_uses_chat_schema_and_preserves_model(self):
        endpoint, model = PRESETS['NVIDIA Nemotron']
        cloud = Cloud('nvidia-key', model, endpoint)
        cloud.request = Mock(return_value=message('Ready.'))
        self.assertEqual(cloud.reply('Hello', lambda: False, lambda *args: None), 'Ready.')
        payload = cloud.request.call_args.args[0]
        self.assertEqual(payload['model'], model)
        self.assertFalse(payload['stream'])
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertIn('parameters', payload['tools'][0]['function'])

    def test_tools_can_be_disabled_for_chat_only_models(self):
        cloud = Cloud('key', 'custom-model', 'https://example.com/v1', tools_enabled=False)
        self.assertNotIn('tools', cloud.payload([]))

    def test_internal_reasoning_is_not_spoken(self):
        cloud = Cloud('key')
        cloud.request = Mock(return_value=message('<think>private</think> Hello.'))
        self.assertEqual(cloud.reply('Hi', lambda: False, lambda *args: None), 'Hello.')

    def test_endpoints_validate_transport_and_normalize(self):
        self.assertEqual(validate_endpoint('https://example.com/v1/chat/completions/'), 'https://example.com/v1')
        self.assertEqual(validate_endpoint('http://localhost:11434/v1'), 'http://localhost:11434/v1')
        for bad in ['file:///secrets', 'http://example.com/v1', 'https://key@example.com/v1',
                    'https://example.com/v1?key=secret', 'https://example.com/v1#fragment']:
            with self.assertRaises(ValueError):
                validate_endpoint(bad)




    @patch('ultron.cloud.execute')
    def test_unexpected_tools_never_execute_when_disabled(self, action):
        cloud = Cloud('key', tools_enabled=False)
        cloud.request = Mock(side_effect=[call(), message('Desktop tools are disabled.')])
        cloud.reply('Open calculator', lambda: False, lambda *args: None)
        action.assert_not_called()

    def test_request_routes_key_to_configured_provider(self):
        cloud = Cloud('fake-nvidia-key', 'custom-model', 'https://integrate.api.nvidia.com/v1')
        response = Mock()
        response.status = 200
        response.read.return_value = json.dumps(message('Hello.')).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = context
        with patch('ultron.cloud.build_opener', return_value=opener):
            cloud.request(cloud.payload([]))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://integrate.api.nvidia.com/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fake-nvidia-key')


if __name__ == '__main__':
    unittest.main()
