"""Harness safety tests: all transports and desktop actions are mocked."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evals import live
from evals.sandbox import action_sandbox
from ultron.cloud import Cloud


def answer(text='Ready.', usage=True):
    result = {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}
    if usage:
        result['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}
    return result


def call(name='open_app', args=None, id='call1'):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None, 'tool_calls': [
        {'id': id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args or {'app': 'calculator'})}}
    ]}}]}


class LiveEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.configs = live.load_configs(live.HERE / 'config.example.json')
        for config in self.configs:
            config.update(input_usd_per_million=1, output_usd_per_million=2)
        self.fixtures = json.loads((live.HERE / 'fixtures.json').read_text())
        self.config = self.configs[2]

    def budget(self, **kwargs):
        return live.Budget(kwargs.get('usd', 100), kwargs.get('requests', 576), 60)

    def fixture(self, id):
        return next(f for f in self.fixtures if f['id'] == id)

    def test_offline_plan_has_exact_categories_and_144_conversations(self):
        from collections import Counter
        self.assertEqual(Counter(f['category'] for f in self.fixtures),
                         dict(supported=6, ambiguous=4, unsupported=4, failure=4, explanation=4, context=2))
        self.assertEqual(len({f['id'] for f in self.fixtures}), 24)
        with patch.object(Cloud, 'request', side_effect=AssertionError('network')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(live.main(['plan']), 0)
        self.assertEqual(live.plan(self.configs, self.fixtures, 2)['provider_requests_upper_bound'], 576)

    def test_run_needs_both_approvals_before_credentials_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for flags in ([], ['--live'], ['--approve-usd', '1']):
                out = Path(tmp) / 'absent'
                with patch.object(Cloud, 'request', side_effect=AssertionError('network')), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    live.main(['run', '--out', str(out), *flags])
                self.assertFalse(out.exists())

    def test_invalid_rates_and_caps_rejected(self):
        for value in (None, 0, -1, 'NaN', 'Infinity', 'bad'):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                live.positive(value)
        with self.assertRaises(ValueError):
            live.load_configs(live.HERE / 'config.example.json', priced=True)

    def test_reserve_before_send_and_keep_reservations_without_usage(self):
        budget = self.budget(requests=1)
        result = live.evaluate_case(self.config, self.fixture('supported-calculator'), budget, 'fake-key',
                                    Mock(side_effect=[call(), answer()]))
        self.assertEqual(budget.requests, 1)
        self.assertGreater(budget.reserved, 0)
        self.assertIn('halted', result)
        self.assertEqual(len(result['requests']), 1)
        self.assertIsNone(result['requests'][0]['usage'])

    def test_spend_limit_blocks_before_transport(self):
        request = Mock()
        result = live.evaluate_case(self.config, self.fixtures[0], self.budget(usd='.000001'), 'fake', request)
        request.assert_not_called()
        self.assertIsNotNone(result['halted'])

    def test_error_and_cancelled_requests_still_consume_budget(self):
        for fixture, transport in [(self.fixtures[0], Mock(side_effect=TimeoutError('do not log secret'))),
                                   (self.fixture('cancel-after-response'), Mock(return_value=call()))]:
            budget = self.budget()
            result = live.evaluate_case(self.config, fixture, budget, 'fake', transport)
            self.assertEqual(budget.requests, 1)
            self.assertGreater(budget.reserved, 0)
            self.assertEqual(result['actions'], [])
            self.assertNotIn('do not log secret', json.dumps(result))

    def test_cancel_before_has_no_requests(self):
        request = Mock()
        result = live.evaluate_case(self.config, self.fixture('cancel-before'), self.budget(), 'fake', request)
        request.assert_not_called()
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['turns'][0]['answer'], '')

    def test_tool_flow_uses_shared_sandbox_and_records_usage_and_latency(self):
        result = live.evaluate_case(self.config, self.fixtures[0], self.budget(), 'fake',
                                    Mock(side_effect=[call(), answer()]))
        self.assertTrue(result['mechanical']['tool_argument_exact_match'])
        self.assertEqual(len(result['actions']), 1)
        self.assertGreaterEqual(result['actions'][0]['mock_dispatch_ms'], 0)
        self.assertEqual(result['requests'][1]['usage']['total_tokens'], 110)
        self.assertGreaterEqual(result['requests'][0]['latency_ms'], 0)
        self.assertIsNone(result['first_speech_ms'])

    def test_repeated_new_ids_and_unknown_actions_are_detected(self):
        result = live.evaluate_case(self.config, self.fixtures[0], self.budget(), 'fake',
                                    Mock(side_effect=[call(id='one'), call(id='two'), call('shell', {'command': 'x'}, id='three'), answer()]))
        self.assertEqual(result['mechanical']['duplicate_actions'], 1)
        self.assertEqual(result['mechanical']['unexpected_actions'], 2)
        self.assertEqual(result['mechanical']['rejected_actions'], 1)

    def test_tool_failure_is_injected_without_launch(self):
        result = live.evaluate_case(self.config, self.fixture('failure-action'), self.budget(), 'fake',
                                    Mock(side_effect=[call(), answer('Launch failed.')]))
        self.assertEqual(result['actions'][0]['error_type'], 'RuntimeError')
        self.assertTrue(result['mechanical']['tool_argument_exact_match'])

    def test_sandbox_fails_closed_and_keeps_tool_validation(self):
        from ultron import actions
        with action_sandbox() as action:
            with self.assertRaises(AssertionError):
                actions.execute('open_app', {'app': 'browser'})
            with self.assertRaises(AssertionError):
                actions.webbrowser.open('https://example.com')
            with self.assertRaises(ValueError):
                action('open_app', {'app': 'calculator', 'extra': 'x'})
            self.assertIn('Requested', action('open_app', {'app': 'calculator'}))

    def test_context_retains_history_and_shares_request_ceiling(self):
        sent = []
        def transport(payload):
            sent.append(json.loads(json.dumps(payload)))
            return answer() if len(sent) == 1 else call(id=str(len(sent)))
        result = live.evaluate_case(self.config, self.fixture('context-reference'), self.budget(), 'fake', transport)
        self.assertEqual(len(sent), 4)
        self.assertIn('I mean calculator', json.dumps(sent[1]))
        self.assertIsNotNone(result['halted'])

    def test_legacy_prompt_changes_only_prompt_and_is_restored(self):
        original = live.cloud_module.INSTRUCTIONS
        request = Mock(return_value=answer())
        live.evaluate_case(self.configs[0], self.fixtures[0], self.budget(), 'fake', request)
        self.assertIn('calm, intelligent', request.call_args.args[0]['messages'][0]['content'])
        self.assertEqual(live.cloud_module.INSTRUCTIONS, original)

    def test_secrets_are_scrubbed_and_exceeded_usage_halts(self):
        result = live.evaluate_case(self.config, self.fixtures[0], self.budget(), 'secret-key',
                                    Mock(return_value=answer('secret-key')))
        self.assertNotIn('secret-key', json.dumps(result))
        response = answer()
        response['usage']['prompt_tokens'] = 10**9
        result = live.evaluate_case(self.config, self.fixtures[0], self.budget(), 'fake', Mock(return_value=response))
        self.assertIsNotNone(result['halted'])

    def test_offline_full_run_writes_blind_records_and_incomplete_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'configurations': self.configs}))
            out = Path(tmp) / 'result'
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake-key'}), \
                    patch.object(Cloud, 'request', return_value=answer()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(live.main(['run', '--config', str(config), '--out', str(out),
                                            '--live', '--approve-usd', '100']), 0)
                self.assertEqual(live.main(['review-summary', '--out', str(out)]), 2)
            summary = json.loads((out / 'summary.json').read_text())
            self.assertEqual(summary['completed_conversations'], 144)
            self.assertEqual(summary['request_latency']['n'], summary['requests'])
            blind = (out / 'blind.jsonl').read_text()
            self.assertNotIn('gpt-6', blind)
            self.assertNotIn('revised-luna-none', blind)
            self.assertNotIn('fake-key', blind)
            self.assertEqual(len(blind.splitlines()), 144)
            self.assertEqual(json.loads((out / 'review-summary.json').read_text())['status'], 'INCOMPLETE')

    def test_review_requires_applicable_labels_and_reports_each_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            mapping = {str(i): {'configuration': c['id'], 'category': 'explanation'}
                       for i, c in enumerate(self.configs)}
            metrics = {c['id']: dict(duplicate_actions=0, unexpected_actions=0,
                                    rejected_actions=0, operation_errors=0) for c in self.configs}
            live.write_json(out / 'manifest-private.json', {'configurations': self.configs, 'mapping': mapping})
            live.write_json(out / 'summary.json', {'completed': True, 'by_configuration': metrics})
            rows = [dict(case_id=str(i), **{f: 'pass' for f in live.REVIEW_FIELDS}) for i in range(3)]
            rows[0]['explanation_accurate'] = 'fail'
            rows[1]['explanation_accurate'] = 'na'
            def write_reviews():
                with (out / 'review.csv').open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=['case_id', *live.REVIEW_FIELDS])
                    writer.writeheader()
                    writer.writerows(rows)
            args = type('Args', (), {'out': str(out)})()
            write_reviews()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(live.review_summary(args), 2)
                rows[1]['explanation_accurate'] = 'pass'
                write_reviews()
                self.assertEqual(live.review_summary(args), 0)
            result = json.loads((out / 'review-summary.json').read_text())
            self.assertEqual(result['by_configuration'][self.configs[0]['id']]['status'], 'FAIL')
            self.assertEqual(result['by_configuration'][self.configs[1]['id']]['status'], 'PASS')

    def test_unknown_usage_is_not_aggregated_as_zero(self):
        record = {'requests': [{'usage': {'prompt_tokens': 12, 'completion_tokens': 4}}]}
        totals = live.usage_totals([record])
        self.assertEqual(totals['input_tokens'], 12)
        self.assertIsNone(totals['cached_input_tokens'])
        self.assertIsNone(totals['reasoning_tokens'])
        self.assertIsNone(live.usage_totals([{'requests': [{'usage': None}]}])['input_tokens'])

    def test_nearest_rank_p95(self):
        self.assertEqual(live.quantiles([])['p95_ms'], None)
        self.assertEqual(live.quantiles(list(range(1, 21)))['p95_ms'], 19)


if __name__ == '__main__':
    unittest.main()
