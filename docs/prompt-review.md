# Prompt, model, and tool safeguards

Reviewed against main `7c7229ffa1f3650a68d0fe9990bd0e0bd751de5a` on November 1, 2026.
This is a focused application hardening review, not a penetration test or a claim of vulnerability-free software.

## Implemented measures

1. Updated the OpenAI preset and constructor default from GPT-4.1 mini to GPT-6 Luna.
   Luna uses Chat Completions with explicit `reasoning_effort: none`, `verbosity: low`,
   `max_completion_tokens: 512`, and `parallel_tool_calls: false`. Existing saved model choices are preserved.
2. Preserved `strict: true` inside OpenAI's outgoing function definitions. Kept third-party
   payloads separate and added exact local argument-property validation for every provider.
3. Rewrote instructions around current intent, observable tool evidence, ambiguous state,
   action completion, disabled capabilities, speech-friendly output, and brief examples.
   Explained that media keys toggle unknown state and do not verify the target player.
4. Reject truncated or filtered responses before accepting text or executing tool calls.
   Reject malformed calls and duplicate call IDs before dispatching a batch.
5. Bound request input to 8,000 characters, history to six turns and 24,000 serialized
   characters, one provider body to 1 MiB, and one operation to four model rounds/eight calls.
   History eviction preserves whole exchanges. Interrupted batches receive explicit
   not-executed results so future requests do not contain unmatched tool IDs.
6. Removed recognized think-tag content before retaining history as well as before speech.
   Incomplete reasoning tags cause an error rather than being displayed or retained.
7. Added in-memory operation metrics, aggregating usage over all model rounds. Missing usage
   is marked incomplete; missing cached/reasoning detail is unknown rather than assumed zero.
8. Routed the three explicit app buttons through validated local actions with deterministic
   acknowledgments, preserving queueing, cancellation, disabled-tools behavior, and history.
9. Reused model-specific settings for connection checks and required the expected OK response.
   Connection verification explicitly does not claim that tool calling was tested.
10. Lowered Gemini Argon thinking to low without raising its existing spend cap; kept
    Nemotron thinking disabled. Provider-specific tuning does not leak to custom endpoints.
11. Retained existing HTTPS checks, redirect refusal, provider-key isolation, encrypted saved
    credentials, app allowlists, and the prohibition on model-generated shell/file/message actions.

## Verification and measured results

- Baseline: 33/33 tests passed in 9.293 seconds using Python 3.14.4 on Windows.
- Updated suite: 62/62 tests passed in 8.345 seconds, including 29 additional regression tests.
  These runtimes describe test execution, not provider or speech performance.
- All provider calls and OS actions were mocked. No real API calls, credits, recordings,
  app launches, or playback actions were used for validation.
- Mocked normal tool flow uses two provider requests; a fixed app button uses zero.
- Outgoing OpenAI tool definitions now retain strict mode. Truncated tool calls, duplicate
  IDs, malformed batches, and oversized batches are blocked before their first action.
- Tests verify that stripped reasoning is absent from retained history, whole-turn history
  remains within its character bound, and usage is aggregated over two simulated rounds.
- Sandbox temporary-directory permissions initially prevented four existing settings tests.
  Running with TEMP/TMP assigned to a writable workspace directory resolved that environment issue.

No live model-quality, recognition-quality, token-savings, API latency, or speech-latency gain
has been measured. Mocked responses cannot establish any of those outcomes.

## Remaining vulnerabilities and limitations

- **Medium, action authorization:** the wake phrase is not speaker authentication. Nearby
  speech or an incorrect transcript can request an allowed action. Disable automatic listening
  or desktop tools when this is inappropriate; speaker verification is outside this patch.
- **Medium, model-directed side effects:** prompts and strict JSON constrain behavior but do
  not prove user intent. A model can select an unwanted allowed action or repeat it with a new
  call ID. Duplicate-ID detection is not semantic deduplication. Action count is bounded;
  adding capabilities requires a fresh authorization and threat review.
- **Medium, provider trust/privacy:** natural-language requests and retained context are sent
  to the configured provider. A deliberately selected custom endpoint receives its configured
  key and text. HTTPS and redirect refusal do not establish that the provider is trustworthy.
- **Low, residual reasoning disclosure:** known think-tag blocks are removed, but no regex can
  identify reasoning written as ordinary prose. The selected instruct model/provider must keep
  reasoning in supported private channels.
- **Functional, unverifiable state:** app launches and media keys are requests; screen,
  playback, volume, and mute state remain unobservable. Search results are opened but not read.
- **Functional, cancellation:** a pending HTTP operation can remain blocked for up to 60
  seconds; dispatched OS actions cannot be undone. Streaming/network cancellation is deferred.
- **Functional, budgets and difficult tasks:** character bounds are not exact token budgets.
  Gemini's retained 2,048-token cap can still truncate reasoning tasks. No automatic stronger
  model escalation, Responses adapter, or production quality routing was added without evals.
- **Migration:** existing saved GPT-4.1 mini settings are not rewritten. OpenAI lists that
  model for shutdown on January 14, 2027. Select the new preset and save to migrate.

None of these classifications is a CVSS score or evidence of a demonstrated exploit.

## Proposed live evaluation (not executed)

Use 24 fixtures: six supported commands, four ambiguous requests, four unsupported requests,
four failure/cancellation cases, four explanations, and two contextual follow-ups. Mock OS actions.
Compare current prompt/current model, revised prompt/current model, and revised prompt/Luna-none,
twice each: 144 conversations, at most 576 provider requests under the four-round bound.
Use a separately approved spending cap and never run it implicitly in tests or CI.

Record tool/argument accuracy, clarification appropriateness, duplicate actions, unsupported actions,
truthful acknowledgments, explanation accuracy, length compliance, full usage, and median/p95
request latency. Separately measure transcription, action dispatch, first speech, and end-to-end
completion. Review outputs blind. Require zero unsupported/duplicate actions and false-success
claims, and no material quality regression. Test Luna-medium or Sol-medium on difficult cases
only after a Responses adapter exists for reasoning with tools. Prefer the lightest configuration
that meets these conditions; do not infer performance from token prices.

## Official guidance checked

- [OpenAI model lifecycle](https://developers.openai.com/api/docs/deprecations)
- [GPT-6 Luna settings](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI prompting](https://developers.openai.com/api/docs/guides/prompt-engineering)
- [Gemini compatibility settings](https://ai.google.dev/gemini-api/docs/openai)
- [Nemotron endpoint](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer)
