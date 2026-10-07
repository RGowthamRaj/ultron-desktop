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




if __name__ == '__main__':
    unittest.main()
