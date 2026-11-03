"""FastAPI inscrita no topico MQTT do sistema de seguranca didatico.

Os dados chegam por MQTT, NAO pela porta serial diretamente.
"""
import json
import os
import threading
import time
from contextlib import asynccontextmanager

import paho.mqtt.client as mqtt
from fastapi import FastAPI

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPICO = "seguranca/maquina1/status"

estado = {
    "distancia_cm": None,
    "situacao": "AGUARDANDO",
    "conectado": False,
    "origem": "mqtt",
    "ultima_leitura": None,
    "mqtt_conectado": False,
}
_trava = threading.Lock()
_ultima_monotonica = None


def on_connect(client, userdata, flags, reason_code, properties):
    ok = not reason_code.is_failure
    with _trava:
        estado["mqtt_conectado"] = ok
    if ok:
        client.subscribe(TOPICO, qos=1)
        print("FastAPI inscrita em", TOPICO)
    else:
        print("Conexao MQTT recusada:", reason_code)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    with _trava:
        estado["mqtt_conectado"] = False


def on_message(client, userdata, msg):
    global _ultima_monotonica
    try:
        dados = json.loads(msg.payload.decode("utf-8"))
        distancia = float(dados["distancia_cm"])
        situacao = dados["situacao"]
        if not (0 <= distancia <= 1000 and situacao in ("NORMAL", "ALERTA")):
            return
        ultima = dados["ultima_leitura"]
    except (KeyError, ValueError, TypeError, UnicodeDecodeError):
        return
    with _trava:
        estado.update(
            distancia_cm=round(distancia, 2),
            situacao=situacao,
            conectado=True,
            origem=dados.get("origem", "mqtt"),
            ultima_leitura=ultima,
        )
        _ultima_monotonica = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seguranca-fastapi")
    cliente.on_connect = on_connect
    cliente.on_disconnect = on_disconnect
    cliente.on_message = on_message
    cliente.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cliente.loop_start()
    try:
        yield
    finally:
        cliente.disconnect()
        cliente.loop_stop()


app = FastAPI(title="Seguranca de Maquinas - MQTT", lifespan=lifespan)


@app.get("/")
def inicio():
    return {"mensagem": "API MQTT funcionando. Consulte /status ou /docs."}


@app.get("/status")
def status():
    with _trava:
        atual = estado.copy()
        ultima = _ultima_monotonica
    if not atual["mqtt_conectado"] or ultima is None or time.monotonic() - ultima > 5:
        atual.update(conectado=False, situacao="SEM_SINAL", distancia_cm=None)
    return atual
