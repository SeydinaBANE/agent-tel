import asyncio
import base64
import json
import re
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.agents.team import create_team_agent
from app.agents.tel_agent import create_tel_agent, process_turn, process_turn_streaming
from app.config import settings
from app.db.repository import get_calls_by_caller, save_call
from app.logger import get_logger
from app.services.escalation import ESCALATION_SENTINEL, transfer_call
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech, synthesize_streaming
from app.services.webhook import notify_call_ended
from app.telephony.ws_auth import verify_ws_token

logger = get_logger(__name__)

SILENCE_THRESHOLD = 0.8  # secondes
CHUNK_DURATION = 0.02  # 20ms par paquet Twilio
MIN_AUDIO_BYTES = 1600  # ~100ms — en-dessous on ignore

_E164 = re.compile(r"^\+[1-9]\d{1,14}$")


class CallSession:
    def __init__(self, call_sid: str, caller: str):
        self.call_sid = call_sid
        self.caller = caller
        factory = create_team_agent if settings.multi_agent_mode else create_tel_agent
        self.agent = factory(caller_number=caller)
        self.audio_buffer = bytearray()
        self.stream_sid: str | None = None
        self.silence_counter = 0
        self.speaking = False
        self.agent_speaking = False
        self.agent_task: asyncio.Task | None = None
        self.transcript: list[str] = []
        self.start_time = time.monotonic()
        self.last_activity = time.monotonic()
        self.escalation_requested = False

    async def load_memory(self) -> None:
        """Recrée l'agent avec l'historique des appels précédents injecté."""
        if not _E164.match(self.caller):
            return
        try:
            records = await get_calls_by_caller(self.caller, limit=3)
            if records:
                factory = create_team_agent if settings.multi_agent_mode else create_tel_agent
                self.agent = factory(caller_number=self.caller, memory_records=records)
        except Exception as exc:
            logger.warning("memory_load_error", call_sid=self.call_sid, error=str(exc))

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


# Active WebSocket sessions (pour arrêt gracieux)
_active_sessions: set[CallSession] = set()


async def cancel_all_sessions() -> None:
    """Annule toutes les sessions actives (appelé lors de l'arrêt gracieux)."""
    for session in list(_active_sessions):
        _cancel_agent(session)
    _active_sessions.clear()


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

                # Validation du token d'authentification WebSocket
                token = websocket.query_params.get("token", "")
                if not verify_ws_token(token, caller):
                    logger.warning("ws_auth_failed", call_sid=call_sid, caller=caller)
                    await websocket.close(code=4001)
                    return

                session = CallSession(call_sid=call_sid, caller=caller)
                session.stream_sid = start["streamSid"]
                _active_sessions.add(session)

                # Charge l'historique du client avant le premier tour
                await session.load_memory()

                logger.info("call_started", call_sid=call_sid, caller=caller)

                timeout_task = asyncio.create_task(_timeout_watchdog(websocket, session))
                session.agent_task = asyncio.create_task(
                    _send_audio(websocket, session, "__START__")
                )

            elif event == "media" and session:
                session.add_audio(message["media"]["payload"])

                # --- Barge-in ---
                if session.agent_speaking and session.speaking:
                    _cancel_agent(session)
                    await _send_clear(websocket, session.stream_sid)
                    logger.info("barge_in", call_sid=session.call_sid)

                if _agent_free(session) and session.should_transcribe():
                    audio_data = session.flush_audio()
                    if len(audio_data) < MIN_AUDIO_BYTES:
                        continue

                    t0 = time.monotonic()
                    text = await transcribe_audio(audio_data)
                    stt_ms = int((time.monotonic() - t0) * 1000)

                    if not text:
                        continue

                    session.transcript.append(f"Utilisateur: {text}")
                    logger.info("user_speech", call_sid=session.call_sid, text=text)

                    if settings.llm_streaming:
                        session.agent_task = asyncio.create_task(
                            _handle_streaming_turn(websocket, session, text, stt_ms)
                        )
                    else:
                        t1 = time.monotonic()
                        reply = await process_turn(session.agent, text)
                        llm_ms = int((time.monotonic() - t1) * 1000)

                        logger.info(
                            "turn_latency",
                            call_sid=session.call_sid,
                            stt_ms=stt_ms,
                            llm_ms=llm_ms,
                        )

                        if ESCALATION_SENTINEL in reply:
                            reason = reply.split(":", 1)[-1].strip()
                            session.escalation_requested = True
                            farewell = "Je vous transfère vers un conseiller. Un instant."
                            session.transcript.append(f"Agent: {farewell}")
                            session.agent_task = asyncio.create_task(
                                _send_audio(websocket, session, farewell)
                            )
                            await session.agent_task
                            await transfer_call(session.call_sid, reason=reason)
                            await _handle_call_end(session)
                            break

                        session.transcript.append(f"Agent: {reply}")
                        logger.info("agent_reply", call_sid=session.call_sid, text=reply)
                        session.agent_task = asyncio.create_task(
                            _send_audio(websocket, session, reply)
                        )

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
            _active_sessions.discard(session)


