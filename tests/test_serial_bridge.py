import json

import serial_para_mqtt as bridge


def test_parse_serial_line():
    assert bridge.parse_serial_line("20.00,ALERTA") == (20.0, "ALERTA")
    assert bridge.parse_serial_line(" 80 , normal ") == (80.0, "NORMAL")
    assert bridge.parse_serial_line("texto") is None
    assert bridge.parse_serial_line("-1,ALERTA") is None
    assert bridge.parse_serial_line("20,ERRO") is None


def test_publish_builds_compatible_payload(monkeypatch):
    published = []

    class Result:
        rc = 0

    class FakeClient:
        def is_connected(self):
            return True

        def publish(self, topic, payload, qos, retain):
            published.append((topic, json.loads(payload), qos, retain))
            return Result()

    bridge.connected_event.set()
    monkeypatch.setattr(bridge, "sequence_number", 0)
    assert bridge.publish(FakeClient(), 12.345, "ALERTA") is True

    topic, payload, qos, retain = published[0]
    assert topic == "seguranca/maquina1/status"
    assert payload["distance_cm"] == 12.35
    assert payload["distancia_cm"] == 12.35
    assert payload["sequence_number"] == 1
    assert qos == 1
    assert retain is False
