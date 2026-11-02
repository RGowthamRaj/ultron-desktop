# Opt-in live evaluation

This implements the bounded **text/model** experiment proposed in
[prompt-review.md](prompt-review.md). It is not invoked by application startup,
connection checks, unit-test discovery, or CI. No live evaluation was run while
implementing it. Unit tests use fake responses, including a complete fake
144-conversation run; those results are not quality or performance evidence.

## What is compared

`evals/fixtures.json` contains 24 concrete synthetic fixtures: six supported
commands, four ambiguous requests, four unsupported requests, four injected
failure/cancellation cases, four explanations, and two multi-turn follow-ups.
Every conversation starts with fresh history; contextual turns share history.

The default experiment is three configurations, twice each = 144 conversations,
at most 576 HTTP requests. The limit is **four requests for the entire
conversation**, including follow-up turns, rather than four per turn. A blocked
request ends the run and leaves partial artifacts. Two repeats are a small
exploratory experiment, not a statistical guarantee.

| Configuration | Prompt | Model |
| --- | --- | --- |
| original-current | Original prompt from `7c7229ffa1f3650a68d0fe9990bd0e0bd751de5a` | `gpt-4.1-mini` |
| revised-current | Current `ultron.cloud.INSTRUCTIONS` | Same current comparison model |
| revised-luna-none | Current instructions | `gpt-6-luna`, existing `none`/`low` settings |

The original prompt is snapshotted verbatim in `evals/legacy-prompt.txt`.
All arms use the **merged hardened dispatch and wire settings**. This isolates
prompt/model effects; it does not replay the old unsafe dispatcher or estimate
all benefits of PR #1. Existing strict tools, output caps, reasoning stripping,
redirect refusal and bounded response reads remain active. No Responses adapter,
medium reasoning, automatic fallback, or stronger-model escalation is added.

If the old model is unavailable, deliberately change the **first two** model IDs
to the same supported Chat Completions model and report that substitution.
Do not silently replace failed arms. Custom endpoints and provider keys are not
accepted in configuration: this first experiment targets only the application's
fixed `https://api.openai.com/v1` endpoint. Production settings are never loaded.

## Offline preview: no key and no network

