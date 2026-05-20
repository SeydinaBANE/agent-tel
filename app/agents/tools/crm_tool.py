from agno.tools import tool

from app.services.crm import get_contact, log_activity


async def _get_client_info(phone_number: str) -> str:
    contact = await get_contact(phone_number)
    if not contact:
        return f"Aucun client trouvé pour le numéro {phone_number}."
    name = contact.get("name", "Inconnu")
    account = contact.get("account", contact.get("properties", {}).get("lifecyclestage", "?"))
    last = contact.get("last_contact", contact.get("properties", {}).get("lastmodifieddate", "?"))
    return f"Client : {name} | Compte : {account} | Dernier contact : {last}"


async def _log_call_summary(phone_number: str, summary: str) -> str:
    return await log_activity(phone_number, summary)


get_client_info = tool(
    description="Récupère les informations d'un client depuis le CRM via son numéro de téléphone."
)(_get_client_info)

log_call_summary = tool(
    description="Enregistre un résumé de l'appel dans le CRM pour un client donné."
)(_log_call_summary)
