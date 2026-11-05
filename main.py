"""API, dashboard e assinante MQTT do sistema de seguranca didatico."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import Database


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "maquina1")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", f"seguranca/{DEVICE_ID}/status")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "seguranca.db"))
STALE_AFTER_SECONDS = float(os.getenv("STALE_AFTER_SECONDS", "5"))
PERSIST_INTERVAL_SECONDS = float(os.getenv("PERSIST_INTERVAL_SECONDS", "1"))

database = Database(DATABASE_PATH)
state = {
    "device_id": DEVICE_ID,
    "distance_cm": None,
    "situation": "AGUARDANDO",
    "connected": False,
    "source": "mqtt",
    "last_reading": None,
    "mqtt_connected": False,
    "database_ok": True,
}
state_lock = threading.Lock()
last_message_monotonic: float | None = None
last_persisted_monotonic: float | None = None
last_persisted_situation: str | None = None


class AcknowledgeRequest(BaseModel):
    operator: str = Field(default="operador", min_length=1, max_length=60)


def parse_message(payload: bytes) -> dict | None:
    try:
        data = json.loads(payload.decode("utf-8"))
        distance = float(data["distance_cm"] if "distance_cm" in data else data["distancia_cm"])
        situation = str(data.get("situation", data.get("situacao", ""))).strip().upper()
        device_id = str(data.get("device_id", DEVICE_ID)).strip()
        source = str(data.get("source", data.get("origem", "mqtt"))).strip()[:40] or "mqtt"
        measured_at = str(data.get("measured_at", data.get("ultima_leitura", ""))).strip()
        sequence = data.get("sequence_number")

        if not (0 <= distance <= 1000 and situation in {"NORMAL", "ALERTA"}):
            return None
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,50}", device_id):
            return None
        parsed_time = datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        measured_at = parsed_time.astimezone(timezone.utc).isoformat()
        if sequence is not None:
            sequence = int(sequence)
    except (KeyError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return {
        "device_id": device_id,
        "distance_cm": round(distance, 2),
        "situation": situation,
        "source": source,
        "measured_at": measured_at,
        "sequence_number": sequence,
    }


def on_connect(client, userdata, flags, reason_code, properties):
    connected = not reason_code.is_failure
    with state_lock:
        state["mqtt_connected"] = connected
    if connected:
        client.subscribe(MQTT_TOPIC, qos=1)
        print("FastAPI inscrita em", MQTT_TOPIC)
    else:
        print("Conexao MQTT recusada:", reason_code)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    with state_lock:
        state["mqtt_connected"] = False


def on_message(client, userdata, msg):
    global last_message_monotonic, last_persisted_monotonic, last_persisted_situation

    reading = parse_message(msg.payload)
    if reading is None:
        return

    now_monotonic = time.monotonic()
    with state_lock:
        state.update(
            device_id=reading["device_id"],
            distance_cm=reading["distance_cm"],
            situation=reading["situation"],
            connected=True,
            source=reading["source"],
            last_reading=reading["measured_at"],
        )
        last_message_monotonic = now_monotonic

    should_persist = (
        last_persisted_monotonic is None
        or now_monotonic - last_persisted_monotonic >= PERSIST_INTERVAL_SECONDS
        or reading["situation"] != last_persisted_situation
    )
    if not should_persist:
        return

    try:
        database.record_reading(**reading)
        with state_lock:
            state["database_ok"] = True
        last_persisted_monotonic = now_monotonic
        last_persisted_situation = reading["situation"]
    except Exception as error:  # O MQTT deve continuar mesmo se o disco falhar.
        with state_lock:
            state["database_ok"] = False
        print("Falha ao gravar no banco:", error)


def current_status() -> dict:
    with state_lock:
        current = state.copy()
        last_seen = last_message_monotonic
    if (
        not current["mqtt_connected"]
        or last_seen is None
        or time.monotonic() - last_seen > STALE_AFTER_SECONDS
    ):
        current.update(connected=False, situation="SEM_SINAL", distance_cm=None)
    return current


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.connect()
    client_id = os.getenv("MQTT_CLIENT_ID", f"seguranca-api-{socket.gethostname()}")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    app.state.mqtt_client = client
    try:
        yield
    finally:
        client.disconnect()
        client.loop_stop()
        database.close()


app = FastAPI(title="Seguranca de Maquinas - MQTT", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/status")
@app.get("/api/status")
def get_status():
    return current_status()


@app.get("/api/readings")
def get_readings(
    limit: int = Query(default=120, ge=1, le=1000),
    device_id: str | None = None,
):
    return database.get_readings(limit=limit, device_id=device_id)


@app.get("/api/alerts")
def get_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    device_id: str | None = None,
):
    return database.get_alerts(limit=limit, device_id=device_id)


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, request: AcknowledgeRequest):
    operator = request.operator.strip()
    if not operator:
        raise HTTPException(status_code=422, detail="Informe o nome do operador")
    alert = database.acknowledge_alert(alert_id, operator)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta nao encontrado")
    return alert


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    current = current_status()
    ready = current["mqtt_connected"] and current["database_ok"]
    if not ready:
        raise HTTPException(status_code=503, detail=current)
    return {"status": "ready", **current}


@app.websocket("/ws/status")
async def status_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(current_status())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
