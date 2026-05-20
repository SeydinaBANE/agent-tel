import asyncio
import base64
import json
import re
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.agents.tel_agent import create_tel_agent, process_turn
from app.config import settings
from app.db.repository import save_call
from app.logger import get_logger
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech
from app.services.webhook import notify_call_ended

logger = get_logger(__name__)

SILENCE_THRESHOLD = 0.8  # secondes
CHUNK_DURATION = 0.02  # 20ms par paquet Twilio
MIN_AUDIO_BYTES = 1600  # ~100ms — en-dessous on ignore

_E164 = re.compile(r"^\+[1-9]\d{1,14}$")


class CallSession:
    def __init__(self, call_sid: str, caller: str):
        self.call_sid = call_sid
        self.caller = caller
        self.agent = create_tel_agent(caller_number=caller)
        self.audio_buffer = bytearray()
        self.stream_sid: str | None = None
        self.silence_counter = 0
        self.speaking = False
        self.agent_speaking = False
        self.agent_task: asyncio.Task | None = None
        self.transcript: list[str] = []
        self.start_time = time.monotonic()
        self.last_activity = time.monotonic()

    def add_audio(self, payload: str) -> None:
        chunk = base64.b64decode(payload)
        self.audio_buffer.extend(chunk)
        self.last_activity = time.monotonic()
        energy = sum(abs(b - 128) for b in chunk) / len(chunk)
        if energy > 5:
            self.speaking = True
            self.silence_counter = 0
        elif self.speaking:
            self.silence_counter += 1

    def should_transcribe(self) -> bool:
        return self.speaking and self.silence_counter >= int(SILENCE_THRESHOLD / CHUNK_DURATION)

    def flush_audio(self) -> bytes:
        data = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.speaking = False
        self.silence_counter = 0
        return data

    @property
    def duration(self) -> float:
        return round(time.monotonic() - self.start_time, 1)

    @property
    def idle_secs(self) -> float:
        return round(time.monotonic() - self.last_activity, 1)


# ---------------------------------------------------------------------------
# WebSocket handler principal
# ---------------------------------------------------------------------------


async def handle_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    session: CallSession | None = None
    timeout_task: asyncio.Task | None = None

    try:
        async for raw_message in websocket.iter_text():
            message = json.loads(raw_message)
            event = message.get("event")

            if event == "start":
                start = message["start"]
                call_sid = start["callSid"]
                caller = start.get("customParameters", {}).get("caller", "inconnu")
                session = CallSession(call_sid=call_sid, caller=caller)
                session.stream_sid = start["streamSid"]
                logger.info("call_started", call_sid=call_sid, caller=caller)

                timeout_task = asyncio.create_task(_timeout_watchdog(websocket, session))
                # Salutation initiale en tâche de fond (cancellable si barge-in)
                session.agent_task = asyncio.create_task(
                    _send_audio(websocket, session, "__START__")
                )

            elif event == "media" and session:
                session.add_audio(message["media"]["payload"])

                # --- Barge-in : l'utilisateur parle pendant que l'agent parle ---
                if session.agent_speaking and session.speaking:
                    _cancel_agent(session)
                    await _send_clear(websocket, session.stream_sid)
                    logger.info("barge_in", call_sid=session.call_sid)

                # Nouveau tour uniquement quand l'agent a fini
                if _agent_free(session) and session.should_transcribe():
                    audio_data = session.flush_audio()
                    if len(audio_data) < MIN_AUDIO_BYTES:
                        continue

                    text = await transcribe_audio(audio_data)
                    if not text:
                        continue

                    session.transcript.append(f"Utilisateur: {text}")
                    logger.info("user_speech", call_sid=session.call_sid, text=text)

                    reply = await process_turn(session.agent, text)
                    session.transcript.append(f"Agent: {reply}")
                    logger.info("agent_reply", call_sid=session.call_sid, text=reply)

                    session.agent_task = asyncio.create_task(_send_audio(websocket, session, reply))

            elif event == "stop":
                if session:
                    await _handle_call_end(session)
                break

    except WebSocketDisconnect:
        if session:
            logger.info("websocket_disconnect", call_sid=session.call_sid)
            await _handle_call_end(session)
    except Exception as exc:
        logger.error(
            "stream_error",
            error=str(exc),
            call_sid=session.call_sid if session else None,
            exc_info=True,
        )
    finally:
        if timeout_task:
            timeout_task.cancel()
        if session:
            _cancel_agent(session)


# ---------------------------------------------------------------------------
# Envoi audio (tâche annulable)
# ---------------------------------------------------------------------------


async def _send_audio(websocket: WebSocket, session: CallSession, text: str) -> None:
    session.agent_speaking = True
    try:
        mulaw = await synthesize_speech(text)
        payload = base64.b64encode(mulaw).decode()
        await websocket.send_json(
            {
                "event": "media",
                "streamSid": session.stream_sid,
                "media": {"payload": payload},
            }
        )
    except asyncio.CancelledError:
        pass  # barge-in — silencieux
    except Exception as exc:
        logger.error("audio_send_error", call_sid=session.call_sid, error=str(exc))
    finally:
        session.agent_speaking = False


async def _send_clear(websocket: WebSocket, stream_sid: str | None) -> None:
    if stream_sid:
        await websocket.send_json({"event": "clear", "streamSid": stream_sid})


# ---------------------------------------------------------------------------
# Timeout watchdog
# ---------------------------------------------------------------------------


async def _timeout_watchdog(websocket: WebSocket, session: CallSession) -> None:
    while True:
        await asyncio.sleep(5)
        if session.idle_secs >= settings.call_timeout_secs:
            logger.info(
                "call_timeout",
                call_sid=session.call_sid,
                idle_secs=session.idle_secs,
            )
            _cancel_agent(session)
            await _send_clear(websocket, session.stream_sid)
            farewell = await process_turn(session.agent, "__TIMEOUT__")
            await _send_audio(websocket, session, farewell)
            await _handle_call_end(session)
            break


# ---------------------------------------------------------------------------
# Fin d'appel — résumé automatique + logging
# ---------------------------------------------------------------------------


async def _handle_call_end(session: CallSession) -> None:
    turns = len(session.transcript) // 2
    logger.info(
        "call_ended",
        call_sid=session.call_sid,
        caller=session.caller,
        duration_secs=session.duration,
        turns=turns,
    )

    # Résumé LLM → CRM
    if session.transcript:
        summary = (
            f"Durée: {session.duration}s. "
            f"{turns} échange(s). "
            f"Transcript: {' | '.join(session.transcript[:6])}"
        )
        try:
            await process_turn(session.agent, f"__END__ {summary}")
        except Exception as exc:
            logger.error("end_summary_error", call_sid=session.call_sid, error=str(exc))

    # Persistance DB
    try:
        await save_call(
            call_sid=session.call_sid,
            caller=session.caller,
            duration_secs=session.duration,
            turns=turns,
            transcript="\n".join(session.transcript),
        )
    except Exception as exc:
        logger.error("db_save_error", call_sid=session.call_sid, error=str(exc))

    # Notification Slack / Teams
    try:
        await notify_call_ended(
            call_sid=session.call_sid,
            caller=session.caller,
            duration=session.duration,
            transcript=session.transcript,
        )
    except Exception as exc:
        logger.error("webhook_notify_error", call_sid=session.call_sid, error=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_free(session: CallSession) -> bool:
    return session.agent_task is None or session.agent_task.done()


def _cancel_agent(session: CallSession) -> None:
    if session.agent_task and not session.agent_task.done():
        session.agent_task.cancel()
    session.agent_speaking = False
