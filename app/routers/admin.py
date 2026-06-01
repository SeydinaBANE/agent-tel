from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.models import CallRecord
from app.db.repository import get_call_by_sid, get_call_stats, get_calls_by_caller, get_recent_calls
from app.middleware.admin_auth import verify_admin_key
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_key)])


def _serialize(record: CallRecord) -> dict:
    return {
        "id": record.id,
        "call_sid": record.call_sid,
        "caller": record.caller,
        "direction": record.direction,
        "duration_secs": record.duration_secs,
        "turns": record.turns,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "transcript": record.transcript,
    }


@router.get("/calls")
@limiter.limit("30/minute")
async def list_calls(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    caller: str | None = Query(default=None),
):
    if caller:
        records = await get_calls_by_caller(caller, limit=limit)
    else:
        records = await get_recent_calls(limit=limit, offset=offset)
    return {"calls": [_serialize(r) for r in records], "count": len(records)}


@router.get("/calls/{call_sid}")
async def get_call(call_sid: str):
    record = await get_call_by_sid(call_sid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Appel '{call_sid}' introuvable.")
    return _serialize(record)


@router.get("/metrics")
@limiter.limit("30/minute")
async def metrics(request: Request):
    """Statistiques agrégées : total appels, durée moyenne, tours moyens."""
    return await get_call_stats()
