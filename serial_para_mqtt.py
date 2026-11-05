"""Publica via MQTT as distancias recebidas do Arduino por USB."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import serial


SERIAL_PORT = os.getenv("PORTA_ARDUINO", "/dev/ttyACM0")
SIMULATE = os.getenv("SIMULAR", "0") == "1"
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "maquina1")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", f"seguranca/{DEVICE_ID}/status")
AVAILABILITY_TOPIC = f"seguranca/{DEVICE_ID}/availability"

connected_event = threading.Event()
sequence_number = 0
last_logged_situation: str | None = None


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        connected_event.clear()
        print("Conexao MQTT recusada:", reason_code)
        return
    connected_event.set()
    client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
    print("Conectado ao broker MQTT")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    connected_event.clear()
    print("MQTT desconectado; aguardando reconexao...")


def parse_serial_line(line: str) -> tuple[float, str] | None:
    try:
        distance_text, situation = line.split(",", maxsplit=1)
        distance = float(distance_text.strip())
        situation = situation.strip().upper()
    except ValueError:
        return None
    if not (0 <= distance <= 1000 and situation in {"NORMAL", "ALERTA"}):
        return None
    return distance, situation


def publish(client: mqtt.Client, distance: float, situation: str) -> bool:
    global sequence_number, last_logged_situation
    if not connected_event.is_set() or not client.is_connected():
        print("Aguardando conexao ao broker MQTT...")
        return False

    sequence_number += 1
    measured_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "device_id": DEVICE_ID,
        "distance_cm": round(distance, 2),
        "situation": situation,
        "source": "simulation" if SIMULATE else "arduino",
        "measured_at": measured_at,
        "sequence_number": sequence_number,
        # Campos antigos mantidos para clientes da primeira versao.
        "distancia_cm": round(distance, 2),
        "situacao": situation,
        "origem": "simulacao" if SIMULATE else "arduino",
        "ultima_leitura": measured_at,
    }
    result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1, retain=False)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        if situation != last_logged_situation or sequence_number % 10 == 0:
            print("Enviado MQTT:", payload)
            last_logged_situation = situation
        return True
    print("Falha ao publicar MQTT:", result.rc)
    return False


def create_mqtt_client() -> mqtt.Client:
    client_id = os.getenv("MQTT_CLIENT_ID", f"seguranca-publisher-{socket.gethostname()}")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def run_simulation(client: mqtt.Client) -> None:
    while True:
        for distance in (80, 45, 20, 8, 80):
            situation = "ALERTA" if distance <= 30 else "NORMAL"
            publish(client, distance, situation)
            time.sleep(2)


def run_serial(client: mqtt.Client) -> None:
    while True:
        try:
            with serial.Serial(SERIAL_PORT, baudrate=9600, timeout=1) as arduino:
                print("Arduino conectado em", SERIAL_PORT)
                time.sleep(2)
                while True:
                    line = arduino.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    reading = parse_serial_line(line)
                    if reading is None:
                        print("Linha ignorada:", line)
                        continue
                    publish(client, *reading)
        except (serial.SerialException, OSError) as error:
            print("Erro na serial:", error, "| Tentando novamente em 2 s...")
            time.sleep(2)


def main() -> None:
    client = create_mqtt_client()
    print(f"Broker: {MQTT_HOST}:{MQTT_PORT} | Topico: {MQTT_TOPIC}")
    try:
        run_simulation(client) if SIMULATE else run_serial(client)
    except KeyboardInterrupt:
        print("Encerrando publicador...")
    finally:
        if client.is_connected():
            client.publish(AVAILABILITY_TOPIC, "offline", qos=1, retain=True).wait_for_publish()
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
