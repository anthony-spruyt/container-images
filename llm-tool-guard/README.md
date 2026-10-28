# llm-tool-guard

Prompt-injection scanner for tool results.
The LiteLLM tool-guard middleware sends each tool result's text to `POST /v1/scan`, and the service answers with the hashes to wrap.
The model is an OpenVINO IR that runs on the Intel GPU.
It is loaded from the [llm-tool-guard-model](../llm-tool-guard-model/README.md) image, mounted read-only at `$HF_HOME/hub`; weights are not baked into the image.
With `JEV_MODE=enforce`, Jev is a second check on every result the model flags: it is asked about the windows of the text the model flagged.

## API

`POST /v1/scan`

```json
{ "new": [{ "hash": "sha256:...", "text": "..." }], "known": ["sha256:..."] }
```

The response always has these six fields:

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
- A `jev` field in the request is ignored, so callers that still send it keep working. While `JEV_MODE=enforce`, every flagged text is put to Jev on every scan, and the response adds:
  - `blocked`: hashes where Jev rated any window it was asked about at or above `JEV_BLOCK_AT`. Each is also in `flagged`.
  - `cleared`: hashes where Jev answered for every window it was asked about and rated each below `JEV_CLEAR_BELOW`. They are not in `flagged`.
  - `jev_scores`: the highest probability Jev gave, among the windows it answered for, that the window holds an embedded instruction, for every hash it has an answer for.
  - A model flag stays in `flagged` only when it is neither: a window rated in between, or a window with no answer or over `JEV_MAX_TEXT_BYTES`, keeps the text flagged unless another window blocks it.
  - Jev is asked only about the windows the model flagged, each window whose own score is at or above `THRESHOLD`, sent as the slice of the text it covers. Windows scored below it are not sent. A flag without a model score (a scan error or timeout, a full queue, an oversized text or a hash mismatch) is not asked about, nor is a text flagged for spanning more than `MAX_WINDOWS`, which has no flagged window. A text with more flagged windows than `JEV_MAX_WINDOWS`, or without a free queue slot for each of its windows, is not asked about either and stays flagged. A `known` hash is answered only from the caches.
  - `scores` still holds the model's score for every hash the model flagged, blocked and cleared included.
  - With `JEV_MODE=off`, `blocked`, `cleared` and `jev_scores` are present and empty.
- `503` means the model is still loading, or `MAX_CONCURRENT_REQUESTS` requests are already in flight. The cap is checked before the body is read. A request holds its slot only while its client is connected: when the client disconnects the slot is released, and the scans it started still finish and are cached.

`GET /healthz` fails only when the model could not load, `GET /readyz` passes once it has, and `GET /metrics` serves Prometheus metrics.

## Verdict cache

Verdicts are cached in Valkey under a namespace derived from the model and its revision, the label and threshold, the window settings, the digests of `scanner_types.py`, `classifier.py` and `openvino_backend.py`, the installed `transformers`, `tokenizers` and `openvino` versions, the device and its precision, a digest of the model files and the Intel GPU runtime baked into the image.
Changing any of them starts a fresh namespace.

A value is `<verdict>:<score>`, such as `0:0.0123` for clean, or `<verdict>:<score>:<spans>` for a flagged text, such as `1:0.9731:0-2113,1800-3900`. A text flagged for spanning more than `MAX_WINDOWS` has no windows to list and is stored as `1:1.0`, with no spans. The score is the highest window score. The spans are the character offsets (start, end exclusive) in the text of each window whose own score is at or above `THRESHOLD`; they let a cached flag be put to Jev without scanning again. The verdict is the decision made when the text was scanned and is served as stored, never recomputed from the score; a value in any other form is a miss.

## Jev answer cache

Jev's answers are cached in Valkey beside the verdicts, under `llm-tool-guard:jev:<namespace>:<hash>`. The namespace is a digest of `JEV_MODEL`, the question text, `judge.py`, `JEV_MAX_TEXT_BYTES`, `JEV_MAX_WINDOWS` and the verdict cache namespace, which decides the windows that are flagged and so asked about, so changing any of them starts fresh answers. The verdict cache and its namespace do not depend on Jev: turning Jev on, off or retuning it never rescans a text.

