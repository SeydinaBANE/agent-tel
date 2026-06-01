from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from app.config import settings
from app.telephony.ws_auth import create_ws_token


def _ws_url(caller: str) -> str:
    base = f"{settings.public_url.replace('https', 'wss').replace('http', 'ws')}/ws/stream"
    token = create_ws_token(caller)
    if token:
        return f"{base}?token={token}"
    return base


def build_inbound_twiml(caller: str) -> str:
    """Génère le TwiML pour connecter l'appel entrant au Media Stream WebSocket."""
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=_ws_url(caller))
    stream.parameter(name="caller", value=caller)
    connect.append(stream)
    response.append(connect)
    return str(response)
