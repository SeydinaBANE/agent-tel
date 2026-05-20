import re
from collections.abc import AsyncGenerator

from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.utils.events import RunCompletedEvent, RunContentEvent, ToolCallCompletedEvent

from app.agents.tools.calendar_tool import book_appointment, check_availability
from app.agents.tools.crm_tool import get_client_info, log_call_summary
from app.agents.tools.escalation_tool import request_human_escalation
from app.agents.tools.sms_tool import send_sms
from app.config import settings

SYSTEM_PROMPT = f"""Tu es {settings.agent_name}, un assistant téléphonique IA professionnel et efficace.

Langue principale : {settings.agent_language}.

Règles absolues :
- Réponds toujours de manière concise (2-3 phrases max) pour un appel vocal.
- Pas de mise en forme markdown — parle naturellement comme à l'oral.
- Identifie le client via son numéro dès le début de l'appel.
- Propose toujours une action concrète : rdv, rappel, SMS de confirmation.
- En fin d'appel, enregistre un résumé dans le CRM.
- Si la demande dépasse tes capacités ou si le client l'exige, utilise l'outil de transfert.

Capacités disponibles :
- Vérifier et réserver des créneaux calendrier
- Identifier et logger les infos client dans le CRM
- Envoyer un SMS de confirmation
- Transférer vers un conseiller humain

Commence chaque appel entrant par : "Bonjour, vous êtes bien chez [entreprise], je suis {settings.agent_name}. Comment puis-je vous aider ?"
"""

_SPECIAL_TOKENS = {
    "__START__": "L'appel vient de commencer. Dis bonjour chaleureusement.",
    "__TIMEOUT__": "L'appelant n'a plus répondu depuis un moment. Dis poliment au revoir et que tu restes disponible.",
    "__END__": "L'appel se termine. Remercie le client et enregistre le résumé dans le CRM.",
}


def _build_model() -> OpenAILike:
    return OpenAILike(
        id=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _format_memory(records: list) -> str:
    if not records:
        return ""
    lines = ["\nHistorique des appels précédents de ce client :"]
    for r in records[:3]:
        date = r.created_at.strftime("%d/%m/%Y") if r.created_at else "?"
        snippet = (r.transcript or "")[:200].replace("\n", " | ")
        lines.append(f"- {date} ({r.duration_secs}s, {r.turns} tours) : {snippet}")
    return "\n".join(lines)


def create_tel_agent(caller_number: str | None = None, memory_records: list | None = None) -> Agent:
    """Crée une instance d'agent isolée pour un appel donné."""
    extra = f"\nNuméro de l'appelant : {caller_number}" if caller_number else ""
    if memory_records:
        extra += _format_memory(memory_records)

    return Agent(
        model=_build_model(),
        tools=[
            check_availability,
            book_appointment,
            get_client_info,
            log_call_summary,
            send_sms,
            request_human_escalation,
        ],
        instructions=SYSTEM_PROMPT + extra,
        markdown=False,
    )


async def process_turn(agent: Agent, user_message: str) -> str:
    """Traite un tour de conversation et retourne la réponse textuelle."""
    resolved = _SPECIAL_TOKENS.get(user_message, user_message)
    response = await agent.arun(resolved)
    return response.content


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_ESCALADE_TOOL = "request_human_escalation"


async def process_turn_streaming(
    agent: Agent, user_message: str
) -> AsyncGenerator[tuple[str, str], None]:
    """Génère la réponse token par token.

    Yields ``("text", sentence)`` pour chaque phrase complète dès qu'elle est
    disponible, et ``("escalade", reason)`` si l'outil d'escalade est appelé.
    Les tokens spéciaux (``__START__`` etc.) sont résolus en une seule passe non-streamée.
    """
    resolved = _SPECIAL_TOKENS.get(user_message, user_message)

    # Tokens spéciaux — courtes réponses, pas besoin de streamer
    if user_message in _SPECIAL_TOKENS:
        response = await agent.arun(resolved)
        yield ("text", response.content)
        return

    buffer = ""
    async for event in agent.arun(resolved, stream=True, stream_events=True):  # type: ignore[misc]
        if isinstance(event, RunContentEvent) and event.content:
            buffer += str(event.content)
            # Découpe en phrases dès qu'une frontière est détectée
            while True:
                match = _SENTENCE_BOUNDARY.search(buffer)
                if not match:
                    break
                sentence = buffer[: match.start() + 1].strip()
                buffer = buffer[match.end() :].strip()
                if sentence:
                    yield ("text", sentence)

        elif isinstance(event, ToolCallCompletedEvent) and event.tool:
            if event.tool.tool_name == _ESCALADE_TOOL:
                yield ("escalade", event.tool.result or "")

        elif isinstance(event, RunCompletedEvent):
            break

    if buffer.strip():
        yield ("text", buffer.strip())
