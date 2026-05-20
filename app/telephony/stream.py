import asyncio
import base64
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from app.agents.tel_agent import create_tel_agent, process_turn
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech

logger = logging.getLogger(__name__)

SILENCE_THRESHOLD = 0.8  # secondes de silence pour déclencher la transcription
MULAW_SAMPLE_RATE = 8000
CHUNK_DURATION = 0.02   # 20ms par paquet Twilio


class CallSession:
    def __init__(self, call_sid: str, caller: str):
        self.call_sid = call_sid
        self.caller = caller
        self.agent = create_tel_agent(caller_number=caller)
        self.audio_buffer = bytearray()
        self.stream_sid: str | None = None
        self.silence_counter = 0
        self.speaking = False

    def add_audio(self, payload: str):
        chunk = base64.b64decode(payload)
        self.audio_buffer.extend(chunk)
        energy = sum(abs(b - 128) for b in chunk) / len(chunk)
        if energy > 5:
            self.speaking = True
            self.silence_counter = 0
        elif self.speaking:
            self.silence_counter += 1

    def should_transcribe(self) -> bool:
        threshold_chunks = int(SILENCE_THRESHOLD / CHUNK_DURATION)
        return self.speaking and self.silence_counter >= threshold_chunks

    def flush_audio(self) -> bytes:
        data = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.speaking = False
        self.silence_counter = 0
        return data


async def handle_media_stream(websocket: WebSocket):
    """Gère un flux Twilio Media Stream en temps réel."""
    await websocket.accept()
    session: CallSession | None = None

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
                logger.info(f"Appel démarré : {call_sid} de {caller}")

                greeting = await process_turn(session.agent, "__START__")
                await _send_audio(websocket, session.stream_sid, greeting)

            elif event == "media" and session:
                session.add_audio(message["media"]["payload"])

                if session.should_transcribe():
                    audio_data = session.flush_audio()
                    if len(audio_data) < 1600:
                        continue

                    text = await transcribe_audio(audio_data)
                    if not text:
                        continue

                    logger.info(f"[{session.call_sid}] Utilisateur: {text}")
                    reply = await process_turn(session.agent, text)
                    logger.info(f"[{session.call_sid}] Agent: {reply}")
                    await _send_audio(websocket, session.stream_sid, reply)

            elif event == "stop":
                logger.info(f"Appel terminé : {session.call_sid if session else 'unknown'}")
                break

    except WebSocketDisconnect:
        logger.info("WebSocket déconnecté")
    except Exception as e:
        logger.error(f"Erreur stream : {e}", exc_info=True)


async def _send_audio(websocket: WebSocket, stream_sid: str, text: str):
    """Synthétise le texte et l'envoie au flux Twilio."""
    mulaw_audio = await synthesize_speech(text)
    payload = base64.b64encode(mulaw_audio).decode("utf-8")
    await websocket.send_json({
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": payload},
    })
