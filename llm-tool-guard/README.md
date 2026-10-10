# llm-tool-guard

Prompt-injection scanner for tool results. The LiteLLM tool-guard middleware sends each tool result's text to `POST /v1/scan`, and the service answers with the hashes to wrap. The model is loaded from a Hugging Face cache mounted at `HF_HOME`; weights are not baked into the image.

## API

`POST /v1/scan`

```json
{ "new": [{ "hash": "sha256:...", "text": "..." }], "known": ["sha256:..."] }
```

```json
{ "flagged": ["sha256:..."], "unknown": ["sha256:..."] }
```

- `new` items are checked against the content hash, looked up in the verdict cache and scanned on a miss. A text whose hash does not match, is over `MAX_TEXT_BYTES`, exceeds `SCAN_TIMEOUT_SECONDS`, cannot be scanned, or finds no room in the scan queue is flagged and not cached.
- `known` hashes are looked up only. Hashes without a verdict come back in `unknown`.
- `503` means the model is still loading, or `MAX_CONCURRENT_REQUESTS` requests are already in flight. The cap is checked before the body is read.

`GET /healthz` fails only when the model could not load, `GET /readyz` passes once it has, and `GET /metrics` serves Prometheus metrics.

## Verdict cache

Verdicts are cached in Valkey under a namespace derived from the model and its revision, the label and threshold, the window settings, the digest of `scanner_types.py`, and the installed `transformers`, `tokenizers` and `torch` versions. Changing any of them starts a fresh namespace.

## Configuration

| Variable                  | Default                                  | Purpose                                                                                       |
| ------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| `LISTEN_HOST`             | `0.0.0.0`                                | Bind address                                                                                  |
| `LISTEN_PORT`             | `8080`                                   | Bind port                                                                                     |
| `LOG_LEVEL`               | `INFO`                                   | Log level                                                                                     |
| `AUTH_TOKEN`              | empty                                    | Bearer token required on `/v1/scan`; no auth when empty                                       |
| `MODEL`                   | `Horizon-Labs/prompt-injection-guard-base` | Hugging Face model                                                                          |
| `INJECTION_LABEL`         | `INJECTION`                              | Model label that means injection                                                              |
| `THRESHOLD`               | `0.9`                                    | Score at or above which a text is flagged, in (0, 1]                                          |
| `WINDOW_TOKENS`           | `2048`                                   | Tokens per scan window                                                                        |
| `WINDOW_OVERLAP`          | `512`                                    | Tokens shared by consecutive windows                                                          |
| `WINDOW_BATCH_SIZE`       | `1`                                      | Windows scored per model call                                                                 |
| `MAX_WINDOWS`             | covers `MAX_TEXT_BYTES`                  | Most windows one text may span                                                                |
| `MAX_TEXT_BYTES`          | `262144`                                 | Largest text scanned; larger texts are flagged                                                |
| `MAX_BODY_BYTES`          | `8388608`                                | Largest request body, about 32 texts of `MAX_TEXT_BYTES`; larger bodies get `413`             |
| `MAX_CONCURRENT_REQUESTS` | `8`                                      | Most `/v1/scan` requests in flight; further requests get `503`                               |
| `MAX_PENDING_SCANS`       | `128`                                    | Most texts queued or being scanned; further texts are flagged                                 |
| `SCAN_WORKERS`            | `1`                                      | Threads running the model                                                                     |
| `SCAN_TIMEOUT_SECONDS`    | `300`                                    | Time budget per text, about 1 s per KB of CPU time at `MAX_TEXT_BYTES`; checked between windows |
| `SHUTDOWN_DRAIN_SECONDS`  | `20`                                     | Time given to scans in flight to finish and be cached when the service stops                  |
| `VALKEY_URL`              | empty                                    | Verdict cache; no caching when empty                                                          |
| `VALKEY_USERNAME`         | empty                                    | Valkey user                                                                                   |
| `VALKEY_PASSWORD`         | empty                                    | Valkey password                                                                               |
| `VALKEY_TIMEOUT_SECONDS`  | `0.5`                                    | Connect and read timeout for Valkey                                                           |
| `CACHE_TTL_SECONDS`       | `2592000`                                | Lifetime of a cached verdict                                                                  |

A scan that runs past `SCAN_TIMEOUT_SECONDS` is flagged, not cached, and counted as `llm_tool_guard_scans_total{verdict="timeout"}`. A model call already running cannot be interrupted, so the budget is checked before each window and the worker is freed at the next window boundary.
