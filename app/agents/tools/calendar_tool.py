from agno.tools import tool

from app.services.calendar_service import create_event, list_free_slots


async def _check_availability(date: str) -> str:
    slots = await list_free_slots(date)
    if not slots:
        return f"Aucun créneau disponible le {date}."
    return f"Créneaux disponibles le {date} : {', '.join(slots)}"


async def _book_appointment(date: str, time: str, client_name: str, reason: str) -> str:
    summary = f"{reason} — {client_name}"
    event_id = await create_event(date=date, time=time, summary=summary)
    if event_id.startswith("Erreur"):
        return f"Impossible de créer le rendez-vous : {event_id}"
    return (
        f"Rendez-vous confirmé pour {client_name} le {date} à {time}. "
        f"Motif : {reason}. Référence : {event_id}"
    )


check_availability = tool(
    description="Vérifie les créneaux disponibles dans le calendrier pour une date donnée."
)(_check_availability)

book_appointment = tool(
    description="Prend un rendez-vous pour un client à une date et heure précises."
)(_book_appointment)
