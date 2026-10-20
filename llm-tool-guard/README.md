# llm-tool-guard

Prompt-injection scanner for tool results. The LiteLLM tool-guard middleware sends each tool result's text to `POST /v1/scan`, and the service answers with the hashes to wrap. The model is loaded from a Hugging Face cache mounted at `HF_HOME`; weights are not baked into the image. With `JEV_MODE=enforce`, a result the model flags can be put to Jev, TypeSafe's System One model, as a second check.

## API

`POST /v1/scan`

```json
{ "new": [{ "hash": "sha256:...", "text": "..." }], "known": ["sha256:..."], "jev": true }
```

```json
{ "flagged": ["sha256:..."], "unknown": ["sha256:..."], "scores": { "sha256:...": 0.9731 } }
```

With `"jev": true`, the response also carries the second check's verdicts:

```json
{
  "flagged": ["sha256:..."],
  "unknown": ["sha256:..."],
  "scores": { "sha256:...": 0.9731 },
  "blocked": ["sha256:..."],
  "cleared": ["sha256:..."],
  "jev_scores": { "sha256:...": 0.97 }
}
```

- `new` items are checked against the content hash, looked up in the verdict cache and scanned on a miss. A text whose hash does not match, is over `MAX_TEXT_BYTES`, exceeds `SCAN_TIMEOUT_SECONDS`, cannot be scanned, or finds no room in the scan queue is flagged and not cached.
- `scores` holds the model's score for each hash the model flagged, and is `{}` when there are none. A flagged hash without a score was flagged for another reason: a scan error or timeout, a full scan queue, an oversized text or a hash mismatch. Scores are the scanner's, rounded to 4 decimal places.
- `known` hashes are looked up only. Hashes without a verdict come back in `unknown`.
- `jev` is optional and defaults to `false`; it must be a boolean. Without it the response has exactly the three fields above and every model flag is in `flagged`. With it, and `JEV_MODE=enforce`, each hash the model flagged is put to Jev and the response adds:
  - `blocked`: hashes Jev rated at or above `JEV_BLOCK_AT`. Each is also in `flagged`.
  - `cleared`: hashes Jev rated below `JEV_CLEAR_BELOW`. They are not in `flagged`.
  - `jev_scores`: Jev's probability that the text holds an embedded instruction, for every hash it has an answer for.
  - A model flag Jev rated in between, gave no answer for, or was not asked about stays in `flagged` only. Only flags that carry a model score are asked about, which leaves out scan errors and timeouts, a full queue, oversized texts and hash mismatches. A text over `JEV_MAX_TEXT_BYTES` is not asked about, and a `known` hash is answered only from the caches.
  - `scores` still holds the model's score for every hash the model flagged, blocked and cleared included.
  - With `JEV_MODE=off`, `blocked`, `cleared` and `jev_scores` are present and empty.
- `503` means the model is still loading, or `MAX_CONCURRENT_REQUESTS` requests are already in flight. The cap is checked before the body is read. A request holds its slot only while its client is connected: when the client disconnects the slot is released, and the scans it started still finish and are cached.

`GET /healthz` fails only when the model could not load, `GET /readyz` passes once it has, and `GET /metrics` serves Prometheus metrics.

## Verdict cache

Verdicts are cached in Valkey under a namespace derived from the model and its revision, the label and threshold, the window settings, the digests of `scanner_types.py` and `classifier.py`, and the installed `transformers`, `tokenizers` and `torch` versions. Changing any of them starts a fresh namespace.

A value is `<verdict>:<score>`, such as `1:0.9731` for flagged and `0:0.0123` for clean. The verdict is the decision made when the text was scanned and is served as stored, never recomputed from the score; a value in any other form is a miss.

## Jev answer cache

Jev's answers are cached in Valkey beside the verdicts, under `llm-tool-guard:jev:<namespace>:<hash>`. The namespace is a digest of `JEV_MODEL`, the question text and `judge.py`, so changing any of them starts fresh answers. The verdict cache and its namespace do not depend on Jev: turning Jev on, off or retuning it never rescans a text.

