"""Architecture multi-agents : superviseur + agents spécialisés.

Le superviseur délègue les tâches via deux outils dynamiques :
- delegate_to_calendar : réserve/vérifie les créneaux
- delegate_to_crm      : interroge/log le CRM

Chaque spécialiste a un contexte minimal et n'appelle que ses outils propres.
"""

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from app.agents.tools.calendar_tool import book_appointment, check_availability
from app.agents.tools.crm_tool import get_client_info, log_call_summary
from app.agents.tools.escalation_tool import request_human_escalation
from app.agents.tools.sms_tool import send_sms
from app.config import settings


def _model() -> OpenAILike:
    return OpenAILike(
        id=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _calendar_specialist() -> Agent:
    return Agent(
        name="CalendarSpecialist",
        model=_model(),
        tools=[check_availability, book_appointment],
        instructions=(
            "Tu es un assistant de planification. "
            "Réponds uniquement aux questions de disponibilité et de réservation de créneaux. "
            "Sois concis (1-2 phrases max)."
        ),
        markdown=False,
    )


def _crm_specialist() -> Agent:
    return Agent(
        name="CRMSpecialist",
        model=_model(),
        tools=[get_client_info, log_call_summary],
        instructions=(
            "Tu es un assistant CRM. "
            "Réponds uniquement aux questions sur les informations client et l'enregistrement d'activités. "
            "Sois concis (1-2 phrases max)."
        ),
        markdown=False,
    )


def create_team_agent(
    caller_number: str | None = None, memory_records: list | None = None
) -> Agent:
    """Crée un superviseur qui orchestre les agents spécialisés."""
    calendar_agent = _calendar_specialist()
    crm_agent = _crm_specialist()

    # Outils de délégation — le superviseur appelle les spécialistes
    async def _delegate_to_calendar(query: str) -> str:
        """Délègue une demande de calendrier à l'agent spécialisé."""
        response = await calendar_agent.arun(query)
        return response.content

    async def _delegate_to_crm(query: str) -> str:
        """Délègue une demande CRM à l'agent spécialisé."""
        response = await crm_agent.arun(query)
        return response.content

    from agno.tools import tool

    delegate_to_calendar = tool(
        description="Vérifie les créneaux disponibles ou réserve un rendez-vous."
    )(_delegate_to_calendar)

    delegate_to_crm = tool(
        description="Récupère les informations d'un client CRM ou enregistre une activité."
    )(_delegate_to_crm)

    from app.agents.tel_agent import SYSTEM_PROMPT, _format_memory

    extra = f"\nNuméro de l'appelant : {caller_number}" if caller_number else ""
    if memory_records:
        extra += _format_memory(memory_records)

    supervisor_instructions = (
        SYSTEM_PROMPT
        + extra
        + "\n\nArchitecture : délègue les tâches calendrier à `delegate_to_calendar` "
        "et les tâches CRM à `delegate_to_crm`. "
        "Utilise `send_sms` directement pour les SMS."
    )

    return Agent(
        name="Superviseur",
        model=_model(),
        tools=[delegate_to_calendar, delegate_to_crm, send_sms, request_human_escalation],
        instructions=supervisor_instructions,
        markdown=False,
    )
