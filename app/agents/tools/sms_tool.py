from agno.tools import tool
from twilio.rest import Client

from app.config import settings

_twilio = Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _send_sms(to: str, message: str) -> str:
    msg = _twilio.messages.create(
        body=message,
        from_=settings.twilio_phone_number,
        to=to,
    )
    return f"SMS envoyé à {to} (SID: {msg.sid})"


send_sms = tool(
    description="Envoie un SMS de confirmation ou de suivi à un numéro de téléphone."
)(_send_sms)
