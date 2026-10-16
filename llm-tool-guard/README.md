# llm-tool-guard

Prompt-injection scanner for tool results. The LiteLLM tool-guard middleware sends each tool result's text to `POST /v1/scan`, and the service answers with the hashes to wrap. The model is loaded from a Hugging Face cache mounted at `HF_HOME`; weights are not baked into the image.

## API

`POST /v1/scan`

```json
{ "new": [{ "hash": "sha256:...", "text": "..." }], "known": ["sha256:..."] }
```

```json
{ "flagged": ["sha256:..."], "unknown": ["sha256:..."], "scores": { "sha256:...": 0.9731 } }
```

- `new` items are checked against the content hash, looked up in the verdict cache and scanned on a miss. A text whose hash does not match, is over `MAX_TEXT_BYTES`, exceeds `SCAN_TIMEOUT_SECONDS`, cannot be scanned, or finds no room in the scan queue is flagged and not cached.
- `scores` holds the model's score for each hash the model flagged, and is `{}` when there are none. A flagged hash without a score was flagged for another reason: a scan error or timeout, a full scan queue, an oversized text or a hash mismatch. Scores are the scanner's, rounded to 4 decimal places.
- `known` hashes are looked up only. Hashes without a verdict come back in `unknown`.
- `503` means the model is still loading, or `MAX_CONCURRENT_REQUESTS` requests are already in flight. The cap is checked before the body is read. A request holds its slot only while its client is connected: when the client disconnects the slot is released, and the scans it started still finish and are cached.

`GET /healthz` fails only when the model could not load, `GET /readyz` passes once it has, and `GET /metrics` serves Prometheus metrics.

## Verdict cache

Verdicts are cached in Valkey under a namespace derived from the model and its revision, the label and threshold, the window settings, the digests of `scanner_types.py` and `classifier.py`, and the installed `transformers`, `tokenizers` and `torch` versions. Changing any of them starts a fresh namespace.

A value is `<verdict>:<score>`, such as `1:0.9731` for flagged and `0:0.0123` for clean. The verdict is the decision made when the text was scanned and is served as stored, never recomputed from the score; a value in any other form is a miss.

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
| `MAX_PENDING_SCANS`       | `128`                                      | Most texts queued or being scanned; further texts are flagged                                   |
| `SCAN_WORKERS`            | `1`                                        | Threads running the model                                                                       |
| `SCAN_TIMEOUT_SECONDS`    | `300`                                      | Time budget per text, about 1 s per KB of CPU time at `MAX_TEXT_BYTES`; checked between windows |
| `SHUTDOWN_DRAIN_SECONDS`  | `20`                                       | Time given to scans in flight to finish and be cached when the service stops                    |
| `VALKEY_URL`              | empty                                      | Verdict cache; no caching when empty                                                            |
| `VALKEY_USERNAME`         | empty                                      | Valkey user                                                                                     |
| `VALKEY_PASSWORD`         | empty                                      | Valkey password                                                                                 |
| `VALKEY_TIMEOUT_SECONDS`  | `0.5`                                      | Connect and read timeout for Valkey                                                             |
| `CACHE_TTL_SECONDS`       | `2592000`                                  | Lifetime of a cached verdict                                                                    |

A scan that runs past `SCAN_TIMEOUT_SECONDS` is flagged, not cached, and counted as `llm_tool_guard_scans_total{verdict="timeout"}`. A model call already running cannot be interrupted, so the budget is checked before each window and the worker is freed at the next window boundary.

Scans still running when `SHUTDOWN_DRAIN_SECONDS` ends stop at their next window, are not cached, and are counted as `llm_tool_guard_scans_total{verdict="stopped"}`.

## Download tooling

The Python dependencies are pinned in [pyproject.toml](pyproject.toml) and locked with hashes in [uv.lock](uv.lock), installed with `uv sync --locked`, and kept current by Renovate. To bump by hand, edit [pyproject.toml](pyproject.toml), then run `uv lock` in this directory and commit both files. torch is the `cpu` dependency group and comes from the PyTorch CPU index; everything else comes from PyPI.
