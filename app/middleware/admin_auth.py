from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_header_scheme = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def verify_admin_key(api_key: str | None = Security(_header_scheme)) -> None:  # noqa: B008
    """Vérifie X-Admin-Key sur les routes /admin/*.
    Si ADMIN_API_KEY est vide → bypass (dev local). Sinon → 403 si clé incorrecte.
    """
    if not settings.admin_api_key:
        return
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Clé admin invalide.")
