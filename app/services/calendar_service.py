"""Service Google Calendar.
Si GOOGLE_CALENDAR_CREDENTIALS n'est pas configuré → mode mock (créneaux fictifs).
Sinon → appelle l'API Google Calendar avec un compte de service (service account).
"""

import asyncio
import json
from datetime import datetime, timedelta

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_MOCK_SLOTS = ["09:00", "10:30", "14:00", "15:30", "17:00"]


def _require_calendar() -> None:
    if not settings.allow_service_mocks and not settings.google_calendar_credentials:
        raise RuntimeError(
            "GOOGLE_CALENDAR_CREDENTIALS non configuré et ALLOW_SERVICE_MOCKS=false. "
            "Configurez Google Calendar ou passez ALLOW_SERVICE_MOCKS=true."
        )


async def list_free_slots(date: str) -> list[str]:
    """Retourne les créneaux libres pour une date YYYY-MM-DD."""
    if not settings.google_calendar_credentials:
        _require_calendar()
        return _MOCK_SLOTS

    try:
        return await asyncio.to_thread(_fetch_free_slots_sync, date)
    except Exception as exc:
        logger.error("calendar_free_slots_error", date=date, error=str(exc))
        if not settings.allow_service_mocks:
            raise
        return _MOCK_SLOTS


async def create_event(
    date: str, time: str, summary: str, attendee_email: str | None = None
) -> str:
    """Crée un événement Google Calendar. Retourne l'ID ou un message d'erreur."""
    if not settings.google_calendar_credentials:
        _require_calendar()
        from datetime import datetime as dt

        fake_id = f"mock_{dt.now().strftime('%Y%m%d%H%M%S')}"
        return fake_id

    try:
        return await asyncio.to_thread(_create_event_sync, date, time, summary, attendee_email)
    except Exception as exc:
        logger.error("calendar_create_event_error", error=str(exc))
        if not settings.allow_service_mocks:
            raise
        return f"Erreur Google Calendar : {exc}"


# ---------------------------------------------------------------------------
# Fonctions synchrones (exécutées dans asyncio.to_thread)
# ---------------------------------------------------------------------------


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_info = json.loads(settings.google_calendar_credentials)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _fetch_free_slots_sync(date: str) -> list[str]:
    service = _get_service()
    cal_id = settings.google_calendar_id

    day_start = datetime.fromisoformat(f"{date}T08:00:00")
    day_end = datetime.fromisoformat(f"{date}T19:00:00")

    body = {
        "timeMin": day_start.isoformat() + "Z",
        "timeMax": day_end.isoformat() + "Z",
        "items": [{"id": cal_id}],
    }
    result = service.freebusy().query(body=body).execute()
    busy_periods = result["calendars"][cal_id]["busy"]

    # Génère des créneaux de 30min et exclut les occupés
    slots: list[str] = []
    current = day_start
    while current < day_end:
        slot_end = current + timedelta(minutes=30)
        occupied = any(
            datetime.fromisoformat(b["start"].replace("Z", "")) < slot_end
            and datetime.fromisoformat(b["end"].replace("Z", "")) > current
            for b in busy_periods
        )
        if not occupied:
            slots.append(current.strftime("%H:%M"))
        current = slot_end

    return slots


def _create_event_sync(date: str, time: str, summary: str, attendee_email: str | None) -> str:
    service = _get_service()
    cal_id = settings.google_calendar_id

    start = datetime.fromisoformat(f"{date}T{time}:00")
    end = start + timedelta(minutes=30)

    event_body: dict = {
        "summary": summary,
        "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Paris"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Paris"},
    }
    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]

    event = service.events().insert(calendarId=cal_id, body=event_body).execute()
    return event["id"]
