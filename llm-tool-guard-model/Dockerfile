# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:82abc9f53600280b0757126f83c5a7d47088592d2acb6b4c0b9e97f76865508c
FROM docker.io/astral/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:${PYTHON_VERSION} AS download

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt

# Pinned by hand: a new revision starts a fresh verdict-cache namespace in llm-tool-guard, so move it on purpose. Update SHA256SUMS with it.
ARG MODEL=Horizon-Labs/prompt-injection-guard-base
ARG MODEL_REVISION=e4fbfc6f603e24c675cdf310c3b8d7abaa825666

COPY SHA256SUMS .

# /hub is the cache the image ships, with every file the scanner loads except the weights, which only feed the converter.
# A download by commit sha writes no refs/main, and the scanner resolves the model through it.
RUN hf download "$MODEL" config.json tokenizer.json tokenizer_config.json special_tokens_map.json \
      --revision "$MODEL_REVISION" --cache-dir /hub \
    && hf download "$MODEL" model.safetensors --revision "$MODEL_REVISION" --cache-dir /weights \
    && model_dir="$(find /hub -maxdepth 1 -name 'models--*')" \
    && mkdir -p "$model_dir/refs" \
    && printf '%s' "$MODEL_REVISION" > "$model_dir/refs/main" \
    && weights="$(echo /weights/models--*/snapshots/"$MODEL_REVISION")" \
    && sed -e "/model.safetensors\$/ s|  |  $weights/|" -e "/model.safetensors\$/! s|  |  $model_dir/snapshots/$MODEL_REVISION/|" SHA256SUMS > /build/sums \
    && sha256sum --strict -c /build/sums \
    && rm -rf /hub/.locks \
    && find /hub -name '*.lock' -delete

FROM python:${PYTHON_VERSION} AS convert

WORKDIR /convert

ARG UV_PROJECT_ENVIRONMENT=/opt/convert UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy

COPY convert/pyproject.toml convert/uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-build --no-dev

COPY convert/convert.py convert/parity.jsonl ./
# Mounted and linked, not COPYed: the CI build cache stores every layer, and a copy of the weights or the IR is one more.
# Fails the build when the IR scores the parity texts differently from the original.
RUN --mount=from=download,source=/hub,target=/hub \
    --mount=from=download,source=/weights,target=/weights \
    mkdir /source \
    && ln -s /hub/models--*/snapshots/*/* /weights/models--*/snapshots/*/* /source/ \
    && /opt/convert/bin/python convert.py

FROM python:${PYTHON_VERSION} AS assemble
COPY --from=download /hub /hub

# Fixed owner, modes and mtimes: the same revision must give byte-identical layers, or every node re-pulls the weights.
RUN --mount=from=convert,source=/ir,target=/ir \
    snapshot="$(echo /hub/models--*/snapshots/*)" \
    && cp /ir/openvino_model.xml /ir/openvino_model.bin "$snapshot/" \
    && chown -R 0:0 /hub \
    && find /hub -type d -exec chmod 755 {} + \
    && find /hub -type f -exec chmod 644 {} + \
    && find /hub -exec touch -h -d @0 {} +

FROM scratch
COPY --from=assemble /hub/ /
USER 1000:1000
HEALTHCHECK NONE
