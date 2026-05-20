import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


async def notify_call_ended(
    call_sid: str,
    caller: str,
    duration: float,
    transcript: list[str],
) -> None:
    """Envoie une notification Slack/Teams en fin d'appel. Silencieux si non configuré."""
    if not settings.slack_webhook_url:
        return

    turns = len(transcript) // 2
    last_line = transcript[-1] if transcript else "—"
    text = (
        f"*Appel terminé* — `{call_sid}`\n"
        f"• Numéro : {caller}\n"
        f"• Durée : {duration}s — {turns} échange(s)\n"
        f"• Dernier message : _{last_line}_"
    )

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(settings.slack_webhook_url, json={"text": text})
            resp.raise_for_status()
        logger.info("slack_notified", call_sid=call_sid)
    except Exception as exc:
        logger.error("slack_webhook_error", call_sid=call_sid, error=str(exc))
