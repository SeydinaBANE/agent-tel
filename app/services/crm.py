"""Adaptateur CRM HTTP générique (compatible HubSpot / Salesforce / Notion).
Si CRM_API_URL n'est pas configuré, retourne des données fictives (mode mock).
"""

import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_MOCK: dict[str, dict] = {
    "+33600000001": {"name": "Alice Martin", "account": "PRO", "last_contact": "2026-05-10"},
    "+33600000002": {"name": "Bob Dupont", "account": "STANDARD", "last_contact": "2026-04-22"},
}


def _require_crm() -> None:
    if not settings.allow_service_mocks and not settings.crm_api_url:
        raise RuntimeError(
            "CRM_API_URL non configuré et ALLOW_SERVICE_MOCKS=false. "
            "Configurez le CRM ou passez ALLOW_SERVICE_MOCKS=true."
        )


async def get_contact(phone_number: str) -> dict | None:
    if not settings.crm_api_url:
        _require_crm()
        return _MOCK.get(phone_number)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.crm_api_url}/contacts/search",
                params={"phone": phone_number},
                headers={"Authorization": f"Bearer {settings.crm_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return results[0] if results else None
    except Exception as exc:
        logger.error("crm_get_contact_error", phone=phone_number, error=str(exc))
        if not settings.allow_service_mocks:
            raise
        return None


async def log_activity(phone_number: str, summary: str) -> str:
    if not settings.crm_api_url:
        _require_crm()
        return f"[mock] Résumé enregistré pour {phone_number}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.crm_api_url}/engagements",
                json={"phone": phone_number, "note": summary, "type": "CALL"},
                headers={"Authorization": f"Bearer {settings.crm_api_key}"},
            )
            resp.raise_for_status()
            return f"Activité enregistrée (id: {resp.json().get('id', '?')})"
    except Exception as exc:
        logger.error("crm_log_activity_error", phone=phone_number, error=str(exc))
        if not settings.allow_service_mocks:
            raise
        return f"Erreur CRM : {exc}"
