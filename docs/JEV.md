# Jev quick decisions

Jev is TypeSafe AI's System One decision model. It takes a text state and typed questions, then
returns structured choices and probabilities. It is not an LLM and does not write or explain text.
This integration uses `POST https://api.typesafe.ai/v1/systemone` with `jev-latest`.

In 0.3.0 the request shape (`state`, `questions`, `type`, `criteria`, and the `choice`, `score`, and
`noul` names) has not been exercised against the live API; all tests use stubs. The first real call is
a manual smoke test: set `TYPESAFE_API_KEY` and run `af-decide lane path/to/spec.md`, then record its
`request_id` in the 0.3.0 CHANGELOG entry.

Jev is an **advisory** helper. It can suggest an implementation lane and effort and estimate whether
a spec is complete. The architect remains responsible for the route; the Council's own ranking is
unchanged. A low or high probability is a signal to consider, not a permission gate. Independent
tests place Jev around mid-price LLM decision quality, and it can be overconfident outside its
training distribution. Keep the architect and the Council in the decision loop.

Version 0.3.0 saves no tokens: it adds a cheap extra call while the architect and Council still
decide; savings are only possible after calibration shows Jev's confident answers can be trusted.

## Try it

Enable Jev in your project overlay at `.claude/orchestra/lanes.json` (user settings live at
`~/.claude/astrafabulopus/lanes.json`):

```json
{
  "jev": {
    "enabled": true,
    "min_probability": 0.8,
    "key_ref": "op://Private/TypeSafe API/password"
  }
}
```

Then run `af-decide lane path/to/spec.md`. The request sends the supplied spec text as `state`,
along with the selected API model and typed questions. Lane criteria are fixed strings in the
integration for `routine`, `complex`, `frontier`, and `local`; only enabled lane keys are included.
Effort criteria and question instructions are also fixed in code. Lane descriptions, `_note` values,
model talent data, and other lane or model configuration contents are never sent. It prints a
`confident` marker only at or above `min_probability` (default `0.8`).
`af-council recommend --spec path/to/spec.md` adds Jev's suggestion alongside the Council's
independent pick. Neither command changes `af-lane`, `af-review`, or `af-verify` behavior.

Jev receives only the text of the spec or state that you provide. **Never send photos, secrets, or
other file contents.** Do not paste credentials into a spec. The integration does not attach files
or follow paths mentioned in the text.

## Set up a key

Use a key issued by **console.typesafe.ai**. Do not use API keys from reseller sites.

Choose one of these key stores:

1. Install the 1Password CLI, enable its app integration, and set `key_ref` to the `op://…`
   reference for the key. The CLI reads it at call time; the reference, not the key, belongs in
   config.
2. Add the key to macOS Keychain by running `security add-generic-password -a "$USER" -s
   typesafe-api-key -w` in Terminal and typing the key at the prompt.

For a one-off call, you can set `TYPESAFE_API_KEY` in the environment. Resolution order is the
environment, 1Password, then Keychain. The key is sent only in the HTTPS Authorization header.
Redirects are refused before another request can be made, and connect, request, and response reading
share one monotonic deadline (five seconds by default). The key is not printed or written to the
ledger. `af-doctor` reports whether a key is available and where
it was found, without showing its value.

Settings layer from the plugin defaults to user config and then the project config. The Jev block
supports `enabled`, `endpoint`, `model`, `min_probability`, `timeout_s`, `key_ref`, and
`keychain_service`. The default endpoint is TypeSafe's API and the default timeout is five seconds.

## Calibrate before trusting

Each suggestion appends a `kind: "jev"` ledger record with the question answers, probabilities,
latency, serving model, request id, and the first 12 hex characters of the spec SHA-256. It contains
no spec text and no API key. Lane run records carry the same spec hash. When you grade a later lane
run, Jev links the latest earlier pending suggestion with the same spec hash; if none matches, it
links the latest pending suggestion as a fallback. `af-council grade RUN pass|fail
--spec-complete yes|no` records your label for whether the spec was complete. Use
`--decision DECISION_ID` to select a particular suggestion when several are pending. The decision
id is printed by `af-decide`.

Collect roughly 50–300 labelled examples before changing the confidence floor. Review the ledger as
a set: compare suggested and actual lane/effort, group by probability range, and check how often
`spec_complete` was right. Use those observed results to set thresholds for your own specs and work.
Do not infer reliability from a handful of calls or tune against the same examples you use to report
calibration.
