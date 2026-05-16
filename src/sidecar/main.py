import asyncio
import time
import json
import logging
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Response, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Configure clean edge-native standard logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kubeedge-stability-sidecar")

LLM_BASE_URL = "http://127.0.0.1:8000"
IS_WARMED_UP = False
IS_WARMING_UP = False  # State latch to prevent probe stampedes

# Strict concurrency semaphore to protect resource-constrained edge CPUs
CONCURRENCY_SEMAPHORE = asyncio.Semaphore(1)

class SummarizeRequest(BaseModel):
    text: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cleanly manages the asynchronous HTTP client pooling lifecycle."""
    app.state.client = httpx.AsyncClient(base_url=LLM_BASE_URL, timeout=60.0)
    yield
    await app.state.client.aclose()
    logger.info("Shared HTTPX client pool closed successfully.")

app = FastAPI(title="KubeEdge LLM Stability Sidecar", lifespan=lifespan)

@app.get("/health/live")
def liveness_check():
    """Confirms the sidecar process itself is alive."""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness_check():
    """
    Blocks edge-routing topology until the core engine has 
    mapped the model into RAM and fully executed cache pre-warming.
    Prevents parallel warmup requests via an initialization state latch.
    """
    global IS_WARMED_UP, IS_WARMING_UP
    if IS_WARMED_UP:
        return {"status": "ready"}
        
    if IS_WARMING_UP:
        return Response(
            content='{"status": "initializing_cache"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )
        
    try:
        # Check if the underlying engine server is up
        response = await app.state.client.get("/v1/models", timeout=2.0)
        if response.status_code == 200:
            IS_WARMING_UP = True  # Engage latch before starting slow warmup path
            logger.info("LLM engine detected. Initiating cold-start prefill warm-up sequence...")
            
            warmup_payload = {
                "model": "qwen2.5-0.5b",
                "messages": [{"role": "user", "content": "warmup"}],
                "max_tokens": 1,
                "stream": False
            }
            # Absorb the severe initial prefill latency safely before turning Ready
            await app.state.client.post("/v1/chat/completions", json=warmup_payload, timeout=45.0)
            IS_WARMED_UP = True
            IS_WARMING_UP = False
            logger.info("Warm-up execution completed. Pod is now officially Ready to take traffic.")
            return {"status": "ready"}
            
    except Exception as e:
        IS_WARMING_UP = False  # Reset state latch to allow retries if initialization failed
        logger.warning(f"Readiness check failed. Engine is still initializing: {e}")
        
    return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

async def telemetry_stream_processor(response: httpx.Response, start_time: float):
    """Wraps streaming execution chunks to log live, accurate TTFT and throughput metrics."""
    ttft_captured = False
    total_chunks = 0
    
    async for chunk in response.aiter_bytes():
        if not ttft_captured:
            ttft_ms = int((time.time() - start_time) * 1000)
            logger.info(f"[METRIC] Time to First Token (TTFT): {ttft_ms}ms")
            ttft_captured = True
        total_chunks += 1
        yield chunk
        
    total_latency = int((time.time() - start_time) * 1000)
    logger.info(f"[METRIC] Total Transaction Latency: {total_latency}ms across {total_chunks} chunk frames.")

@app.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    """
    Intercepts streaming/unary traffic, enforces cgroup-protective 
    concurrency boundaries, and records live edge operational telemetry.
    """
    if not IS_WARMED_UP:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model engine context is still warming up or unavailable."
        )

    # Concurrency boundary check to safeguard against CPU context thrashing
    if CONCURRENCY_SEMAPHORE.locked():
        logger.warning("Node under intense pressure. Dropping incoming inference demand with 429 status.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Edge node inference capacity saturated. Request throttled for runtime stability."
        )

    async with CONCURRENCY_SEMAPHORE:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)  # Scrub host to pass strict reverse-proxy parsing

        start_time = time.time()
        
        req = app.state.client.build_request("POST", "/v1/chat/completions", content=body, headers=headers)
        resp = await app.state.client.send(req, stream=True)

        return StreamingResponse(
            telemetry_stream_processor(resp, start_time),
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )

@app.post("/v1/tasks/summarize")
async def process_summarize_task(req: SummarizeRequest):
    """
    Fulfills the optional LFX task scenario requirement.
    Transforms raw operational logs into structured single-sentence prompt tasks.
    """
    if not IS_WARMED_UP:
        raise HTTPException(status_code=503, detail="Model runtime not fully initialized")

    async with CONCURRENCY_SEMAPHORE:
        system_prompt = "You are an industrial edge assistant. Summarize the following log precisely in one brief sentence."
        optimized_prompt = f"{system_prompt}\n\nLog: {req.text}\n\nSummary:"
        
        payload = {
            "model": "qwen2.5-0.5b",
            "messages": [{"role": "user", "content": optimized_prompt}],
            "max_tokens": 96,
            "temperature": 0.1,
            "stream": False
        }
        
        start_time = time.time()
        try:
            response = await app.state.client.post("/v1/chat/completions", json=payload, timeout=30.0)
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Inference engine error during task completion")
                
            result = response.json()
            logger.info(f"[METRIC] Task execution completed in {latency_ms}ms")
            
            return {
                "summary": result["choices"][0]["message"]["content"].strip(),
                "latency_ms": latency_ms,
                "tokens_generated": result["usage"]["completion_tokens"]
            }
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Inference engine timeout during summarization task")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)