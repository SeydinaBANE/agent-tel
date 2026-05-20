from agno.tools import tool

from app.services.escalation import ESCALATION_SENTINEL


def _request_human_escalation(reason: str) -> str:
    """Signale une demande de transfert vers un conseiller humain.
    Le signal est détecté par stream.py qui déclenche le transfert Twilio.
    """
    return f"{ESCALATION_SENTINEL}: {reason}"


request_human_escalation = tool(
    description=(
        "Transfère l'appel vers un conseiller humain. "
        "À utiliser si la demande dépasse tes capacités ou si l'appelant l'exige."
    )
)(_request_human_escalation)
