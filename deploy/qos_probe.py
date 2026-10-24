#!/usr/bin/env python3
"""Probe QoS in-VM: mengukur link yang sama dengan beban pipeline ML.

Probe ini berjalan di dalam VM (bukan dari laptop) sehingga pengukurannya
menggambarkan beban pada jaringan yang juga dipakai traffic SSH brute force,
yaitu interface host-only VirtualBox.

Hasil probe ditulis ke ``qos/last.json`` (di luar folder ``capture/``) supaya
tidak pernah disentuh pipeline ML. Probe memakai port iperf3 terpisah (5201
TCP untuk throughput, 5202/5203 UDP untuk jitter) yang tidak lolos filter
``tcp port 22`` pada ``ids-tcpdump``, jadi data ML tidak terkontaminasi.
Packet loss diambil dari ICMP ping; loss UDP hanya dipakai sebagai fallback
bila ping tidak tersedia.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "qos"
OUTPUT_PATH = OUTPUT_DIR / "last.json"
HISTORY_PATH = OUTPUT_DIR / "history.json"
# Berapa banyak titik yang disimpan (480 titik @ 10 detik = 80 menit).
HISTORY_MAX_POINTS = int(os.environ.get("QOS_HISTORY_MAX_POINTS", "480"))

IPERF3_BINARY = os.environ.get("QOS_PROBE_IPERF3", "/usr/local/bin/iperf3")
PING_BINARY = os.environ.get("QOS_PROBE_PING", "/bin/ping")
TARGET_HOST = os.environ.get("QOS_PROBE_TARGET", "192.168.56.102")
TCP_PORT = int(os.environ.get("QOS_PROBE_TCP_PORT", "5201"))
# Port UDP di peer. Dua arah memakai port berbeda supaya probe tidak pernah
# mengukur ke server yang sedang dipakai probe dari arah sebaliknya.
UDP_PORT = int(os.environ.get("QOS_PROBE_UDP_PORT", "5202"))
TCP_DURATION = int(os.environ.get("QOS_PROBE_TCP_DURATION", "3"))
UDP_DURATION = int(os.environ.get("QOS_PROBE_UDP_DURATION", "2"))
UDP_BANDWIDTH = os.environ.get("QOS_PROBE_UDP_BANDWIDTH", "1M")
PING_COUNT = int(os.environ.get("QOS_PROBE_PING_COUNT", "10"))
PING_INTERVAL = os.environ.get("QOS_PROBE_PING_INTERVAL", "0.2")
PING_TIMEOUT = int(os.environ.get("QOS_PROBE_PING_TIMEOUT", "2"))
# Batas waktu per subprocess supaya probe tidak pernah menggantung.
SUBPROCESS_TIMEOUT = int(os.environ.get("QOS_PROBE_TIMEOUT", "20"))


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_log(message):
    print(f"[qos-probe] {message}", flush=True)


def run_json(command, timeout):
    """Jalankan perintah dan kembalikan JSON (atau None bila gagal)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        write_log(f"{command[0]} gagal: {exc.__class__.__name__}")
        return None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        # iperf3 pesan error berada di field JSON "error", bukan di stderr.
        message = ""
        try:
            payload = json.loads(detail)
            if isinstance(payload, dict) and payload.get("error"):
                message = str(payload["error"])
        except ValueError:
            pass
        if not message:
            lines = [line.strip() for line in detail.splitlines() if line.strip()]
            message = lines[-1] if lines else "tidak ada pesan"
        write_log(f"{command[0]} keluar dengan kode {result.returncode}: {message}")
        return None
    try:
        return json.loads(result.stdout.decode("utf-8", "replace"))
    except ValueError:
        write_log(f"{command[0]} bukan JSON")
        return None


def measure_throughput(attempts=2):
    """iperf3 TCP: throughput (retry sekali bila server sedang sibuk)."""
    payload = None
    for _ in range(max(1, attempts)):
        payload = run_json(
            [
                IPERF3_BINARY,
                "-c",
                TARGET_HOST,
                "-p",
                str(TCP_PORT),
                "-t",
                str(TCP_DURATION),
                "-J",
            ],
            TCP_DURATION + SUBPROCESS_TIMEOUT,
        )
        if payload:
            break
        time.sleep(1)
    if not payload:
        return None
    end = payload.get("end") if isinstance(payload, dict) else None
    if not isinstance(end, dict):
        return None
    received = end.get("sum_received") if isinstance(end.get("sum_received"), dict) else {}
    bits = received.get("bits_per_second")
    if not isinstance(bits, (int, float)):
        return None
    return round(bits / 1_000_000, 3)


