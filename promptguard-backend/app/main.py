"""REST API with request validation, local auth option, rate limits and audit summaries."""
import hmac
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import Settings
from .schemas import TextInput, SimulationInput, PolicyInput, SuiteInput
from .scenarios import CASES
from .detection import analyze
from .policy import check
from .engines import Engine, ProviderError
from .service import Service, DISCLAIMER
from .store import Store

class BodyLimit:
    """Bound streamed request bytes, not just the caller's Content-Length header."""
    def __init__(self, app, maximum=65536):
        self.app, self.maximum = app, maximum
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.maximum:
                response = JSONResponse({"detail": "Request body exceeds 64 KiB."}, status_code=413)
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)

def create_app(settings=None):
    cfg = settings or Settings.from_env()
    cfg.validate()
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(Engine(cfg), Store(cfg.db_path))
        yield
    app = FastAPI(title="PromptGuard MDC Backend", version="1.0.0", lifespan=lifespan,
                  description="Educational prompt injection lab. No real tools execute. Use /docs to try the APIs.")
    app.state.settings = cfg
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(cfg.allowed_hosts))
    if cfg.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])
    buckets, lock = {}, threading.Lock()
    bearer_scheme = HTTPBearer(auto_error=False)
    def authorize(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
        if cfg.api_key:
            header = request.headers.get("Authorization", "")
            if not hmac.compare_digest(header.encode(), ("Bearer " + cfg.api_key).encode()):
                raise HTTPException(401, "Missing or invalid API bearer key.", headers={"WWW-Authenticate": "Bearer"})
        ip = request.client.host if request.client else "local"
        now = time.monotonic()
        with lock:
            # Ignore forwarded headers. One-process, per-peer in-memory limiter for this lab.
            for key in list(buckets):
                if not buckets[key] or now - buckets[key][-1] >= 60:
                    del buckets[key]
            if ip not in buckets and len(buckets) >= 4096:
                raise HTTPException(429, "Rate-limiter capacity reached.", headers={"Retry-After": "60"})
            q = buckets.setdefault(ip, deque())
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= cfg.requests_per_minute:
                raise HTTPException(429, "Rate limit exceeded.", headers={"Retry-After": "60"})
            q.append(now)
    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Pydantic's default errors may echo sensitive submitted input. Omit it.
        errors = [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)
    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({"detail": "AI provider unavailable or returned invalid output. No simulation record was saved. Check server-side provider settings; do not retry blindly."}, status_code=502)
    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response
    @app.get("/health", tags=["System"])
    def health():
        return {"status": "ok", "engine": cfg.engine, "version": "1.0.0", "tool_execution": False,
                "authentication_required": bool(cfg.api_key)}
    api = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)])
    @api.get("/scenarios", tags=["Scenarios"])
    def scenarios():
        return {"scenarios": [{"id": k, **v} for k, v in CASES.items()], "disclaimer": DISCLAIMER}
    @api.post("/analyze", tags=["Analysis"])
    def analysis(body: TextInput):
        return analyze(body.text)
    @api.post("/policy/check", tags=["Policy"])
    def policy(body: PolicyInput):
        return check(body.proposal.model_dump(), body.defenses)
    @api.post("/simulations", tags=["Simulations"], status_code=201)
    def simulate(body: SimulationInput, request: Request):
        return request.app.state.service.simulate(body)
    @api.post("/tests/run", tags=["Evaluation"])
    def suite(body: SuiteInput, request: Request):
        if cfg.engine == "openai" and not cfg.allow_live_suite:
            raise HTTPException(409, "Live suite is disabled to avoid unexpected costs. Set PG_ALLOW_LIVE_SUITE=1 to enable 14 provider calls per run.")
        results = [request.app.state.service.simulate(SimulationInput(scenario_id=k, defenses=body.defenses)) for k in CASES]
        counts = {state: sum(r["evaluation"]["safety_check"] == state for r in results) for state in ["pass", "fail", "inconclusive"]}
        return {"engine": cfg.engine, "defenses": body.defenses.model_dump(), "total": len(results),
                "safety_checks": counts, "legitimate_task_checks_passed": sum(r["evaluation"]["task_check"] == "pass" for r in results),
                "results": [{"id": r["id"], "scenario_id": r["scenario_id"], "evaluation": r["evaluation"], "policy": r["defended"]["policy"]} for r in results],
                "disclaimer": "Scripted assertions in demo mode; narrow observations in live mode. Not a universal attack-resistance score."}
    @api.get("/logs", tags=["Audit summaries"])
    def logs(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return request.app.state.service.store.list(limit, offset)
    @api.get("/logs/export", tags=["Audit summaries"])
    def export(request: Request, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
        data = request.app.state.service.store.list(limit, offset)
        data["note"] = "Summary-only export. Paginate using offset until all records are retrieved."
        return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="promptguard-audit-summaries.json"'})
    @api.get("/logs/{record_id}", tags=["Audit summaries"])
    def log(record_id: str, request: Request):
        record = request.app.state.service.store.get(record_id)
        if record is None:
            raise HTTPException(404, "Simulation summary not found.")
        return record
    app.include_router(api)
    return app
