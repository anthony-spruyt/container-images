# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
FROM python:${PYTHON_VERSION} AS download

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt

# Pinned by hand: a new revision starts a fresh verdict-cache namespace in llm-tool-guard, so move it on purpose. Update SHA256SUMS with it.
ARG MODEL=Horizon-Labs/prompt-injection-guard-base
ARG MODEL_REVISION=e4fbfc6f603e24c675cdf310c3b8d7abaa825666

COPY SHA256SUMS .

# Only the files the scanner loads. A download by commit sha writes no refs/main, and the scanner resolves the model through it.
# Fixed owner, modes and mtimes: the same revision must give byte-identical layers, or every node re-pulls the weights.
RUN hf download "$MODEL" config.json model.safetensors tokenizer.json tokenizer_config.json special_tokens_map.json \
      --revision "$MODEL_REVISION" --cache-dir /hub \
    && model_dir="$(find /hub -maxdepth 1 -name 'models--*')" \
    && mkdir -p "$model_dir/refs" \
    && printf '%s' "$MODEL_REVISION" > "$model_dir/refs/main" \
    && sed "s|  |  $model_dir/snapshots/$MODEL_REVISION/|" SHA256SUMS > /build/sums \
    && sha256sum --strict -c /build/sums \
    && rm -rf /hub/.locks \
    && find /hub -name '*.lock' -delete \
    && chown -R 0:0 /hub \
    && find /hub -type d -exec chmod 755 {} + \
    && find /hub -type f -exec chmod 644 {} + \
    && find /hub -exec touch -h -d @0 {} +

FROM scratch
COPY --from=download /hub/ /
USER 1000:1000
HEALTHCHECK NONE
