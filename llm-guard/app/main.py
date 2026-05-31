import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
import scanner

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ready
    scanner.load()
    _ready = True
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    if not _ready:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"status": "ok"}


# --- LiteLLM guardrail format ---

class _StructuredMsg(BaseModel):
    role: str
    content: object

    def text(self) -> str:
        c = self.content
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(p.get("text", "") for p in c if p.get("type") == "text")
        return str(c)


class LiteLLMRequest(BaseModel):
    texts: list[str] = []
    structured_messages: list[_StructuredMsg] = []
    litellm_call_id: str = ""
    litellm_trace_id: str = ""


def _extract_prompt(req: LiteLLMRequest) -> str:
    if req.texts:
        return "\n".join(req.texts)
    parts = [m.text() for m in req.structured_messages if m.role == "user"]
    return "\n".join(parts)


@app.post("/")
async def litellm_guardrail(req: LiteLLMRequest):
    prompt = _extract_prompt(req)
    if not prompt:
        return {"action": "NONE"}

    is_safe, score = scanner.scan(prompt)
    logger.info("litellm scan", extra={"call_id": req.litellm_call_id, "is_safe": is_safe, "score": score})

    if not is_safe:
        return {"action": "BLOCKED", "blocked_reason": f"prompt injection detected (score: {score})"}
    return {"action": "NONE"}


# --- llm-guard-api compat format ---

class ScanPromptRequest(BaseModel):
    prompt: str


@app.post("/analyze/prompt")
@app.post("/scan/prompt")
async def scan_prompt(req: ScanPromptRequest):
    is_safe, score = scanner.scan(req.prompt)
    return {
        "is_valid": is_safe,
        "sanitized_prompt": req.prompt,
        "scanners": {"PromptInjection": score},
    }


if __name__ == "__main__":
    uvicorn.run(app, host=config.LISTEN_HOST, port=config.LISTEN_PORT)