- A value is Jev's raw probability, such as `0.0312`, or `-` when Jev gave no answer. `JEV_BLOCK_AT` and `JEV_CLEAR_BELOW` are applied when a value is read, so changing them needs no new Jev calls.
- A value is written with `SET NX EX GET` and the stored value is used, so replicas that ask about one text at the same time serve the same answer.
- `-` is kept for `CACHE_TTL_SECONDS` when Jev refuses the request (`400` with the error code `max_tokens_exceeded`, `413` or `422` without a top-level `error` in its body), and for one hour, or `CACHE_TTL_SECONDS` if shorter, after any other failure, such as `429`, `529`, `5xx`, any other `400`, a `413` or `422` with a top-level `error` (a gateway's error), `401`, `403`, a timeout, a response from a model other than `JEV_MODEL`, or an unusable body. A text with `-` stored is flagged; once it expires, only a request that carries the text asks again.
- A text over `JEV_MAX_TEXT_BYTES` is not asked about and nothing is stored for it, so a larger limit applies to it at once.
- With `VALKEY_URL` set but Valkey unreachable, Jev is still asked, but an answer that cannot be stored is not used: the text stays flagged, so every turn gets the same verdict. Without `VALKEY_URL`, the answer is used for that request only.
- A request cancelled by its client still gets its ask: one in progress finishes, and one whose scan is still running starts when the scan ends. Either stores the answer. An ask stopped by shutdown stores nothing.

## Configuration

| Variable                  | Default                                    | Purpose                                                                                         |
| ------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `LISTEN_HOST`             | `0.0.0.0`                                  | Bind address                                                                                    |
| `LISTEN_PORT`             | `8080`                                     | Bind port                                                                                       |
| `LOG_LEVEL`               | `INFO`                                     | Log level                                                                                       |
| `AUTH_TOKEN`              | empty                                      | Bearer token required on `/v1/scan`; no auth when empty                                         |
| `MODEL`                   | `Horizon-Labs/prompt-injection-guard-base` | Hugging Face model                                                                              |
| `INJECTION_LABEL`         | `INJECTION`                                | Model label that means injection                                                                |
| `THRESHOLD`               | `0.9`                                      | Score at or above which a text is flagged, in (0, 1]                                            |
| `WINDOW_TOKENS`           | `2048`                                     | Tokens per scan window                                                                          |
| `WINDOW_OVERLAP`          | `512`                                      | Tokens shared by consecutive windows                                                            |
| `WINDOW_BATCH_SIZE`       | `1`                                        | Windows scored per model call                                                                   |
| `MAX_WINDOWS`             | covers `MAX_TEXT_BYTES`                    | Most windows one text may span                                                                  |
| `MAX_TEXT_BYTES`          | `262144`                                   | Largest text scanned; larger texts are flagged                                                  |
| `MAX_BODY_BYTES`          | `8388608`                                  | Largest request body, about 32 texts of `MAX_TEXT_BYTES`; larger bodies get `413`               |
| `MAX_CONCURRENT_REQUESTS` | `8`                                        | Most `/v1/scan` requests in flight; further requests get `503`                                  |
| `MAX_PENDING_SCANS`       | `128`                                      | Most texts queued or being scanned, plus Jev asks in flight; further texts are flagged          |
| `SCAN_WORKERS`            | `1`                                        | Threads running the model                                                                       |
| `SCAN_TIMEOUT_SECONDS`    | `300`                                      | Time budget per text, about 1 s per KB of CPU time at `MAX_TEXT_BYTES`; checked between windows |
| `SHUTDOWN_DRAIN_SECONDS`  | `20`                                       | Time given to scans in flight to finish and be cached when the service stops                    |
| `VALKEY_URL`              | empty                                      | Verdict cache; no caching when empty                                                            |
| `VALKEY_USERNAME`         | empty                                      | Valkey user                                                                                     |
| `VALKEY_PASSWORD`         | empty                                      | Valkey password                                                                                 |
| `VALKEY_TIMEOUT_SECONDS`  | `0.5`                                      | Connect and read timeout for Valkey                                                             |
| `CACHE_TTL_SECONDS`       | `2592000`                                  | Lifetime of a cached verdict                                                                    |
| `JEV_MODE`                | `off`                                      | `off` or `enforce`; `enforce` puts model flags to Jev and needs `JEV_API_URL` and `JEV_API_KEY` |
| `JEV_API_URL`             | empty                                      | Base URL of the Jev API, absolute http(s); required with `enforce`                              |
| `JEV_API_KEY`             | empty                                      | Bearer token sent to the Jev API; required with `enforce`                                       |
| `JEV_MODEL`               | `jev-1.13.0`                               | Pinned Jev model; an answer from another model counts as an error                               |
| `JEV_BLOCK_AT`            | `0.9`                                      | Probability at or above which Jev blocks a text, in (0, 1]                                      |
| `JEV_CLEAR_BELOW`         | `0.08`                                     | Probability below which Jev clears a text; must not exceed `JEV_BLOCK_AT`                       |
| `JEV_TIMEOUT_SECONDS`     | `10`                                       | Time budget per ask, including one retry on `429`, `5xx`, a timeout or a dropped connection     |
| `JEV_MAX_TEXT_BYTES`      | `16384`                                    | Largest text put to Jev; larger flagged texts stay flagged                                      |

A scan that runs past `SCAN_TIMEOUT_SECONDS` is flagged, not cached, and counted as `llm_tool_guard_scans_total{verdict="timeout"}`. A model call already running cannot be interrupted, so the budget is checked before each window and the worker is freed at the next window boundary.

Scans still running when `SHUTDOWN_DRAIN_SECONDS` ends stop at their next window, are not cached, and are counted as `llm_tool_guard_scans_total{verdict="stopped"}`. Jev asks still running then are cancelled.

## Second check

The service refuses to start when `JEV_MODE` is not `off` or `enforce`, when `JEV_MODE=enforce` has no `JEV_API_URL` or `JEV_API_KEY`, when `JEV_API_KEY` is not printable ASCII (a trailing newline, for example), when `JEV_API_URL` is not an absolute http(s) URL or has a query or fragment, when `JEV_BLOCK_AT` is outside (0, 1], or when `JEV_CLEAR_BELOW` is above `JEV_BLOCK_AT`. The error names the variable, never its value.

For a model flag in a request with `"jev": true`, the service posts the text to `{JEV_API_URL}/v1/systemone` (for example, a gateway's TypeSafe pass-through) with `Authorization: Bearer <JEV_API_KEY>` as `{"tool_output": <text>}` with one yes/no question: does the text contain an embedded instruction aimed at whoever processes it? Jev answers with the probability of yes. The call runs on the event loop, not the scan thread, and holds a `MAX_PENDING_SCANS` slot while it waits; a text that finds no slot is flagged and not cached. The service needs network access to `JEV_API_URL`; trailing slashes on it are ignored and a path prefix is kept.

A `429`, `5xx`, a timeout or a dropped connection is retried once inside `JEV_TIMEOUT_SECONDS`. Any other failure, a `4xx` from the API's gateway included, is final for that ask, and the text stays in `flagged`.

`llm_tool_guard_jev_requests_total{outcome}` counts asks by `blocked`, `cleared`, `middle` (answered in between), `error` and `skipped` (not asked: over `JEV_MAX_TEXT_BYTES`, or no queue slot). `llm_tool_guard_jev_duration_seconds` times the calls to Jev. Answers served from the cache are not counted.

## Download tooling

The Python dependencies are pinned in [pyproject.toml](pyproject.toml) and locked with hashes in [uv.lock](uv.lock), installed with `uv sync --locked`, and kept current by Renovate. To bump by hand, edit [pyproject.toml](pyproject.toml), then run `uv lock` in this directory and commit both files. `uv lock` resolves only releases uploaded at least 7 days ago (`exclude-newer` in [pyproject.toml](pyproject.toml)), so pinning a release younger than that fails to resolve. torch is the `cpu` dependency group and comes from the PyTorch CPU index; everything else comes from PyPI.
