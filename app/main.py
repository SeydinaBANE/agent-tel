import re

from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.responses import PlainTextResponse

from app.logger import setup_logging
from app.telephony.inbound import build_inbound_twiml
from app.telephony.outbound import build_outbound_twiml, initiate_outbound_call
from app.telephony.stream import handle_media_stream

setup_logging()

app = FastAPI(title="Agent Téléphonique IA", version="2.0.0")

_E164 = re.compile(r"^\+[1-9]\d{1,14}$")


# --- Santé ---

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Webhooks Twilio (appels entrants) ---

@app.post("/twiml/inbound", response_class=PlainTextResponse)
async def twiml_inbound(request: Request):
    form = await request.form()
    caller = form.get("From", "inconnu")
    return PlainTextResponse(content=build_inbound_twiml(caller=caller), media_type="application/xml")


# --- TwiML pour appels sortants ---

@app.get("/twiml/outbound", response_class=PlainTextResponse)
async def twiml_outbound(
    caller: str = Query(default="inconnu"),
    context: str = Query(default=""),
):
    return PlainTextResponse(content=build_outbound_twiml(caller=caller, context=context), media_type="application/xml")


# --- API : déclencher un appel sortant ---

@app.post("/calls/outbound")
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
