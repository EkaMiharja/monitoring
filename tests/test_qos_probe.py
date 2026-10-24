import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "qos_probe", ROOT / "deploy" / "qos_probe.py"
)
qos_probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qos_probe)


def run_probe(monkeypatch, ping_loss, udp_loss):
    captured = {}
    monkeypatch.setattr(qos_probe.shutil, "which", lambda _: "/usr/local/bin/iperf3")
    monkeypatch.setattr(qos_probe, "measure_delay", lambda: (1.2, ping_loss))
    monkeypatch.setattr(qos_probe, "measure_throughput", lambda: 100.0)
    monkeypatch.setattr(qos_probe, "measure_loss", lambda: (0.5, udp_loss))
    monkeypatch.setattr(qos_probe, "write_result", captured.update)
    monkeypatch.setattr(qos_probe, "append_history", lambda point: 1)
    monkeypatch.setattr(qos_probe, "write_log", lambda message: None)
    assert qos_probe.main() == 0
    return captured


def test_packet_loss_prefers_ping(monkeypatch):
    payload = run_probe(monkeypatch, ping_loss=1.5, udp_loss=0.0)
    assert payload["packet_loss_percent"] == 1.5
    assert payload["packet_loss_source"] == "ping"
    assert payload["ping_packet_loss_percent"] == 1.5
    assert payload["udp_packet_loss_percent"] == 0.0


def test_packet_loss_falls_back_to_udp(monkeypatch):
    payload = run_probe(monkeypatch, ping_loss=None, udp_loss=2.5)
    assert payload["packet_loss_percent"] == 2.5
    assert payload["packet_loss_source"] == "udp"


def test_packet_loss_unavailable(monkeypatch):
    payload = run_probe(monkeypatch, ping_loss=None, udp_loss=None)
    assert payload["packet_loss_percent"] is None
    assert payload["packet_loss_source"] is None
