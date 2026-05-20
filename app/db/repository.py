from datetime import datetime

from sqlalchemy import desc, func, select

from app.db.models import CallRecord
from app.db.session import AsyncSessionLocal


async def save_call(
    call_sid: str,
    caller: str,
    duration_secs: float,
    turns: int,
    transcript: str,
    direction: str = "inbound",
    status: str = "completed",
) -> CallRecord:
    async with AsyncSessionLocal() as session:
        record = CallRecord(
            call_sid=call_sid,
            caller=caller,
            direction=direction,
            duration_secs=duration_secs,
            turns=turns,
            transcript=transcript,
            status=status,
            created_at=datetime.utcnow(),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def get_call_by_sid(call_sid: str) -> CallRecord | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CallRecord).where(CallRecord.call_sid == call_sid))
        return result.scalar_one_or_none()


async def get_recent_calls(limit: int = 20, offset: int = 0) -> list[CallRecord]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CallRecord).order_by(desc(CallRecord.created_at)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())


async def get_calls_by_caller(caller: str, limit: int = 10) -> list[CallRecord]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CallRecord)
            .where(CallRecord.caller == caller)
            .order_by(desc(CallRecord.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_call_stats() -> dict:
    """Statistiques agrégées : total, durée moyenne, tours moyens."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                func.count(CallRecord.id).label("total_calls"),
                func.avg(CallRecord.duration_secs).label("avg_duration"),
                func.avg(CallRecord.turns).label("avg_turns"),
            )
        )
        row = result.one()
        return {
            "total_calls": row.total_calls or 0,
            "avg_duration_secs": round(row.avg_duration or 0.0, 1),
            "avg_turns": round(row.avg_turns or 0.0, 1),
        }
