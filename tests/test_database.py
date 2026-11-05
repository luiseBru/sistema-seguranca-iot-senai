from database import Database


def test_database_records_readings_and_alert_lifecycle(tmp_path):
    database = Database(tmp_path / "security.db")
    database.record_reading(
        device_id="maquina1",
        measured_at="2026-11-05T10:00:00+00:00",
        distance_cm=80,
        situation="NORMAL",
        source="test",
        sequence_number=1,
    )
    database.record_reading(
        device_id="maquina1",
        measured_at="2026-11-05T10:00:01+00:00",
        distance_cm=20,
        situation="ALERTA",
        source="test",
        sequence_number=2,
    )
    database.record_reading(
        device_id="maquina1",
        measured_at="2026-11-05T10:00:02+00:00",
        distance_cm=8,
        situation="ALERTA",
        source="test",
        sequence_number=3,
    )
    database.record_reading(
        device_id="maquina1",
        measured_at="2026-11-05T10:00:03+00:00",
        distance_cm=50,
        situation="NORMAL",
        source="test",
        sequence_number=4,
    )

    readings = database.get_readings()
    alerts = database.get_alerts()
    assert len(readings) == 4
    assert [reading["sequence_number"] for reading in readings] == [1, 2, 3, 4]
    assert len(alerts) == 1
    assert alerts[0]["min_distance_cm"] == 8
    assert alerts[0]["ended_at"] == "2026-11-05T10:00:03+00:00"

    acknowledged = database.acknowledge_alert(alerts[0]["id"], "Bruna")
    assert acknowledged["acknowledged_by"] == "Bruna"
    assert acknowledged["acknowledged_at"] is not None
    database.close()


def test_database_limits_queries(tmp_path):
    database = Database(tmp_path / "security.db")
    for sequence in range(5):
        database.record_reading(
            device_id="maquina1",
            measured_at=f"2026-11-05T10:00:0{sequence}+00:00",
            distance_cm=80,
            situation="NORMAL",
            source="test",
            sequence_number=sequence,
        )
    assert len(database.get_readings(limit=2)) == 2
    assert database.get_readings(limit=2)[0]["sequence_number"] == 3
    assert database.acknowledge_alert(999, "operador") is None
