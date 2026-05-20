from datetime import datetime

from agno.tools import tool


def _check_availability(date: str) -> str:
    slots = ["09:00", "10:30", "14:00", "15:30", "17:00"]
    return f"Créneaux disponibles le {date} : {', '.join(slots)}"


def _book_appointment(date: str, time: str, client_name: str, reason: str) -> str:
    confirmation_id = f"RDV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return (
        f"Rendez-vous confirmé pour {client_name} le {date} à {time}. "
        f"Motif : {reason}. Référence : {confirmation_id}"
    )


check_availability = tool(
    description="Vérifie les créneaux disponibles dans le calendrier pour une date donnée."
)(_check_availability)

book_appointment = tool(
    description="Prend un rendez-vous pour un client à une date et heure précises."
)(_book_appointment)