From the repository root, with Python 3.14 (the project's supported version):

```powershell
python -m evals.live --help
python -m evals.live plan
python -m unittest discover -s tests -p test_live_eval.py -v
```

The harness itself uses only the standard library and application modules that
do not initialize audio or Tkinter. The three commands above do not contact a
provider. The plan prints counts; it does not approve spending.

## Prepare a separately approved budget

1. Copy the configuration to an ignored local file:

   ```powershell
   Copy-Item evals/config.example.json output-config.local.json
   ```

2. Edit `output-config.local.json`: replace **every** null input/output USD per
   million token rate with a verified positive current rate for its exact model.
   These are conservative billing ceilings, not price predictions: input rate
   must cover every input category, including cached input, and output rate must
   cover all charged output/reasoning tokens. The harness rejects missing, zero,
   negative, NaN, and infinite rates. It intentionally ships no stale prices.
3. Approve a USD cap independently. Use a dedicated provider project/key with a
   provider-enforced spend/quota limit where available. Supply that key through
   `OPENAI_API_KEY` in this terminal using your normal secret manager. Do not
   paste a key into a command saved in shell history, the config, a PR, or chat.
   No credential is created, read from saved settings, or written by this tool.

Each request reserves cost **before sending**, based on serialized UTF-8 payload
bytes plus 8,192 tokens of base allowance and 1,024 tokens per message/tool,
and the actual payload's completion-token cap. It uses Decimal arithmetic and
never releases a reservation, even after a cheap response, missing usage, a
network failure, timeout or cancellation. Consequently a small cap can stop well
before all 144 conversations. Increase it only with a new deliberate approval;
there is no resume, retry, or automatic cap increase. An existing output folder
is refused, preventing accidental overwrites or ambiguous budget reuse.

This bounds client-issued work under the **declared rate and token ceilings**.
It is not a guarantee of an external provider's invoice: token framing, provider
billing and rate changes remain outside the client. Usage exceeding a declared
ceiling stops further requests; a request already billed cannot be undone.
Use a provider-enforced limit for a financial hard stop. Missing usage stays
unknown and never reduces the budget reservation.

## Deliberate live run

Only after supplying verified rates, the dedicated key and separate budget
approval, run explicitly:

```powershell
python -m evals.live run --config output-config.local.json --live --approve-usd 2.00 --max-requests 576 --max-seconds 3600 --out output/live-eval-20261102
```

`2.00` is an example operator approval, not a promise that $2 completes the
experiment. Both `--live` **and** `--approve-usd` are mandatory. Without either,
the command exits before reading credentials, creating output, or contacting the
provider. `--repeats 1` allows a smaller 72-conversation exploratory run and is
recorded as such. `--seed` controls randomized job order (default `20261102`).

Requests are serial, with no SDK retry, connection probe, automatic fallback or
parallel worker. Default maximum is 576 requests and one hour. Request/time/
spending exhaustion stops the run; exit status 2 means partial/incomplete, while
0 means the planned conversations were attempted, **not** that quality passed.
The existing HTTP timeout is 60 seconds; the wall-time deadline and Ctrl+C cannot
undo an in-flight request and the deadline can overrun by one request timeout.
An ordinary provider error is recorded by type and consumes its reservation;
the next independent fixture may proceed. Review error counts before drawing
conclusions. A rejected configuration or missing key exits without a request.

## OS-action isolation and failure injection

`evals.sandbox.action_sandbox` shares the regression tests' `Mock` plus
`patch('ultron.cloud.execute', ...)` boundary. It is also used by the existing
local-button safety regression. The mock validates fixed tool names, exact
argument keys, string/enumeration values and query length before returning the
same deterministic acknowledgment shapes as real tools. There is no import of
the app, listener, microphone or speech modules.

Defense in depth blocks the real action function, process launches, browser
opening, Windows startfile and the media-key API. No real application launch,
search, playback action, shell command, file edit, recording or speech occurs.
Mock dispatch timing measures Python mock work only.

The failure cases inject a tool error, disable tools, cancel before any request,
or cancel immediately after a live response. The last one consumes a paid
request but dispatches no action. Cancellation is synthetic control-flow
measurement, not microphone interruption or network-cancellation performance.

## Artifacts and review

All default output paths and local config paths are gitignored. The output
directory is owner-only on platforms honoring chmod; on Windows protect it using
your normal user ACLs. Keep it private: it deliberately contains synthetic prompts,
model replies and tool arguments for evaluation. The key is scrubbed from records;
exception bodies/strings, headers and raw provider responses are not logged.
Do not replace fixtures with personal conversations without a fresh privacy review.

| File | Contents |
| --- | --- |
| `manifest-private.json` | Configuration/repeat mapping, prompt/fixture hashes, limits, reservations and completion status |
| `results-private.jsonl` | Per-conversation answers, attempted actions, exact-match checks, errors, all request usage objects and timings |
| `blind.jsonl` | Random case IDs, fixture rubric, answers and action evidence; no configuration mapping, usage, model or timing metadata |
| `review.csv` | Blank human labels for clarification, truthful acknowledgment, explanation accuracy, length and regression |
| `summary.json` | Aggregate and per-configuration request median/p95, token totals and completeness, action checks and budget reservation |

Model self-identification in answer prose can still reveal an arm; blinding is
metadata removal, not a guarantee that a reviewer cannot infer the model.
Provide only `blind.jsonl` and `review.csv` to the reviewer initially. Use `pass`,
`fail`, or `na` for nonapplicable categories, leaving unreviewed cells blank.
Truthful acknowledgment must always be `pass` or `fail`, including a correctly
silent cancellation. Explanation rubrics include required facts and explicit
sentence counts. For actions, require one brief sentence and no observed-state
claim beyond tool evidence. Clarifications must ask before ambiguous actions.

Exact tool/argument matching, rejected calls, unexpected allowed actions and
repeated signatures (even with new call IDs) are mechanical checks. They are
not semantic judgments about explanation correctness or truthful success claims.
Exact-match search wording is fixed by the fixture. Repeated actions within a
turn and actions beyond that turn's expected multiset are counted separately.
The injected action failure is an expected valid attempt, not an unsupported
call. Cancellation fixtures require no dispatch. Provider tools rejected before
dispatch appear as operation errors and must also be reviewed.

After initial blind labels, an evaluator can use the private mapping to compare
arms for each fixture and populate `no_material_regression`: no new safety error,
incorrect explanation, inappropriate clarification, or length failure against
the baseline. Baseline rows may mark that cell `na`. Do not treat blank labels,
partial runs or all-NA safety reviews as a pass. Then aggregate offline:

```powershell
python -m evals.live review-summary --out output/live-eval-20261102
```

This writes `review-summary.json` with a pass/fail/incomplete result per arm.
It exits 0 only for a complete reviewed comparison with at least one revised arm
passing, including zero rejected, duplicate or unexpected actions and operation
errors in that arm. A failing baseline does not disqualify a passing revised arm.
Applicable clarification, explanation, length, truthfulness and revised-arm
regression labels must be pass/fail, not NA. It remains a human-reviewed text
quality gate, not proof of safety or an automatic recommendation. Inspect each arm's error/usage coverage; choose the
lightest arm meeting the original zero unsupported/duplicate/false-success and
no-material-regression criteria. Do not infer quality or latency from prices.

## Timing and recognition limits

HTTP latency uses a monotonic timer around each actual request, including
failure wait time. Median and nearest-rank p95 include every attempted request;
per-request errors allow failed requests to be separated during analysis.
Raw usage is retained per round; absent usage/detail remains null in aggregates,
never a measured zero. Reservations are not actual measured spend.

This runner starts with text and ends with a text reply. It explicitly records
`transcription_ms`, `recognition_word_error_rate`, `first_speech_ms`, and
`end_to_end_audio_ms` as null, and names dispatch timing `mock_dispatch_ms`.
It does **not** measure recognition accuracy, actual OS dispatch, speech startup
or audio completion and cannot support claims about them.

For a separate, supervised audio experiment, retain a sidecar keyed by blind
`case_id` with: machine/OS and microphone/voice/Vosk version; reference and
recognized text; transcription start/end; command-capture end; OS dispatch
start/end; first audible speech; speech completion. Use a common monotonic clock
for durations (and record event definitions). Derive transcription duration,
action dispatch duration, command-to-first-speech, command-to-audio-completion,
and normalized word error rate `(substitutions + deletions + insertions) /
reference words`. A call to `speak()` is not first audible speech. Keep recordings
local and consented; never substitute mock timings into that sidecar. No such
hardware experiment is launched by this harness or required for its offline tests.
