from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from app.config import settings


def build_inbound_twiml(caller: str) -> str:
    """Génère le TwiML pour connecter l'appel entrant au Media Stream WebSocket."""
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"{settings.public_url.replace('https', 'wss').replace('http', 'ws')}/ws/stream")
    stream.parameter(name="caller", value=caller)
    connect.append(stream)
    response.append(connect)
    return str(response)
