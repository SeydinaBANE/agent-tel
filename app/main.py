import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request, WebSocket
from fastapi.responses import PlainTextResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.db.repository import get_recent_calls
from app.db.session import init_db
from app.logger import setup_logging
from app.middleware.twilio_auth import verify_twilio_signature
from app.routers.admin import router as admin_router
from app.telephony.inbound import build_inbound_twiml
from app.telephony.outbound import build_outbound_twiml, initiate_outbound_call
from app.telephony.stream import handle_media_stream

setup_logging()

_E164 = re.compile(r"^\+[1-9]\d{1,14}$")

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.2)
    await init_db()
    yield


app = FastAPI(title="Agent Téléphonique IA", version="4.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.include_router(admin_router)


# --- Santé ---


@app.get("/health")
async def health():
    call_count = len(await get_recent_calls(limit=1))
    return {
        "status": "ok",
        "version": app.version,
        "db": "ok" if call_count >= 0 else "error",
        "uptime_hint": "use /admin/calls for metrics",
    }


# --- Webhooks Twilio (appels entrants) — signature validée ---


@app.post(
    "/twiml/inbound",
    response_class=PlainTextResponse,
    dependencies=[Depends(verify_twilio_signature)],
)
async def twiml_inbound(request: Request):
    form = await request.form()
    caller = form.get("From", "inconnu")
    return PlainTextResponse(
        content=build_inbound_twiml(caller=str(caller)), media_type="application/xml"
    )


# --- TwiML pour appels sortants ---


@app.get("/twiml/outbound", response_class=PlainTextResponse)
async def twiml_outbound(
    caller: str = Query(default="inconnu"),
    context: str = Query(default=""),
):
    return PlainTextResponse(
        content=build_outbound_twiml(caller=caller, context=context),
        media_type="application/xml",
    )


# --- API : déclencher un appel sortant (rate-limited) ---


@app.post("/calls/outbound")
@limiter.limit(f"{settings.rate_limit_calls_per_minute}/minute")
async def create_outbound_call(request: Request):
    body = await request.json()
    to = body.get("to")

    if not to:
        return {"error": "Le champ 'to' est requis (numéro E.164)"}
    if not _E164.match(to):
        return {"error": f"Format E.164 invalide : '{to}'. Attendu : +33600000001"}

    call_sid = initiate_outbound_call(to=to, context=body.get("context", ""))
    return {"call_sid": call_sid, "to": to, "status": "initiated"}


# --- WebSocket : flux audio temps réel ---


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await handle_media_stream(websocket)
