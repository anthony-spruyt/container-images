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
    """
    Initialize scanner resources at application startup and mark the service as ready.
    
    This lifespan context is used by FastAPI on startup: it loads scanner resources and sets the module readiness flag (`_STATE["ready"] = True`) before yielding control to run the application.
    """
    scanner.load()
    _STATE["ready"] = True
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """
    Return liveness status for the service.
    
    Returns:
        dict: `{"status": "ok"}` indicating the service is alive.
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """
    Report whether the service is ready to receive traffic.
    
    Returns:
        `{"status": "ok"}` if the application is marked ready; otherwise an HTTP 503 response with `{"status": "not ready"}`.
    """
    if not _STATE["ready"]:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"status": "ok"}


# --- LiteLLM guardrail format ---

class _StructuredMsg(BaseModel):
    """A single message in a structured conversation."""

    role: str
    content: object

    def text(self) -> str:
        """
        Return the plain-text representation of this structured message's content.
        
        If the content is a string, that string is returned; if it's a list, the `text` fields of elements with `"type" == "text"` are joined with newlines; otherwise the content is converted to a string.
        
        Returns:
            str: The extracted plain-text string.
        """
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
    """
    Build a single prompt string from a LiteLLM request.
    
    If `req.texts` contains items, those strings are joined with newline characters and returned.
    Otherwise, the `text()` results of `req.structured_messages` with `role == "user"` are joined with newlines.
    Returns an empty string if no text content is found.
    
    Returns:
        str: The composed prompt string.
    """
    if req.texts:
        return "\n".join(req.texts)
    parts = [m.text() for m in req.structured_messages if m.role == "user"]
    return "\n".join(parts)


def _safe_id(value: str) -> str:
    """Strip newlines to prevent log injection."""
    return value.replace("\n", " ").replace("\r", " ")


@app.post("/")
async def litellm_guardrail(req: LiteLLMRequest):
    """
    Evaluate a LiteLLM request for prompt-injection and produce a guardrail action.
    
    Parameters:
        req (LiteLLMRequest): The incoming LiteLLM payload; prompt is extracted from `texts` or from user-role entries in `structured_messages`.
    
    Returns:
        dict: A response object with an `action` key:
            - `"BLOCKED"` with `blocked_reason` set to "prompt injection detected (score: <score>)" when the prompt is classified as unsafe.
            - `"NONE"` when no prompt is found or the prompt is considered safe.
    """
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
    """
    Scan a provided prompt for prompt-injection and return an llm-guard-api compatible result.
    
    Parameters:
        req (ScanPromptRequest): Request containing the `prompt` string to scan.
    
    Returns:
        dict: {
            "is_valid": `true` if the prompt is considered safe, `false` otherwise,
            "sanitized_prompt": the (unchanged) prompt string provided in the request,
            "scanners": mapping of scanner names to their numeric scores, e.g. {"PromptInjection": <score>}
        }
    """
    loop = asyncio.get_running_loop()
    is_safe, score = await loop.run_in_executor(None, scanner.scan, req.prompt)
    return {
        "is_valid": is_safe,
        "sanitized_prompt": req.prompt,
        "scanners": {"PromptInjection": score},
    }


if __name__ == "__main__":
    uvicorn.run(app, host=config.LISTEN_HOST, port=config.LISTEN_PORT)
