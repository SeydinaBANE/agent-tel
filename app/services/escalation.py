"""Transfert d'appel vers un conseiller humain via Twilio REST API."""

import asyncio

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

ESCALATION_SENTINEL = "__ESCALADE__"


async def transfer_call(call_sid: str, reason: str = "") -> bool:
    """Redirige l'appel en cours vers ESCALATION_PHONE. Retourne True si réussi."""
    if not settings.escalation_phone:
        logger.warning("escalation_no_phone_configured", call_sid=call_sid)
        return False

    twiml = (
        f"<Response>"
        f"<Say language='fr-FR'>Je vous transfère vers un conseiller. Veuillez patienter.</Say>"
        f"<Dial><Number>{settings.escalation_phone}</Number></Dial>"
        f"</Response>"
    )

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        await asyncio.to_thread(
            client.calls(call_sid).update,
            twiml=twiml,
        )
        logger.info(
            "call_escalated", call_sid=call_sid, to=settings.escalation_phone, reason=reason
        )
        return True
    except Exception as exc:
        logger.error("escalation_error", call_sid=call_sid, error=str(exc))
        return False
