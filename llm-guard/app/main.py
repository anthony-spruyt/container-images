"""FastAPI service: LiteLLM guardrail and llm-guard-api compatible endpoints."""
import asyncio
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

_STATE = {"ready": False}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load model on startup and mark service ready."""
    scanner.load()
    _STATE["ready"] = True
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness probe."""
    if not _STATE["ready"]:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"status": "ok"}


# --- LiteLLM guardrail format ---

class _StructuredMsg(BaseModel):
    """A single message in a structured conversation."""

    role: str
    content: object

    def text(self) -> str:
        """Extract plain text from string or content-part list."""
        c = self.content
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(
                str(p.get("text", ""))
                for p in c
                if isinstance(p, dict) and p.get("type") == "text"
            )
        return str(c)


class LiteLLMRequest(BaseModel):
    """Request body from a LiteLLM guardrail hook."""

    texts: list[str] = []
    structured_messages: list[_StructuredMsg] = []
    litellm_call_id: str = ""
    litellm_trace_id: str = ""


def _extract_prompt(req: LiteLLMRequest) -> str:
    """Extract user text from a LiteLLM request."""
    if req.texts:
        return "\n".join(req.texts)
    parts = [m.text() for m in req.structured_messages if m.role == "user"]
    return "\n".join(parts)


def _safe_id(value: str) -> str:
    """Strip newlines to prevent log injection."""
    return value.replace("\n", " ").replace("\r", " ")


@app.post("/")
async def litellm_guardrail(req: LiteLLMRequest):
    """LiteLLM guardrail endpoint — returns BLOCKED or NONE."""
    prompt = _extract_prompt(req)
    if not prompt:
        return {"action": "NONE"}

    loop = asyncio.get_running_loop()
    is_safe, score = await loop.run_in_executor(None, scanner.scan, prompt)

    logger.info(
        "litellm scan",
        extra={"call_id": _safe_id(req.litellm_call_id), "is_safe": is_safe, "score": score},
    )

    if not is_safe:
        return {
            "action": "BLOCKED",
            "blocked_reason": f"prompt injection detected (score: {score})",
        }
    return {"action": "NONE"}


# --- llm-guard-api compat format ---

class ScanPromptRequest(BaseModel):
    """Request body for llm-guard-api compatible endpoints."""

    prompt: str


@app.post("/analyze/prompt")
@app.post("/scan/prompt")
async def scan_prompt(req: ScanPromptRequest):
    """llm-guard-api compatible prompt scan endpoint."""
    loop = asyncio.get_running_loop()
    is_safe, score = await loop.run_in_executor(None, scanner.scan, req.prompt)
    return {
        "is_valid": is_safe,
        "sanitized_prompt": req.prompt,
        "scanners": {"PromptInjection": score},
    }


if __name__ == "__main__":
    uvicorn.run(app, host=config.LISTEN_HOST, port=config.LISTEN_PORT)
