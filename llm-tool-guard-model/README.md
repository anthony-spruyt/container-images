# llm-tool-guard-model

The model for [llm-tool-guard](../llm-tool-guard/README.md), as an image of its own.
The image holds only a Hugging Face hub cache for `Horizon-Labs/prompt-injection-guard-base`: `config.json`, the tokenizer files and the model converted to an OpenVINO IR (`openvino_model.xml` and `openvino_model.bin`, f32). `model.safetensors` is downloaded and checked at build time but not shipped.
The scanner image stays small and the model is pulled once per model revision, not once per scanner release.

The files sit at the image root, laid out as a hub cache (huggingface_hub 2.x): `models--Horizon-Labs--prompt-injection-guard-base/` with `snapshots/<revision>/`, `refs/main` holding the revision, and `blobs/`.
In the snapshot the config and tokenizer files link to `models--…/blobs/<id>`, and the large ones link on to the top-level `blobs/<xx>/<sha256>`, so mount the whole image with no `subPath`.
The IR files are regular files in the snapshot.

The image has no shell and no command; it only supplies files. The same revision and converter pins always build byte-identical layers, so a release from a build-tooling bump costs nodes no new download.

## Usage

Mount the image read-only at `$HF_HOME/hub` of the scanner, over a writable `HF_HOME`, and run the scanner offline:

```bash
docker run --mount type=image,source=ghcr.io/anthony-spruyt/llm-tool-guard-model:latest,destination=/app/.cache/huggingface/hub \
  --tmpfs /app/.cache/huggingface:mode=1777 \
  -e HF_HUB_OFFLINE=1 \
  ghcr.io/anthony-spruyt/llm-tool-guard:latest
```

In Kubernetes this is an `image` volume mounted at `$HF_HOME/hub`, with an `emptyDir` at `HF_HOME`.

## Revision

`MODEL_REVISION` in the [Dockerfile](Dockerfile) pins the model's commit sha by hand, with the sha256 of each source file in [SHA256SUMS](SHA256SUMS), which the build checks; Renovate does not track Hugging Face. The scanner takes its revision from `refs/main` and derives its verdict-cache namespace from it, so moving the pin starts a fresh cache namespace: change it on purpose.

`llm-tool-guard` lists this directory under `watch` in its `metadata.yaml`, and its `test.sh` builds this image and starts the scanner on it. A model change therefore re-runs the scanner test.

## Conversion

The `convert` build stage runs [convert/convert.py](convert/convert.py) in the uv project in [convert/](convert/): CPU torch, transformers and OpenVINO at the versions in its `uv.lock`. It calls `openvino.convert_model` with `input_ids` and `attention_mask` as i64 inputs of any batch and sequence length, then saves with `compress_to_fp16=False`. It needs about 4 GB of RAM.

The same step then fails the build unless the IR scores like the original. It scores the texts in [convert/parity.jsonl](convert/parity.jsonl) one at a time with torch and with the saved IR on the CPU in f32, and compares the injection score:

- Any difference above 1e-4 fails the build. The last build's largest was about 1e-6.
- The fixture must keep at least 16 texts that score between 0.5 and 0.99 and one text of 1000 or more tokens, so it cannot shrink into proving nothing.

The texts are public: excerpts of the `deepset/prompt-injections`, `Lakera/gandalf_ignore_instructions` and `jackhhao/jailbreak-classification` datasets.

The scanner compiles the IR with the same OpenVINO release. Both pins are `openvino==` lines in `pyproject.toml` files that Renovate moves together, and `llm-tool-guard/test.sh` fails when they differ.

## Download tooling

[requirements.txt](requirements.txt) locks `huggingface_hub` and every dependency of it with hashes, and the build installs it with `--require-hashes`. Renovate keeps it current. To bump by hand, edit [requirements.in](requirements.in) and re-run the command in the header of `requirements.txt`.