- A value holds one answer per text: the highest probability among the windows Jev answered for, such as `0.0312`. A `+` after it, as in `0.97+`, means a window got no answer, so the text can be blocked by it but never cleared. `-` means no window got an answer. `JEV_BLOCK_AT` and `JEV_CLEAR_BELOW` are applied when a value is read, so changing them needs no new Jev calls. The highest probability blocks a text when any window does, and clears it only when every window is below `JEV_CLEAR_BELOW`.
- A value is written with `SET NX EX GET` and the stored value is used, so replicas that ask about one text at the same time serve the same answer.
- A complete value is kept for `CACHE_TTL_SECONDS`. `-`, and `+` values for the windows they miss, are kept for `CACHE_TTL_SECONDS` when Jev refuses the request (`400` with the error code `max_tokens_exceeded`, `413` or `422` without a top-level `error` in its body), and for one hour, or `CACHE_TTL_SECONDS` if shorter, after any other failure, such as `429`, `529`, `5xx`, any other `400`, a `413` or `422` with a top-level `error` (an error from a proxy in front of the API), `401`, `403`, a timeout, a response from a model other than `JEV_MODEL`, or an unusable body. A text with `-` stored is flagged; once it expires, only a request that carries the text asks again. A `+` value takes the shorter time when any missing window failed that way.
- A window over `JEV_MAX_TEXT_BYTES` is not asked about. It counts as a window with no answer that asking again would not change, so its text is stored (`+` when other windows answered, `-` when none did) and not asked again. A larger limit starts a new namespace, so it applies at once.
- A text with more flagged windows than `JEV_MAX_WINDOWS` is not asked about and nothing is stored for it. A text takes a queue slot for each of its windows at once, or none: without that many free slots (a text with more windows than `MAX_PENDING_SCANS` never has them) nothing is asked or stored for it, and it stays flagged for that request, so a later request with free slots asks.
- With `VALKEY_URL` set but Valkey unreachable, Jev is still asked, but an answer that cannot be stored is not used: the text stays flagged, so every turn gets the same verdict. Without `VALKEY_URL`, the answer is used for that request only.
- A request cancelled by its client still gets its asks: ones in progress finish, and ones whose scan is still running start when the scan ends. Either stores the answer. An ask stopped by shutdown stores nothing.

## Configuration

| Variable                  | Default                                    | Purpose                                                                                         |
| ------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `LISTEN_HOST`             | `0.0.0.0`                                  | Bind address                                                                                    |
| `LISTEN_PORT`             | `8080`                                     | Bind port                                                                                       |
| `LOG_LEVEL`               | `INFO`                                     | Log level                                                                                       |
| `AUTH_TOKEN`              | empty                                      | Bearer token required on `/v1/scan`; no auth when empty                                         |
| `MODEL`                   | `Horizon-Labs/prompt-injection-guard-base` | Hugging Face model                                                                              |
| `INJECTION_LABEL`         | `INJECTION`                                | Model label that means injection                                                                |
| `SCANNER_DEVICE`          | `GPU`                                      | OpenVINO device the model runs on, `GPU` or `CPU`; a missing device fails the load              |
| `THRESHOLD`               | `0.9`                                      | Score at or above which a text is flagged, in (0, 1]                                            |
| `WINDOW_TOKENS`           | `2048`                                     | Tokens per scan window                                                                          |
| `WINDOW_OVERLAP`          | `512`                                      | Tokens shared by consecutive windows                                                            |
| `WINDOW_BATCH_SIZE`       | `1`                                        | Windows scored per model call; only `1` is accepted, as padded rows score NaN                   |
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
| `JEV_MODE`                | `off`                                      | `off` or `enforce`; `enforce` asks Jev about flags, needs `JEV_API_URL` and `JEV_API_KEY`       |
| `JEV_API_URL`             | empty                                      | Base URL of the Jev API, absolute http(s); required with `enforce`                              |
| `JEV_API_KEY`             | empty                                      | Bearer token sent to the Jev API; required with `enforce`                                       |
| `JEV_MODEL`               | `jev-1.13.0`                               | Pinned Jev model; an answer from another model counts as an error                               |
| `JEV_BLOCK_AT`            | `0.9`                                      | Probability at or above which Jev blocks a window, and so its text, in (0, 1]                   |
| `JEV_CLEAR_BELOW`         | `0.08`                                     | Probability below which Jev clears a window; must not exceed `JEV_BLOCK_AT`                     |
| `JEV_TIMEOUT_SECONDS`     | `10`                                       | Time budget per ask, including one retry on `429`, `5xx`, a timeout or a dropped connection     |
| `JEV_MAX_TEXT_BYTES`      | `16384`                                    | Largest window put to Jev, in bytes; a larger flagged window counts as unanswered               |
| `JEV_MAX_WINDOWS`         | `16`                                       | Most flagged windows of one text put to Jev; a text with more is not asked, stays flagged       |

A scan that runs past `SCAN_TIMEOUT_SECONDS` is flagged, not cached, and counted as `llm_tool_guard_scans_total{verdict="timeout"}`. A model call already running cannot be interrupted, so the budget is checked before each window and the worker is freed at the next window boundary.

