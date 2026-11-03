"""Publica via MQTT as distancias recebidas do Arduino por USB.

Uso real: PORTA_ARDUINO=/dev/ttyACM0 python serial_para_mqtt.py
Teste sem Arduino: SIMULAR=1 python serial_para_mqtt.py
"""
import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import serial

PORTA_ARDUINO = os.getenv("PORTA_ARDUINO", "/dev/ttyACM0")
SIMULAR = os.getenv("SIMULAR", "0") == "1"
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPICO = "seguranca/maquina1/status"


def publicar(cliente, distancia, situacao):
    if not cliente.is_connected():
        print("Aguardando reconexao ao broker MQTT...")
        return
    payload = {
        "distancia_cm": round(distancia, 2),
        "situacao": situacao,
        "origem": "simulacao" if SIMULAR else "arduino",
        "ultima_leitura": datetime.now(timezone.utc).isoformat(),
    }
    resultado = cliente.publish(TOPICO, json.dumps(payload), qos=1, retain=False)
    if resultado.rc == mqtt.MQTT_ERR_SUCCESS:
        print("Enviado MQTT:", payload)
    else:
        print("Falha ao publicar MQTT:", resultado.rc)


def main():
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seguranca-publicador")
    cliente.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cliente.loop_start()
    print(f"Broker: {MQTT_HOST}:{MQTT_PORT} | Topico: {TOPICO}")
    try:
        if SIMULAR:
            while True:
                for distancia in (80, 45, 20, 8, 80):
                    situacao = "ALERTA" if distancia <= 30 else "NORMAL"
                    publicar(cliente, distancia, situacao)
                    time.sleep(2)
        else:
            while True:
                try:
                    with serial.Serial(PORTA_ARDUINO, baudrate=9600, timeout=1) as arduino:
                        print("Arduino conectado em", PORTA_ARDUINO)
                        time.sleep(2)  # Arduino Uno pode reiniciar ao abrir a serial.
                        while True:
                            linha = arduino.readline().decode("utf-8", errors="ignore").strip()
                            if not linha:
                                continue
                            try:
                                d_texto, situacao = linha.split(",", maxsplit=1)
                                distancia = float(d_texto.strip())
                                situacao = situacao.strip().upper()
                                if not (0 <= distancia <= 1000 and situacao in {"NORMAL", "ALERTA"}):
                                    continue
                            except ValueError:
                                print("Linha ignorada:", linha)
                                continue
                            publicar(cliente, distancia, situacao)
                except (serial.SerialException, OSError) as e:
                    print("Erro na serial:", e, "| Tentando novamente em 2 s...")
                    time.sleep(2)
    except KeyboardInterrupt:
        print("Encerrando publicador...")
    finally:
        cliente.disconnect()
        cliente.loop_stop()


if __name__ == "__main__":
    main()