# ---------------------------------------------------------------------------
# Envoi audio (tâche annulable)
# ---------------------------------------------------------------------------


async def _send_audio(websocket: WebSocket, session: CallSession, text: str) -> None:
    """Envoie l'audio — streaming phrase par phrase si TTS_SENTENCE_STREAMING=true."""
    session.agent_speaking = True
    t0 = time.monotonic()
    chunks_sent = 0
    try:
        if settings.tts_sentence_streaming:
            async for mulaw in synthesize_streaming(text):
                payload = base64.b64encode(mulaw).decode()
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": session.stream_sid,
                        "media": {"payload": payload},
                    }
                )
                chunks_sent += 1
        else:
            mulaw = await synthesize_speech(text)
            payload = base64.b64encode(mulaw).decode()
            await websocket.send_json(
                {
                    "event": "media",
                    "streamSid": session.stream_sid,
                    "media": {"payload": payload},
                }
            )
            chunks_sent = 1

        tts_ms = int((time.monotonic() - t0) * 1000)
        logger.info("tts_latency", call_sid=session.call_sid, tts_ms=tts_ms, chunks=chunks_sent)

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
        escalated=session.escalation_requested,
    )

    # Résumé LLM → CRM
    summary_text = ""
    if session.transcript and not session.escalation_requested:
        summary_text = (
            f"Durée: {session.duration}s. "
            f"{turns} échange(s). "
            f"Transcript: {' | '.join(session.transcript[:6])}"
        )
        try:
            await process_turn(session.agent, f"__END__ {summary_text}")
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
            status="escalated" if session.escalation_requested else "completed",
        )
    except Exception as exc:
        logger.error("db_save_error", call_sid=session.call_sid, error=str(exc))

    # SMS résumé post-appel
    if settings.send_summary_sms and summary_text and _E164.match(session.caller):
        try:
            from twilio.rest import Client

            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            body = f"Résumé de votre appel : {summary_text[:140]}"
            await asyncio.to_thread(
                client.messages.create,
                body=body,
                from_=settings.twilio_phone_number,
                to=session.caller,
            )
            logger.info("summary_sms_sent", call_sid=session.call_sid, caller=session.caller)
        except Exception as exc:
            logger.error("summary_sms_error", call_sid=session.call_sid, error=str(exc))

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
# Pipeline LLM streaming → TTS (latence first-audio réduite)
# ---------------------------------------------------------------------------


async def _handle_streaming_turn(
    websocket: WebSocket, session: CallSession, user_text: str, stt_ms: int
) -> None:
    """Pipeline streaming : génère les phrases au fil du LLM et TTS chacune dès qu'elle est prête."""
    session.agent_speaking = True
    reply_parts: list[str] = []
    t0 = time.monotonic()
    first_sentence = True

    try:
        async for kind, content in process_turn_streaming(session.agent, user_text):
            if kind == "escalade":
                session.escalation_requested = True
                farewell = "Je vous transfère vers un conseiller. Un instant."
                mulaw = await synthesize_speech(farewell)
                payload = base64.b64encode(mulaw).decode()
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": session.stream_sid,
                        "media": {"payload": payload},
                    }
                )
                await transfer_call(session.call_sid, reason=content)
                break

            if kind == "text" and content:
                if first_sentence:
                    llm_first_ms = int((time.monotonic() - t0) * 1000)
                    logger.info(
                        "turn_latency_streaming",
                        call_sid=session.call_sid,
                        stt_ms=stt_ms,
                        llm_first_sentence_ms=llm_first_ms,
                    )
                    first_sentence = False

                reply_parts.append(content)
                t_tts = time.monotonic()
                mulaw = await synthesize_speech(content)
                tts_ms = int((time.monotonic() - t_tts) * 1000)
                logger.info("tts_latency", call_sid=session.call_sid, tts_ms=tts_ms)

                payload = base64.b64encode(mulaw).decode()
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": session.stream_sid,
                        "media": {"payload": payload},
                    }
                )

        full_reply = " ".join(reply_parts)
        if full_reply:
            session.transcript.append(f"Agent: {full_reply}")
            logger.info("agent_reply", call_sid=session.call_sid, text=full_reply[:120])

    except asyncio.CancelledError:
        pass  # barge-in
    except Exception as exc:
        logger.error("streaming_turn_error", call_sid=session.call_sid, error=str(exc))
    finally:
        session.agent_speaking = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_free(session: CallSession) -> bool:
    return session.agent_task is None or session.agent_task.done()


def _cancel_agent(session: CallSession) -> None:
    if session.agent_task and not session.agent_task.done():
        session.agent_task.cancel()
    session.agent_speaking = False
