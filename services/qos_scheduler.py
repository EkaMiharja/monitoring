"""Background scheduler for automatic QoS measurements.

The scheduler triggers the ping and iperf3 runners of every configured VM on a
fixed interval so the QoS panels keep receiving samples without pressing the
manual buttons. It never runs two measurements of the same kind at once: every
runner refuses to start while it is already busy, and the iperf3 cooldown is
evaluated per runner.
"""

from __future__ import annotations

import threading

from utils import iso, parse_iso, utc_now

PING_METRIC = "ping"
IPERF3_METRIC = "iperf3"


class QosScheduler:
    """Run QoS measurements automatically on a fixed interval for many VMs."""

    def __init__(self, config, runners_by_vm=None):
        self.enabled = bool(config.get("QOS_AUTO_ENABLED", False))
        self.interval = max(1, int(config.get("QOS_AUTO_INTERVAL_SECONDS", 5) or 5))
        self.metrics = self._parse_metrics(config.get("QOS_AUTO_METRICS"))
        duration = config.get("QOS_AUTO_IPERF3_DURATION_SECONDS")
        self.iperf_duration = int(duration) if duration else None
        bandwidth = config.get("QOS_AUTO_IPERF3_BANDWIDTH")
        self.iperf_bandwidth = str(bandwidth).strip() if bandwidth else None
        self.iperf_cooldown = max(
            0, int(config.get("QOS_AUTO_IPERF3_COOLDOWN_SECONDS", 2) or 0)
        )
        protocol = config.get("QOS_AUTO_IPERF3_PROTOCOL")
        self.iperf_protocol = str(protocol).strip().lower() if protocol else None
        self.loss_enabled = bool(config.get("QOS_AUTO_LOSS_ENABLED", True))
        self.loss_duration = max(1, int(config.get("QOS_AUTO_LOSS_DURATION_SECONDS", 2) or 2))
        loss_bandwidth = config.get("QOS_AUTO_LOSS_BANDWIDTH")
        self.loss_bandwidth = str(loss_bandwidth).strip() if loss_bandwidth else None
        self.loss_interval = max(5, int(config.get("QOS_AUTO_LOSS_INTERVAL_SECONDS", 30) or 30))
        self.runners_by_vm = dict(runners_by_vm or {})
        # VM yang terakhir dibuka di dashboard -> profil UDP (jitter & packet loss)
        # hanya dijalankan untuk VM ini.
        self.active_vm = None
        # Jarak antar VM saat tes pertama: hindari dua stream iperf3 UDP bersamaan.
        self.stagger_seconds = max(
            0, int(self.interval // max(1, 2 * len(self.runners_by_vm)))
        ) if self.runners_by_vm else 0
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._started_at = None
        self._last_loss_at = {}
        self._loss_inflight = False
        self.last_tick = None
        self.last_error = None

    @staticmethod
    def _parse_metrics(raw):
        if raw is None:
            return {PING_METRIC}
        if isinstance(raw, str):
            parts = raw.split(",")
        else:
            parts = list(raw)
        names = {str(part).strip().lower() for part in parts if str(part).strip()}
        return names or {PING_METRIC}

    def start(self):
        if not self.enabled or self._thread is not None:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="qos-scheduler", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    @property
    def running(self):
        thread = self._thread
        return bool(thread and thread.is_alive())

    def _loop(self):
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(self.interval):
                break

    def set_active_vm(self, vm):
        """Catat VM yang sedang dibuka; profil UDP hanya jalan untuk VM ini."""
        if not vm:
            return
        with self.lock:
            if vm == self.active_vm:
                return
            self.active_vm = vm
            # VM baru boleh langsung tes, tidak menunggu sisa interval VM lama.
            self._last_loss_at.pop(vm, None)

    def tick(self):
        """Trigger one measurement per configured metric for every VM."""
        with self.lock:
            if self._started_at is None:
                self._started_at = utc_now()
            self.last_tick = iso(utc_now())
        for index, (vm, runners) in enumerate(self.runners_by_vm.items()):
            for metric in sorted(self.metrics):
                try:
                    self._trigger(vm, runners, metric, index)
                except Exception as exc:  # noqa: BLE001 - scheduler must survive runner errors
                    with self.lock:
                        self.last_error = f"{vm}/{metric}: {exc.__class__.__name__}: {exc}"
        self._trigger_loss()
        self._release_loss_slot()

    def _trigger(self, vm, runners, metric, index=0):
        if metric == PING_METRIC:
            runner = runners.get("ping")
            if runner is not None:
                runner.start()
            return
        if metric == IPERF3_METRIC:
            runner = runners.get("iperf3")
            if runner is None:
                return
            if getattr(runner, "running", False):
                return
            if not self._iperf_ready(runner, index):
                return
            runner.start(
                duration_seconds=self.iperf_duration,
                bandwidth=self.iperf_bandwidth,
                protocol=self.iperf_protocol,
            )

    def _trigger_loss(self):
        """Jalankan tes UDP ringan (jitter & packet loss) untuk VM yang aktif saja.

        Hanya satu stream UDP berjalan pada satu waktu supaya server iperf3
        tidak ikut sibuk dan tes TCP tidak terpengaruh.
        """
        if not self.loss_enabled:
            return
        with self.lock:
            vm = self.active_vm
        if not vm:
            return
        runner = self.runners_by_vm.get(vm, {}).get("iperf3")
        if runner is None or not hasattr(runner, "start_loss"):
            return
        if getattr(runner, "loss_running", False):
            return
        now = utc_now()
        with self.lock:
            if self._loss_inflight:
                return
            last = self._last_loss_at.get(vm)
            if last is not None and (now - last).total_seconds() < self.loss_interval:
                return
            self._last_loss_at[vm] = now
            self._loss_inflight = True
        try:
            runner.start_loss(
                duration_seconds=self.loss_duration,
                bandwidth=self.loss_bandwidth,
                protocol="udp",
            )
        except Exception as exc:  # noqa: BLE001 - scheduler must survive runner errors
            with self.lock:
                self._loss_inflight = False
                self.last_error = f"{vm}/loss: {exc.__class__.__name__}: {exc}"

    def _release_loss_slot(self):
        """Lepas slot UDP ketika tidak ada tes UDP yang berjalan."""
        with self.lock:
            if not self._loss_inflight:
                return
            for runners in self.runners_by_vm.values():
                runner = runners.get("iperf3")
                if runner is not None and getattr(runner, "loss_running", False):
                    return
            self._loss_inflight = False

    def _iperf_ready(self, runner, index=0):
        """Wait for a gap after the previous iperf3 run of this runner.

        The iperf3 server handles one test at a time; starting a new client
        while the previous test is still winding down makes the client hang.
        Tes pertama tiap VM juga digeser agar tidak ada dua stream UDP
        bersamaan di laptop.
        """
        if self.iperf_cooldown <= 0:
            return True
        meta = getattr(runner, "meta", None) or {}
        started = parse_iso(meta.get("timestamp"))
        if started is None:
            if self._started_at is None:
                return True
            offset = index * self.stagger_seconds
            return (utc_now() - self._started_at).total_seconds() >= offset
        duration = self.iperf_duration or getattr(runner, "duration", 0)
        elapsed = (utc_now() - started).total_seconds()
        return elapsed >= duration + self.iperf_cooldown + index * self.stagger_seconds

    def status(self):
        with self.lock:
            return {
                "enabled": self.enabled,
                "interval_seconds": self.interval,
                "metrics": sorted(self.metrics),
                "running": self.running,
                "last_tick": self.last_tick,
                "last_error": self.last_error,
                "loss_enabled": self.loss_enabled,
                "loss_interval_seconds": self.loss_interval,
                "active_vm": self.active_vm,
                "vms": sorted(self.runners_by_vm),
            }
