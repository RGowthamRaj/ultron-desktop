"""Offline regression checks: never contact a provider or dispatch desktop actions."""
import json
import unittest
from unittest.mock import Mock, patch

from ultron.actions import execute
from evals.sandbox import action_sandbox
from ultron.cloud import Cloud, PRESETS


def answer(text='Ready.', finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': text}}]}


def tool_response(ids=('call1',), finish='tool_calls'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': None, 'tool_calls': [
        {'id': value, 'type': 'function', 'function': {
            'name': 'open_app', 'arguments': '{"app":"calculator"}'}}
        for value in ids]}}]}


class CloudSafetyTests(unittest.TestCase):
    def reply(self, cloud, text='Hello'):
        return cloud.reply(text, lambda: False, lambda *args: None)

    def test_openai_default_is_luna_without_reasoning(self):
        cloud = Cloud('fake-key')
        self.assertEqual(PRESETS['OpenAI'][1], 'gpt-6-luna')
        payload = cloud.payload([])
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(payload['max_completion_tokens'], 512)
        self.assertNotIn('max_tokens', payload)
        self.assertEqual(payload['verbosity'], 'low')

    def test_strict_survives_openai_wire_conversion(self):
        payload = Cloud('fake-key').payload([])
        for tool in payload['tools']:
            self.assertTrue(tool['function']['strict'])
        self.assertFalse(payload['parallel_tool_calls'])

    def test_custom_payload_does_not_receive_openai_settings(self):
        payload = Cloud('fake-key', 'custom-model', 'https://example.com/v1').payload([])
        self.assertNotIn('reasoning_effort', payload)
        self.assertNotIn('verbosity', payload)
        self.assertNotIn('strict', payload['tools'][0]['function'])
        self.assertEqual(payload['max_tokens'], 1024)

    def test_gemini_uses_low_thinking(self):
        endpoint, model = PRESETS['Gemini 4 Argon']
        self.assertEqual(Cloud('fake-key', model, endpoint).payload([])['reasoning_effort'], 'low')

    def test_provider_detection_requires_exact_hostname(self):
        cloud = Cloud('fake-key', 'custom-model', 'https://generativelanguage.googleapis.com.attacker.example/v1')
        self.assertNotIn('reasoning_effort', cloud.payload([]))

    def test_saved_legacy_model_is_preserved(self):
        cloud = Cloud('fake-key', 'gpt-4.1-mini')
        self.assertEqual(cloud.payload([])['model'], 'gpt-4.1-mini')
        self.assertNotIn('reasoning_effort', cloud.payload([]))

    def test_incompatible_openai_tool_model_is_rejected_before_network(self):
        cloud = Cloud('fake-key', 'gpt-6.1-sol')
        cloud.request = Mock()
        with self.assertRaisesRegex(ValueError, 'Responses'):
            self.reply(cloud)
        cloud.request.assert_not_called()

    def test_truncated_final_text_is_not_accepted_or_retained(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=answer('Partial answer', 'length'))
        with self.assertRaisesRegex(RuntimeError, 'output limit'):
            self.reply(cloud)
        self.assertEqual(cloud.history, [])

    @patch('ultron.cloud.execute')
    def test_truncated_tool_call_never_executes(self, action):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=tool_response(finish='length'))
        with self.assertRaises(RuntimeError):
            self.reply(cloud)
        action.assert_not_called()

    @patch('ultron.cloud.execute')
    def test_duplicate_tool_ids_never_execute(self, action):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=tool_response(('same', 'same')))
        with self.assertRaisesRegex(RuntimeError, 'ID'):
            self.reply(cloud)
        action.assert_not_called()

    @patch('ultron.cloud.execute')
    def test_oversized_tool_batch_never_executes(self, action):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=tool_response(tuple(str(i) for i in range(9))))
        with self.assertRaisesRegex(RuntimeError, 'action limit'):
            self.reply(cloud)
        action.assert_not_called()

    def test_connection_check_requires_expected_text(self):
        for response in [answer(''), answer('Unexpected'), answer('OK', 'length'), tool_response()]:
            with self.subTest(response=response):
                cloud = Cloud('fake-key')
                cloud.request = Mock(return_value=response)
                with self.assertRaises(RuntimeError):
                    cloud.check()

    def test_connection_check_uses_model_settings_without_tools(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=answer('OK'))
        cloud.check()
        payload = cloud.request.call_args.args[0]
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertNotIn('tools', payload)
        self.assertNotIn('max_tokens', payload)

    def test_reasoning_is_removed_from_retained_history(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=answer('<think>private analysis</think> Hello.'))
        self.assertEqual(self.reply(cloud), 'Hello.')
        self.assertNotIn('private analysis', json.dumps(cloud.history))

    @patch('ultron.actions.subprocess.Popen')
    def test_extra_tool_arguments_are_rejected_locally(self, launch):
        with self.assertRaises(ValueError):
            execute('open_app', {'app': 'calculator', 'command': 'anything'})
        launch.assert_not_called()

    def test_oversized_input_is_rejected_before_network(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock()
        with self.assertRaises(ValueError):
            self.reply(cloud, 'x' * 8001)
        cloud.request.assert_not_called()

    def test_history_budget_evicts_whole_turns(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=answer('x' * 4000))
        for _ in range(6):
            self.reply(cloud, 'x' * 4000)
        self.assertLessEqual(len(json.dumps(cloud.history, ensure_ascii=False)), 24000)
        for turn in cloud.history:
            self.assertEqual(turn[0]['role'], 'user')
            self.assertEqual(turn[-1]['role'], 'assistant')

    @patch('ultron.cloud.execute', return_value='Requested opening calculator.')
    def test_metrics_include_all_rounds_without_transcript(self, action):
        cloud = Cloud('fake-key')
        first, second = tool_response(), answer('Requested opening Calculator.')
        for response in (first, second):
            response['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10,
                                 'prompt_tokens_details': {'cached_tokens': 20},
                                 'completion_tokens_details': {'reasoning_tokens': 0}}
        cloud.request = Mock(side_effect=[first, second])
        self.reply(cloud, 'Open calculator')
        metrics = cloud.last_metrics
        self.assertEqual(metrics['requests'], 2)
        self.assertEqual(metrics['input_tokens'], 200)
        self.assertEqual(metrics['output_tokens'], 20)
        self.assertEqual(metrics['cached_input_tokens'], 40)
        self.assertEqual(metrics['actions'], 1)
        self.assertGreaterEqual(metrics['elapsed_ms'], 0)
        self.assertTrue(metrics['usage_complete'])
        self.assertNotIn('calculator', json.dumps(metrics))

    def test_local_button_action_uses_no_provider_requests(self):
        # Reuse this fail-closed mock boundary in the opt-in live harness.
        with action_sandbox() as action:
            cloud = Cloud('fake-key')
            cloud.request = Mock()
            result = cloud.open_local_app('calculator', lambda: False, lambda *args: None)
            self.assertEqual(result, 'Requested opening calculator.')
            cloud.request.assert_not_called()
            action.assert_called_once_with('open_app', {'app': 'calculator'})
            self.assertEqual(cloud.last_metrics['requests'], 0)
            self.assertEqual(len(cloud.history), 1)

    @patch('ultron.cloud.execute')
    def test_local_buttons_respect_tools_disabled_and_stop(self, action):
        cloud = Cloud('fake-key', tools_enabled=False)
        self.assertIn('disabled', cloud.open_local_app('calculator', lambda: False, lambda *args: None))
        cloud = Cloud('fake-key')
        self.assertEqual(cloud.open_local_app('calculator', lambda: True, lambda *args: None), '')
        action.assert_not_called()

    def test_disabled_tools_are_explicit_in_instructions(self):
        cloud = Cloud('fake-key', tools_enabled=False)
        cloud.request = Mock(return_value=answer())
        self.reply(cloud)
        payload = cloud.request.call_args.args[0]
        self.assertIn('Desktop tools are disabled', payload['messages'][0]['content'])
        self.assertNotIn('tools', payload)

    @patch('ultron.cloud.execute', return_value='Requested opening calculator.')
    def test_cancelled_batch_keeps_matched_tool_results(self, action):
        stopped = [False]
        def dispatch(*args):
            stopped[0] = True
            return 'Requested opening calculator.'
        action.side_effect = dispatch
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=tool_response(('first', 'second')))
        self.assertEqual(cloud.reply('Open calculator and browser', lambda: stopped[0], lambda *args: None), '')
        action.assert_called_once()
        results = {item['tool_call_id']: item['content'] for item in cloud.history[0]
                   if item.get('role') == 'tool'}
        self.assertEqual(set(results), {'first', 'second'})
        self.assertIn('Not executed', results['second'])

    @patch('ultron.cloud.execute', return_value='Requested opening calculator.')
    def test_missing_usage_details_stay_unknown_across_rounds(self, action):
        cloud = Cloud('fake-key')
        first, second = tool_response(), answer()
        first['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10}
        second['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10,
                           'prompt_tokens_details': {'cached_tokens': 5}}
        cloud.request = Mock(side_effect=[first, second])
        self.reply(cloud)
        self.assertIsNone(cloud.last_metrics['cached_input_tokens'])
        self.assertIsNone(cloud.last_metrics['reasoning_tokens'])
        self.assertEqual(cloud.last_metrics['input_tokens'], 200)

    def test_missing_usage_is_not_reported_as_measured_zero(self):
        cloud = Cloud('fake-key')
        cloud.request = Mock(return_value=answer())
        self.reply(cloud)
        self.assertFalse(cloud.last_metrics['usage_complete'])
        self.assertIsNone(cloud.last_metrics['cached_input_tokens'])
        self.assertIsNone(cloud.last_metrics['reasoning_tokens'])

    @patch('ultron.cloud.execute')
    def test_malformed_function_batch_rejected_before_any_action(self, action):
        cloud = Cloud('fake-key')
        response = tool_response(('first', 'second'))
        del response['choices'][0]['message']['tool_calls'][1]['function']
        cloud.request = Mock(return_value=response)
        with self.assertRaisesRegex(RuntimeError, 'malformed'):
            self.reply(cloud)
        action.assert_not_called()

    @patch('ultron.cloud.execute', return_value='Requested opening calculator.')
    def test_reused_id_across_rounds_does_not_dispatch_twice(self, action):
        cloud = Cloud('fake-key')
        cloud.request = Mock(side_effect=[tool_response(), tool_response()])
        with self.assertRaisesRegex(RuntimeError, 'ID'):
            self.reply(cloud)
        action.assert_called_once()

    def test_oversized_provider_response_is_bounded(self):
        from ultron.cloud import MAX_RESPONSE_BYTES
        response = Mock(status=200)
        response.read.return_value = b'x' * (MAX_RESPONSE_BYTES + 1)
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = context
        with patch('ultron.cloud.build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'size limit'):
                Cloud('fake-key').request({})
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)


if __name__ == '__main__':
    unittest.main()
