from agno.tools import tool

_MOCK_CRM: dict[str, dict] = {
    "+33600000001": {"name": "Alice Martin", "account": "PRO", "last_contact": "2026-05-10"},
    "+33600000002": {"name": "Bob Dupont", "account": "STANDARD", "last_contact": "2026-04-22"},
}


def _get_client_info(phone_number: str) -> str:
    client = _MOCK_CRM.get(phone_number)
    if not client:
        return f"Aucun client trouvé pour le numéro {phone_number}."
    return (
        f"Client : {client['name']} | Compte : {client['account']} "
        f"| Dernier contact : {client['last_contact']}"
    )


def _log_call_summary(phone_number: str, summary: str) -> str:
    return f"Résumé enregistré pour {phone_number} : « {summary} »"


get_client_info = tool(
    description="Récupère les informations d'un client depuis le CRM via son numéro de téléphone."
)(_get_client_info)

log_call_summary = tool(
    description="Enregistre un résumé de l'appel dans le CRM pour un client donné."
)(_log_call_summary)