Scans still running when `SHUTDOWN_DRAIN_SECONDS` ends stop at their next window, are not cached, and are counted as `llm_tool_guard_scans_total{verdict="stopped"}`. Jev asks still running then are cancelled.

## Second check

The service refuses to start when `JEV_MODE` is not `off` or `enforce`, when `JEV_MODE=enforce` has no `JEV_API_URL` or `JEV_API_KEY`, when `JEV_API_KEY` is not printable ASCII (a trailing newline, for example), when `JEV_API_URL` is not an absolute http(s) URL with a valid port, is not printable ASCII (a space or line break, for example), or has user info (the key is sent separately), a query or a fragment, when `JEV_BLOCK_AT` is outside (0, 1], or when `JEV_CLEAR_BELOW` is above `JEV_BLOCK_AT`. The errors never print the key or the URL.

For each window the model flagged, the service posts the window's text to `{JEV_API_URL}/v1/systemone` with `Authorization: Bearer <JEV_API_KEY>` as `{"tool_output": <text>}` with one yes/no question: does the text contain an embedded instruction aimed at whoever processes it? Jev answers with the probability of yes. The windows of one text are asked at once, and at most `JEV_MAX_WINDOWS` of them: a text with more flagged windows is not asked about and stays flagged. The calls run on the event loop, not the scan thread. A text takes one `MAX_PENDING_SCANS` slot for each of its windows when its asks start and holds them until they end; when that many slots are not free, none of its windows is asked and the text stays flagged. The service needs network access to `JEV_API_URL`; trailing slashes on it are ignored and a path prefix is kept.

A `429`, `5xx`, a timeout or a dropped connection is retried once inside `JEV_TIMEOUT_SECONDS`. Any other failure, a `4xx` from a proxy in front of the API included, is final for that ask, and the text stays in `flagged` unless another window blocks it.

`llm_tool_guard_jev_requests_total{outcome}` counts asks, one per window, by `blocked`, `cleared`, `middle` (answered in between), `error` and `skipped` (not asked: over `JEV_MAX_TEXT_BYTES`, or the text found no queue slots for its windows). `llm_tool_guard_jev_duration_seconds` times the calls to Jev. Answers served from the cache are not counted.

## GPU runtime

The model compiles on the device named by `SCANNER_DEVICE`: `GPU` runs in f16 with the `LATENCY` hint, any other device in f32.
A device OpenVINO does not list fails the load, so the pod never turns ready; nothing falls back to the CPU.
CI has no GPU, so `test.sh` runs the scanner with `SCANNER_DEVICE=CPU` and checks that the default device fails the load.
A pod on the GPU needs the Intel GPU device and a group that can open it.

The image carries Intel's OpenCL stack and nothing else of the GPU's:

- `intel-opencl-icd` and `libigdgmm12` from the `intel/compute-runtime` release, the main line that covers Alder Lake.
- `intel-igc-core-2` and `intel-igc-opencl-2` from the `intel/intel-graphics-compiler` release that the driver package pairs with.
- `ocl-icd-libopencl1` from Debian. Debian packages no IGC, and its compute-runtime is too old.

The four Intel `.deb`s are pinned by checksum in the [Dockerfile](Dockerfile), and Renovate tracks only `COMPUTE_RUNTIME_VERSION`. A bump fails the build until the checksums, `GMMLIB_VERSION` (the `libigdgmm12` file name changes between releases) and the IGC pin follow it. Set the IGC version to what the new `intel-opencl-icd` package depends on (`dpkg-deb -f <deb> Depends`); the apt install fails when the pinned IGC is outside that range, so a stale pair cannot ship.

`INTEL_GPU_RUNTIME` names the installed versions and is part of the [verdict cache](#verdict-cache) namespace. The driver keeps its compiler cache in `$XDG_CACHE_HOME/neo_compiler_cache`, which is under `HF_HOME`, so mount a writable volume there.

## Download tooling

The Python dependencies are pinned in [pyproject.toml](pyproject.toml) and locked with hashes in [uv.lock](uv.lock), installed with `uv sync --locked`, and kept current by Renovate.
To bump by hand, edit [pyproject.toml](pyproject.toml), then run `uv lock` in this directory and commit both files. `uv lock` resolves only releases uploaded at least 7 days ago (`exclude-newer` in [pyproject.toml](pyproject.toml)), so pinning a release younger than that fails to resolve.

`openvino-telemetry` is excluded from the lock (`exclude-dependencies` in [pyproject.toml](pyproject.toml)), so importing openvino sends no telemetry. A test in [tests/test_no_telemetry.py](tests/test_no_telemetry.py) fails if the package comes back.
