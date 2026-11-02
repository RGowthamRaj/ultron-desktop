"""Opt-in text/model evaluation. `python -m evals.live --help` is offline."""
import argparse
import copy
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
import uuid
from unittest.mock import patch

from ultron import cloud as cloud_module
from ultron.cloud import Cloud, INSTRUCTIONS
from .sandbox import action_sandbox, simulated_action

HERE = Path(__file__).resolve().parent
REVIEW_FIELDS = ('clarification_appropriate', 'truthful_acknowledgment',
                 'explanation_accurate', 'length_compliant', 'no_material_regression')


class LimitReached(RuntimeError):
    pass


def positive(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Expected a positive finite number.') from None
    if not number.is_finite() or number <= 0:
        raise ValueError('Expected a positive finite number.')
    return number


def load_configs(path, priced=False):
    configs = json.loads(Path(path).read_text(encoding='utf-8'))['configurations']
    if (len(configs) != 3 or len({c['id'] for c in configs}) != 3
            or [c['prompt'] for c in configs] != ['legacy', 'revised', 'revised']
            or configs[0]['model'] != configs[1]['model']
            or configs[2]['model'] != 'gpt-6-luna'):
        raise ValueError('Expected original/current, revised/current, revised/Luna configurations.')
    for config in configs:
        if set(config) != {'id', 'prompt', 'model', 'input_usd_per_million', 'output_usd_per_million'}:
            raise ValueError('Unexpected configuration fields; endpoints and keys are not accepted.')
        if priced:
            for field in ('input_usd_per_million', 'output_usd_per_million'):
                positive(config[field])
        # Validate supported wire configuration offline, before any request.
        Cloud('', config['model']).payload([])
    return configs


class Budget:
    """Reserve worst-case declared cost before sending; never refund reservations.

    Missing usage, timeouts, cancelled requests and failures consume their reservation.
    No retries or unaccounted connection checks.
    """
    def __init__(self, max_usd, max_requests, max_seconds):
        self.limit = positive(max_usd)
        self.max_requests = max_requests
        self.deadline = time.monotonic() + max_seconds
        self.reserved = Decimal(0)
        self.requests = 0

    def reserve(self, payload, config):
        if self.requests >= self.max_requests or time.monotonic() >= self.deadline:
            raise LimitReached('Request or time limit reached.')
        # Byte-based ceiling with substantial protocol/framing allowance. This is
        # deliberately much larger than a character/4 token estimate.
        encoded = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        input_ceiling = encoded + 8192 + 1024 * (len(payload['messages']) + len(payload.get('tools', [])))
        output_ceiling = payload.get('max_completion_tokens', payload.get('max_tokens'))
        amount = (Decimal(input_ceiling) * positive(config['input_usd_per_million'])
                  + Decimal(output_ceiling) * positive(config['output_usd_per_million'])) / 1_000_000
        if self.reserved + amount > self.limit:
            raise LimitReached('Spending reservation would exceed the approved USD cap.')
        self.reserved += amount
        self.requests += 1
        return {'input_token_ceiling': input_ceiling, 'output_token_ceiling': output_ceiling,
                'reserved_usd': str(amount)}


def quantiles(values):
    if not values:
        return {'n': 0, 'median_ms': None, 'p95_ms': None}
    ordered = sorted(values)
    return {'n': len(values), 'median_ms': statistics.median(values),
            'p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1]}


def usage_totals(records):
    requests = [request for record in records for request in record['requests']]
    totals = {}
    for field, group, source in (
            ('input_tokens', None, 'prompt_tokens'), ('output_tokens', None, 'completion_tokens'),
            ('total_tokens', None, 'total_tokens'),
            ('cached_input_tokens', 'prompt_tokens_details', 'cached_tokens'),
            ('reasoning_tokens', 'completion_tokens_details', 'reasoning_tokens')):
        values = []
        for request in requests:
            usage = request['usage']
            detail = usage.get(group) if isinstance(usage, dict) and group else usage
            value = detail.get(source) if isinstance(detail, dict) else None
            values.append(value)
        complete = all(type(v) is int and v >= 0 for v in values)
        totals[field] = sum(values) if complete else None
    totals['usage_complete'] = all(totals[field] is not None for field in ('input_tokens', 'output_tokens'))
    return totals


def scrub(value, secret):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]') if secret else value
    if isinstance(value, dict):
        return {scrub(str(k), secret): scrub(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secret) for v in value]
    return value


def evaluate_case(config, fixture, budget, key, transport=None):
    cloud = Cloud(key, config['model'], tools_enabled=fixture.get('mode') != 'tools_disabled')
    original_request = cloud.request if transport is None else transport
    requests, actions, turns = [], [], []
    cancelled = fixture.get('mode') == 'cancel_before'
    turn_index = 0
    mode = fixture.get('mode')

    def dispatch(name, args):
        entry = {'turn': turn_index, 'name': name, 'arguments': copy.deepcopy(args), 'accepted': False}
        actions.append(entry)
        started = time.monotonic()
        try:
            result = simulated_action(name, args)
            entry['accepted'] = True
            if mode == 'action_failure':
                raise RuntimeError('Simulated application launch failure.')
            entry['result'] = result
            return result
        except Exception as exc:
            entry['error_type'] = type(exc).__name__
            raise
        finally:
            entry['mock_dispatch_ms'] = (time.monotonic() - started) * 1000

    def request(payload):
        nonlocal cancelled
        # Four requests total, even for multi-turn contextual fixtures.
        if len(requests) >= 4:
            raise LimitReached('Conversation request limit reached.')
        reservation = budget.reserve(payload, config)
        record = {'turn': turn_index, **reservation, 'usage': None, 'latency_ms': None}
        requests.append(record)
        started = time.monotonic()
        try:
            response = original_request(payload)
            usage = response.get('usage') if isinstance(response, dict) else None
            record['usage'] = usage
            if isinstance(usage, dict):
                inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
                if (type(inp) is not int or type(out) is not int or inp < 0 or out < 0):
                    record['usage_incomplete'] = True
                elif inp > reservation['input_token_ceiling'] or out > reservation['output_token_ceiling']:
                    raise LimitReached('Provider usage exceeded the declared reservation ceiling.')
            if mode == 'cancel_after_response':
                cancelled = True
            return response
        except Exception as exc:
            record['error_type'] = type(exc).__name__
            raise
        finally:
            record['latency_ms'] = (time.monotonic() - started) * 1000

    cloud.request = request
    prompt = (HERE / 'legacy-prompt.txt').read_text(encoding='utf-8').strip() if config['prompt'] == 'legacy' else INSTRUCTIONS
    halted = None
    with action_sandbox(dispatch), patch.object(cloud_module, 'INSTRUCTIONS', prompt):
        for turn_index, text in enumerate(fixture['turns']):
            result = {'input': text, 'answer': None, 'metrics': None}
            turns.append(result)
            try:
                result['answer'] = cloud.reply(text, lambda: cancelled, lambda *args: None)
            except Exception as exc:
                # Do not log exception strings, provider bodies, headers or keys.
                result['error_type'] = type(exc).__name__
                if isinstance(exc, LimitReached):
                    halted = str(exc)
            result['metrics'] = copy.deepcopy(cloud.last_metrics)
            if halted or cancelled:
                break
    # Exact dispatch matching is mechanical; text correctness remains blind review.
    accuracy = []
    duplicate_count = unexpected_count = rejected_count = 0
    for index, expected in enumerate(fixture['expected']):
        observed = [a for a in actions if a['turn'] == index]
        remaining = copy.deepcopy(expected)
        seen = []
        for action in observed:
            signature = [action['name'], action['arguments']]
            if signature in seen:
                duplicate_count += 1
            seen.append(signature)
            if signature in remaining:
                remaining.remove(signature)
            else:
                unexpected_count += 1
            rejected_count += not action['accepted']
        accuracy.append(not remaining and len(observed) == len(expected) and all(a['accepted'] for a in observed))
    return scrub({'fixture': fixture['id'], 'category': fixture['category'], 'turns': turns,
                  'actions': actions, 'requests': requests, 'halted': halted,
                  'mechanical': {'tool_argument_exact_match': all(accuracy),
                                 'duplicate_actions': duplicate_count,
                                 'unexpected_actions': unexpected_count,
                                 'rejected_actions': rejected_count},
                  'transcription_ms': None, 'recognition_word_error_rate': None,
                  'first_speech_ms': None, 'end_to_end_audio_ms': None}, key)


def plan(configs, fixtures, repeats):
    count = len(configs) * len(fixtures) * repeats
    return {'conversations': count, 'provider_requests_upper_bound': count * 4,
            'repeats': repeats, 'fixtures': len(fixtures), 'configurations': len(configs),
            'network': 'Only run --live --approve-usd CAP can send requests.',
            'os_actions': 'Mocked; microphone and speech never initialized.'}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def run(args):
    # Both CLI approvals must be present before looking for credentials or opening output.
    if not args.live or args.approve_usd is None:
        raise ValueError('Live evaluation requires --live and --approve-usd CAP.')
    positive(args.approve_usd)
    configs = load_configs(args.config, priced=True)
    fixtures = json.loads((HERE / 'fixtures.json').read_text(encoding='utf-8'))
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        raise ValueError('OPENAI_API_KEY must be supplied by the operator; settings are never loaded.')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)  # No overwrite/resume or shared budgets.
    try:
        out.chmod(0o700)
    except OSError:
        pass
    jobs = [(c, f, repeat) for c in configs for f in fixtures for repeat in range(args.repeats)]
    random.Random(args.seed).shuffle(jobs)
    budget = Budget(args.approve_usd, min(args.max_requests, len(jobs) * 4), args.max_seconds)
    manifest = {'plan': plan(configs, fixtures, args.repeats), 'configurations': configs,
                'seed': args.seed, 'approved_usd': str(budget.limit),
                'base_revision': 'ae0c9a4673a51d47f68347f22c63928459a9a14c',
                'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'max_requests': budget.max_requests, 'max_seconds': args.max_seconds,
                'fixture_sha256': hashlib.sha256((HERE / 'fixtures.json').read_bytes()).hexdigest(),
                'legacy_prompt_sha256': hashlib.sha256((HERE / 'legacy-prompt.txt').read_bytes()).hexdigest(),
                'revised_prompt_sha256': hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
                'completed': False, 'mapping': {}, 'halted': None}
    write_json(out / 'manifest-private.json', manifest)
    latencies, records = [], []
    try:
        with (out / 'results-private.jsonl').open('x', encoding='utf-8') as private, \
                (out / 'blind.jsonl').open('x', encoding='utf-8') as blind, \
                (out / 'review.csv').open('x', encoding='utf-8', newline='') as review:
            writer = csv.DictWriter(review, fieldnames=['case_id', *REVIEW_FIELDS, 'notes'])
            writer.writeheader()
            for config, fixture, repeat in jobs:
                if time.monotonic() >= budget.deadline:
                    manifest['halted'] = 'Time limit reached.'
                    break
                case_id = uuid.uuid4().hex
                record = evaluate_case(config, fixture, budget, key)
                record['case_id'] = case_id
                records.append(record)
                manifest['mapping'][case_id] = {'configuration': config['id'], 'repeat': repeat, 'fixture': fixture['id'], 'category': fixture['category']}
                private.write(json.dumps(record, ensure_ascii=False) + '\n')
                private.flush()
                blind.write(json.dumps({'case_id': case_id, 'category': fixture['category'],
                                        'rubric': fixture['rubric'], 'turns': [
                                            {k: v for k, v in t.items() if k != 'metrics'} for t in record['turns']],
                                        'actions': [{k: v for k, v in a.items() if k != 'mock_dispatch_ms'}
                                                    for a in record['actions']]}, ensure_ascii=False) + '\n')
                blind.flush()
                writer.writerow({'case_id': case_id})
                review.flush()
                latencies.extend(r['latency_ms'] for r in record['requests'])
                write_json(out / 'manifest-private.json', manifest)
                if record['halted']:
                    manifest['halted'] = record['halted']
                    break
            manifest['completed'] = len(records) == len(jobs) and not manifest['halted']
    except KeyboardInterrupt:
        manifest['halted'] = 'Interrupted by operator; pending request reservation retained.'
    finally:
        manifest.update(requests=budget.requests, reserved_usd=str(budget.reserved))
        write_json(out / 'manifest-private.json', manifest)
        write_json(out / 'summary.json', {
            'completed_conversations': len(records), 'planned_conversations': len(jobs),
            'completed': manifest['completed'], 'requests': budget.requests, 'usage': usage_totals(records),
            'reserved_usd': str(budget.reserved), 'request_latency': quantiles(latencies),
            'by_configuration': {c['id']: {
                'conversations': sum(manifest['mapping'][r['case_id']]['configuration'] == c['id'] for r in records),
                'usage': usage_totals([r for r in records if manifest['mapping'][r['case_id']]['configuration'] == c['id']]),
                'operation_errors': sum('error_type' in t for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id'] for t in r['turns']),
                'duplicate_actions': sum(r['mechanical']['duplicate_actions'] for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id']),
                'unexpected_actions': sum(r['mechanical']['unexpected_actions'] for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id']),
                'rejected_actions': sum(r['mechanical']['rejected_actions'] for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id']),
                'request_latency': quantiles([q['latency_ms'] for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id'] for q in r['requests']]),
                'tool_argument_exact_matches': sum(r['mechanical']['tool_argument_exact_match'] for r in records
                    if manifest['mapping'][r['case_id']]['configuration'] == c['id'])} for c in configs},
            'duplicate_actions': sum(r['mechanical']['duplicate_actions'] for r in records),
            'unexpected_actions': sum(r['mechanical']['unexpected_actions'] for r in records),
            'rejected_actions': sum(r['mechanical']['rejected_actions'] for r in records),
            'quality_gate': 'UNREVIEWED: complete review.csv and run review-summary.',
            'audio_metrics': 'NOT MEASURED: text-only harness; mock dispatch is not OS latency.'})
    print(f'Evaluation artifacts written to {out}; quality remains subject to blind review.')
    return 0 if manifest['completed'] else 2


def review_summary(args):
    out = Path(args.out)
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    manifest = json.loads((out / 'manifest-private.json').read_text(encoding='utf-8'))
    with (out / 'review.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    ids = [r['case_id'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(manifest['mapping']):
        raise ValueError('Review rows must match each recorded case exactly once.')
    values = [r.get(field, '').strip().lower() for r in rows for field in REVIEW_FIELDS]
    if any(v not in ('pass', 'fail', 'na', '') for v in values):
        raise ValueError('Use pass, fail, na, or a blank unreviewed cell.')
    baseline = manifest['configurations'][0]['id']
    by_configuration = {}
    for config in manifest['configurations']:
        selected = [r for r in rows if manifest['mapping'][r['case_id']]['configuration'] == config['id']]
        required_complete = bool(selected)
        for row in selected:
            category = manifest['mapping'][row['case_id']]['category']
            required = ['truthful_acknowledgment']
            if category == 'ambiguous':
                required.append('clarification_appropriate')
            if category == 'explanation':
                required.append('explanation_accurate')
            if category != 'failure':
                required.append('length_compliant')
            if config['id'] != baseline:
                required.append('no_material_regression')
            required_complete &= all(row.get(field, '').strip().lower() in ('pass', 'fail') for field in required)
        labels = [r.get(field, '').strip().lower() for r in selected for field in REVIEW_FIELDS]
        metrics = summary['by_configuration'][config['id']]
        unsafe = any(metrics[k] for k in ('duplicate_actions', 'unexpected_actions', 'rejected_actions', 'operation_errors'))
        status = ('FAIL' if unsafe or 'fail' in labels else
                  'PASS' if summary['completed'] and required_complete and all(labels) else 'INCOMPLETE')
        by_configuration[config['id']] = {'status': status, 'cases': len(selected)}
    fully_reviewed = all(v['status'] != 'INCOMPLETE' for v in by_configuration.values()) and bool(rows)
    candidate_pass = any(v['status'] == 'PASS' for k, v in by_configuration.items() if k != baseline)
    status = ('PASS' if summary['completed'] and fully_reviewed and candidate_pass else
              'FAIL' if summary['completed'] and fully_reviewed else 'INCOMPLETE')
    result = {'status': status, 'by_configuration': by_configuration,
              'reviewed_cells': sum(bool(v) for v in values), 'total_cells': len(values),
              'note': 'Manual labels are reviewer judgments. A failing baseline does not disqualify a passing revised arm.'}
    write_json(out / 'review-summary.json', result)
    print(json.dumps(result, indent=2))
    return 0 if status == 'PASS' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run'):
        command = sub.add_parser(name)
        command.add_argument('--config', default=str(HERE / 'config.example.json'))
        command.add_argument('--repeats', type=int, choices=(1, 2), default=2)
        if name == 'run':
            command.add_argument('--live', action='store_true')
            command.add_argument('--approve-usd')
            command.add_argument('--out', required=True)
            command.add_argument('--max-requests', type=int, default=576)
            command.add_argument('--max-seconds', type=int, default=3600)
            command.add_argument('--seed', type=int, default=20261102)
    review = sub.add_parser('review-summary')
    review.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'plan':
            configs = load_configs(args.config)
            fixtures = json.loads((HERE / 'fixtures.json').read_text(encoding='utf-8'))
            print(json.dumps(plan(configs, fixtures, args.repeats), indent=2))
            return 0
        if args.command == 'review-summary':
            return review_summary(args)
        if not 1 <= args.max_requests <= 576 or not 1 <= args.max_seconds <= 86400:
            raise ValueError('Use 1–576 requests and 1–86400 seconds.')
        return run(args)
    except (ValueError, KeyError, OSError, TypeError):
        # Config/credential errors never echo values, including malicious endpoints.
        parser.error('Invalid configuration, approval, credential presence, limits, review, or output path; see docs/live-evaluation.md.')


if __name__ == '__main__':
    raise SystemExit(main())