def measure_loss(attempts=2):
    """iperf3 UDP: jitter (loss UDP dipertahankan sebagai fallback)."""
    payload = None
    for _ in range(max(1, attempts)):
        payload = run_json(
            [
                IPERF3_BINARY,
                "-c",
                TARGET_HOST,
                "-p",
                str(UDP_PORT),
                "-t",
                str(UDP_DURATION),
                "-J",
                "-u",
                "-b",
                UDP_BANDWIDTH,
            ],
            UDP_DURATION + SUBPROCESS_TIMEOUT,
        )
        if payload:
            break
        time.sleep(1)
    if not payload:
        return None, None
    end = payload.get("end") if isinstance(payload, dict) else None
    if not isinstance(end, dict):
        return None, None
    summary = end.get("sum") if isinstance(end.get("sum"), dict) else {}
    jitter = summary.get("jitter_ms")
    loss = summary.get("lost_percent")
    return (
        round(float(jitter), 3) if isinstance(jitter, (int, float)) else None,
        round(float(loss), 3) if isinstance(loss, (int, float)) else None,
    )


def measure_delay():
    """ICMP ping: delay rata-rata + packet loss."""
    try:
        result = subprocess.run(
            [
                PING_BINARY,
                "-c",
                str(PING_COUNT),
                "-i",
                PING_INTERVAL,
                "-W",
                str(PING_TIMEOUT),
                TARGET_HOST,
            ],
            capture_output=True,
            timeout=PING_COUNT + PING_TIMEOUT + 5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        write_log(f"ping gagal: {exc.__class__.__name__}")
        return None, None

    text = (result.stdout or b"").decode("utf-8", "replace")
    delay = None
    loss = None
    for line in text.splitlines():
        if "rtt" in line or "min/avg/max" in line:
            parts = line.split("=")[-1].split("/")
            if len(parts) >= 2:
                try:
                    delay = round(float(parts[1]), 3)
                except ValueError:
                    delay = None
        if "packet loss" in line and "%" in line:
            try:
                loss = round(float(line.split("%")[0].split(",")[-1].strip()), 3)
            except ValueError:
                loss = None
    return delay, loss


def read_history():
    """Baca histori probe (toleran terhadap file rusak atau kosong)."""
    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def append_history(point):
    """Tambahkan satu titik ke histori lalu simpan (maks HISTORY_MAX_POINTS)."""
    history = read_history()
    history.append(point)
    if len(history) > HISTORY_MAX_POINTS:
        history = history[-HISTORY_MAX_POINTS:]
    write_json(HISTORY_PATH, history)
    return len(history)


def write_json(path, payload):
    """Tulis JSON secara atomik (tmp + rename) supaya tidak pernah dibaca setengah."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


def write_result(payload):
    """Tulis hasil probe terakhir (atomik)."""
    write_json(OUTPUT_PATH, payload)


def main():
    if not shutil.which(IPERF3_BINARY) and not os.path.exists(IPERF3_BINARY):
        write_log(f"iperf3 tidak ditemukan: {IPERF3_BINARY}")
        return 2

    started = time.time()
    delay, ping_loss = measure_delay()
    throughput = measure_throughput()
    jitter, udp_loss = measure_loss()

    loss_source = (
        "ping" if ping_loss is not None else ("udp" if udp_loss is not None else None)
    )
    loss = ping_loss if ping_loss is not None else udp_loss
    payload = {
        "timestamp": utc_now_iso(),
        "target": TARGET_HOST,
        "delay_ms": delay,
        "jitter_ms": jitter,
        "packet_loss_percent": loss,
        "packet_loss_source": loss_source,
        "throughput_mbps": throughput,
        "ping_packet_loss_percent": ping_loss,
        "udp_packet_loss_percent": udp_loss,
        "duration_seconds": round(time.time() - started, 3),
        "ok": delay is not None or throughput is not None,
    }
    try:
        write_result(payload)
        point = {
            "t": payload["timestamp"],
            "delay_ms": payload["delay_ms"],
            "jitter_ms": payload["jitter_ms"],
            "packet_loss_percent": payload["packet_loss_percent"],
            "throughput_mbps": payload["throughput_mbps"],
        }
        kept = append_history(point)
    except OSError as exc:
        write_log(f"gagal menulis hasil: {exc.__class__.__name__}")
        return 1
    write_log(
        "delay={delay} ms throughput={throughput} Mbps jitter={jitter} ms loss={loss}% "
        "({source}; histori {kept} titik)".format(
            delay=delay,
            throughput=throughput,
            jitter=jitter,
            loss=loss,
            source=loss_source or "tidak tersedia",
            kept=kept,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
