# llm-tool-guard-model

The model weights for [llm-tool-guard](../llm-tool-guard/README.md), as an image of their own. The image holds only a Hugging Face hub cache for `Horizon-Labs/prompt-injection-guard-base` (`config.json`, `model.safetensors` and the tokenizer files), so the scanner image stays small and the weights are pulled once per model revision, not once per scanner release.

The files sit at the image root, laid out as a hub cache: `models--Horizon-Labs--prompt-injection-guard-base/` with `blobs/`, `snapshots/<revision>/` and `refs/main` holding the revision. The image has no shell and no command; it only supplies files.

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

`MODEL_REVISION` in the [Dockerfile](Dockerfile) pins the model's commit sha by hand; Renovate does not track Hugging Face. The scanner takes its revision from `refs/main` and derives its verdict-cache namespace from it, so moving the pin starts a fresh cache namespace: change it on purpose.

`llm-tool-guard` lists this directory under `watch` in its `metadata.yaml`, and its `test.sh` builds this image and starts the scanner on it. A weights change therefore re-runs the scanner test.
