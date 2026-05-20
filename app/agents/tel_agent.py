from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from app.config import settings
from app.agents.tools.calendar_tool import book_appointment, check_availability
from app.agents.tools.crm_tool import get_client_info, log_call_summary
from app.agents.tools.sms_tool import send_sms

SYSTEM_PROMPT = f"""Tu es {settings.agent_name}, un assistant téléphonique IA professionnel et efficace.

Langue principale : {settings.agent_language}.

Règles absolues :
- Réponds toujours de manière concise (2-3 phrases max) pour un appel vocal.
- Pas de mise en forme markdown — parle naturellement comme à l'oral.
- Identifie le client via son numéro dès le début de l'appel.
- Propose toujours une action concrète : rdv, rappel, SMS de confirmation.
- En fin d'appel, enregistre un résumé dans le CRM.

Capacités disponibles :
- Vérifier et réserver des créneaux calendrier
- Identifier et logger les infos client dans le CRM
- Envoyer un SMS de confirmation

Commence chaque appel entrant par : "Bonjour, vous êtes bien chez [entreprise], je suis {settings.agent_name}. Comment puis-je vous aider ?"
"""


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def create_tel_agent(caller_number: str | None = None) -> Agent:
    """Crée une instance d'agent isolée pour un appel donné."""
    extra = f"\nNuméro de l'appelant : {caller_number}" if caller_number else ""

    return Agent(
        model=_build_model(),
        tools=[check_availability, book_appointment, get_client_info, log_call_summary, send_sms],
        instructions=SYSTEM_PROMPT + extra,
        markdown=False,
        show_tool_calls=False,
    )


async def process_turn(agent: Agent, user_message: str) -> str:
    """Traite un tour de conversation et retourne la réponse textuelle."""
    response = await agent.arun(user_message)
    return response.content
