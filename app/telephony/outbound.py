from twilio.rest import Client
from app.config import settings

_twilio = Client(settings.twilio_account_sid, settings.twilio_auth_token)


def initiate_outbound_call(to: str, context: str = "") -> str:
    """
    Lance un appel sortant vers `to`.
    `context` est transmis à l'agent via les customParameters du stream.
    """
    twiml_url = (
        f"{settings.public_url}/twiml/outbound"
        f"?caller={to}&context={context}"
    )
    call = _twilio.calls.create(
        to=to,
        from_=settings.twilio_phone_number,
        url=twiml_url,
    )
    return call.sid


def build_outbound_twiml(caller: str, context: str = "") -> str:
    """TwiML pour les appels sortants — connecte au même WebSocket."""
    from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"{settings.public_url.replace('https', 'wss').replace('http', 'ws')}/ws/stream")
    stream.parameter(name="caller", value=caller)
    stream.parameter(name="context", value=context)
    connect.append(stream)
    response.append(connect)
    return str(response)
