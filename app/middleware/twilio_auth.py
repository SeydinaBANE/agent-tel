"""Validation de la signature Twilio sur les webhooks entrants.

Twilio signe chaque requête avec HMAC-SHA1 du token d'auth.
Si TWILIO_AUTH_TOKEN est vide (tests locaux), la validation est bypassée.
"""

from fastapi import Depends, HTTPException, Request
from twilio.request_validator import RequestValidator

from app.config import settings


def _get_validator() -> RequestValidator:
    return RequestValidator(settings.twilio_auth_token)


async def verify_twilio_signature(
    request: Request,
    validator: RequestValidator = Depends(_get_validator),  # noqa: B008
) -> None:
    if not settings.twilio_auth_token:
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    # Les webhooks Twilio sont toujours POST avec form-data
    form = await request.form()
    params = dict(form)

    if not validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Signature Twilio invalide.")
