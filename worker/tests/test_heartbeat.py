from pathlib import Path

from worker.heartbeat import heartbeat_age_seconds, write_heartbeat


def test_no_heartbeat_returns_none(tmp_path: Path) -> None:
    assert heartbeat_age_seconds(tmp_path / "missing") is None


def test_heartbeat_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "hb"
    write_heartbeat(path)
    age = heartbeat_age_seconds(path)
    assert age is not None
    assert 0 <= age < 5
