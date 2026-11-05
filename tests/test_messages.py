import json
from types import SimpleNamespace

import main


def test_parse_current_and_legacy_messages():
    current = main.parse_message(
        json.dumps(
            {
                "device_id": "maquina1",
                "distance_cm": 20.123,
                "situation": "ALERTA",
                "source": "arduino",
                "measured_at": "2026-11-05T10:00:00Z",
                "sequence_number": 10,
            }
        ).encode()
    )
    legacy = main.parse_message(
        b'{"distancia_cm": 80, "situacao": "NORMAL", "origem": "arduino", '
        b'"ultima_leitura": "2026-11-05T10:00:00+00:00"}'
    )
    assert current["distance_cm"] == 20.12
    assert current["sequence_number"] == 10
    assert legacy["distance_cm"] == 80
    assert legacy["situation"] == "NORMAL"


def test_parse_rejects_invalid_messages():
    assert main.parse_message(b"not-json") is None
    assert main.parse_message(
        b'{"distance_cm": -1, "situation": "ALERTA", "measured_at": "2026-11-05T10:00:00Z"}'
    ) is None
    assert main.parse_message(
        b'{"distance_cm": 20, "situation": "DESCONHECIDO", "measured_at": "2026-11-05T10:00:00Z"}'
    ) is None


def test_on_message_updates_state_and_persists(monkeypatch):
    recorded = []

    class FakeDatabase:
        def record_reading(self, **reading):
            recorded.append(reading)

    monkeypatch.setattr(main, "database", FakeDatabase())
    monkeypatch.setattr(main, "last_persisted_monotonic", None)
    monkeypatch.setattr(main, "last_persisted_situation", None)
    with main.state_lock:
        main.state["mqtt_connected"] = True

    message = SimpleNamespace(
        payload=b'{"device_id":"maquina1","distance_cm":20,"situation":"ALERTA",'
        b'"source":"arduino","measured_at":"2026-11-05T10:00:00Z","sequence_number":1}'
    )
    main.on_message(None, None, message)

    assert main.current_status()["situation"] == "ALERTA"
    assert main.current_status()["distance_cm"] == 20
    assert len(recorded) == 1
