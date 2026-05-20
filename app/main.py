import logging
from fastapi import FastAPI, Request, WebSocket, Query
from fastapi.responses import PlainTextResponse
from app.telephony.inbound import build_inbound_twiml
from app.telephony.outbound import build_outbound_twiml, initiate_outbound_call
from app.telephony.stream import handle_media_stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="Agent Téléphonique IA", version="1.0.0")


# --- Santé ---

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Webhooks Twilio (appels entrants) ---

@app.post("/twiml/inbound", response_class=PlainTextResponse)
async def twiml_inbound(request: Request):
    form = await request.form()
    caller = form.get("From", "inconnu")
    twiml = build_inbound_twiml(caller=caller)
    return PlainTextResponse(content=twiml, media_type="application/xml")


# --- TwiML pour appels sortants ---

@app.get("/twiml/outbound", response_class=PlainTextResponse)
async def twiml_outbound(
    caller: str = Query(default="inconnu"),
    context: str = Query(default=""),
):
    twiml = build_outbound_twiml(caller=caller, context=context)
    return PlainTextResponse(content=twiml, media_type="application/xml")


# --- API : déclencher un appel sortant ---

@app.post("/calls/outbound")
async def create_outbound_call(request: Request):
    body = await request.json()
    to = body.get("to")
    context = body.get("context", "")
    if not to:
        return {"error": "Le champ 'to' est requis (numéro E.164)"}
    call_sid = initiate_outbound_call(to=to, context=context)
    return {"call_sid": call_sid, "to": to, "status": "initiated"}


# --- WebSocket : flux audio temps réel ---

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await handle_media_stream(websocket)
