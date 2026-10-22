import threading
import time

from services.qos_scheduler import QosScheduler


class FakeRunner:
    def __init__(self, configured=True):
        self.configured_flag = configured
        self.calls = []
        self.busy = False
        self.duration = 3
        self.meta = None
        self.lock = threading.Lock()

    def configured(self):
        return self.configured_flag

    def start(self, **kwargs):
        with self.lock:
            self.calls.append(kwargs)
            if self.busy:
                return False
        return True


def make_scheduler(**overrides):
    config = {
        "QOS_AUTO_ENABLED": True,
        "QOS_AUTO_INTERVAL_SECONDS": 5,
        "QOS_AUTO_METRICS": "ping,iperf3",
        "QOS_AUTO_IPERF3_DURATION_SECONDS": 3,
        "QOS_AUTO_IPERF3_BANDWIDTH": "10M",
    }
    config.update(overrides)
    iperf_a, delay_a = FakeRunner(), FakeRunner()
    iperf_b, delay_b = FakeRunner(), FakeRunner()
    runners = {
        "lightgbm-vm": {"iperf3": iperf_a, "ping": delay_a},
        "randomforest-vm": {"iperf3": iperf_b, "ping": delay_b},
    }
    return QosScheduler(config, runners_by_vm=runners), iperf_a, delay_a, iperf_b, delay_b


def test_scheduler_parses_metrics_and_interval():
    scheduler, _, _, _, _ = make_scheduler(QOS_AUTO_METRICS=" ping , iperf3 ")

    assert scheduler.enabled is True
    assert scheduler.interval == 5
    assert scheduler.metrics == {"ping", "iperf3"}
    assert scheduler.iperf_duration == 3
    assert scheduler.iperf_bandwidth == "10M"


def test_scheduler_defaults_to_ping_when_metrics_missing():
    scheduler, _, _, _, _ = make_scheduler(QOS_AUTO_METRICS="")

    assert scheduler.metrics == {"ping"}


def test_tick_triggers_each_metric_for_every_vm():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.stagger_seconds = 0

    scheduler.tick()

    for delay in (delay_a, delay_b):
        assert len(delay.calls) == 1
    for iperf in (iperf_a, iperf_b):
        assert len(iperf.calls) == 1
        assert iperf.calls[0] == {"duration_seconds": 3, "bandwidth": "10M", "protocol": None}


def test_tick_only_triggers_selected_metrics():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler(QOS_AUTO_METRICS="ping")

    scheduler.tick()

    assert len(delay_a.calls) == 1
    assert len(delay_b.calls) == 1
    assert iperf_a.calls == []
    assert iperf_b.calls == []


def test_tick_skips_metric_not_requested_and_reports_status():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler(QOS_AUTO_METRICS="iperf3")

    scheduler.tick()
    status = scheduler.status()

    assert len(iperf_a.calls) == 1
    assert delay_a.calls == []
    assert status["enabled"] is True
    assert status["interval_seconds"] == 5
    assert status["metrics"] == ["iperf3"]
    assert status["running"] is False
    assert status["last_tick"] is not None
    assert status["vms"] == ["lightgbm-vm", "randomforest-vm"]


def test_runner_refuses_second_measurement_while_busy():
    iperf = FakeRunner()
    iperf.busy = True
    scheduler = QosScheduler(
        {
            "QOS_AUTO_ENABLED": True,
            "QOS_AUTO_INTERVAL_SECONDS": 2,
            "QOS_AUTO_METRICS": "iperf3",
        },
        runners_by_vm={"lightgbm-vm": {"iperf3": iperf, "ping": FakeRunner()}},
    )

    scheduler.tick()

    assert len(iperf.calls) == 1
    assert iperf.calls[0] == {"duration_seconds": None, "bandwidth": None, "protocol": None}


def test_scheduler_thread_runs_and_stops():
    scheduler, _, delay_a, _, delay_b = make_scheduler(QOS_AUTO_INTERVAL_SECONDS=1)

    assert scheduler.start() is True
    deadline = time.time() + 5
    while time.time() < deadline and (len(delay_a.calls) < 2 or len(delay_b.calls) < 2):
        time.sleep(0.1)
    scheduler.stop()

    assert len(delay_a.calls) >= 2
    assert len(delay_b.calls) >= 2
    deadline = time.time() + 5
    while time.time() < deadline and scheduler.running:
        time.sleep(0.05)
    assert scheduler.running is False


def test_scheduler_does_not_start_when_disabled():
    scheduler, _, _, _, _ = make_scheduler(QOS_AUTO_ENABLED=False)

    assert scheduler.start() is False
    assert scheduler.status()["running"] is False


def test_iperf3_waits_for_cooldown_after_previous_run():
    from utils import iso, utc_now

    iperf = FakeRunner()
    iperf.meta = {"timestamp": iso(utc_now()), "status": "success"}
    scheduler = QosScheduler(
        {
            "QOS_AUTO_ENABLED": True,
            "QOS_AUTO_INTERVAL_SECONDS": 5,
            "QOS_AUTO_METRICS": "iperf3",
            "QOS_AUTO_IPERF3_DURATION_SECONDS": 3,
            "QOS_AUTO_IPERF3_COOLDOWN_SECONDS": 2,
        },
        runners_by_vm={"lightgbm-vm": {"iperf3": iperf, "ping": FakeRunner()}},
    )

    scheduler.tick()

    assert iperf.calls == []


def test_iperf3_runs_again_after_cooldown():
    iperf = FakeRunner()
    iperf.meta = {"timestamp": "2020-01-01T00:00:00Z", "status": "success"}
    scheduler = QosScheduler(
        {
            "QOS_AUTO_ENABLED": True,
            "QOS_AUTO_INTERVAL_SECONDS": 5,
            "QOS_AUTO_METRICS": "iperf3",
            "QOS_AUTO_IPERF3_DURATION_SECONDS": 3,
            "QOS_AUTO_IPERF3_COOLDOWN_SECONDS": 2,
        },
        runners_by_vm={"lightgbm-vm": {"iperf3": iperf, "ping": FakeRunner()}},
    )

    scheduler.tick()

    assert len(iperf.calls) == 1


def test_first_run_of_each_vm_is_staggered():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.stagger_seconds = 3

    scheduler.tick()

    assert len(iperf_a.calls) == 1
    assert iperf_b.calls == []
    assert len(delay_a.calls) == 1
    assert len(delay_b.calls) == 1


def test_cooldown_is_evaluated_per_runner():
    from utils import iso, utc_now

    iperf_a = FakeRunner()
    iperf_a.meta = {"timestamp": iso(utc_now()), "status": "success"}
    iperf_b = FakeRunner()
    iperf_b.meta = {"timestamp": "2020-01-01T00:00:00Z", "status": "success"}
    scheduler = QosScheduler(
        {
            "QOS_AUTO_ENABLED": True,
            "QOS_AUTO_INTERVAL_SECONDS": 5,
            "QOS_AUTO_METRICS": "iperf3",
            "QOS_AUTO_IPERF3_DURATION_SECONDS": 3,
            "QOS_AUTO_IPERF3_COOLDOWN_SECONDS": 2,
        },
        runners_by_vm={
            "lightgbm-vm": {"iperf3": iperf_a, "ping": FakeRunner()},
            "randomforest-vm": {"iperf3": iperf_b, "ping": FakeRunner()},
        },
    )

    scheduler.tick()

    assert iperf_a.calls == []
    assert len(iperf_b.calls) == 1


def test_loss_profile_runs_on_its_own_interval():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.loss_enabled = True
    scheduler.loss_interval = 30
    scheduler.loss_duration = 2
    scheduler.loss_bandwidth = "1M"

    started = []
    for runner in (iperf_a, iperf_b):
        runner.start_loss = lambda **kwargs: started.append(kwargs) or True

    scheduler.set_active_vm("lightgbm-vm")
    scheduler.tick()
    assert len(started) == 1
    assert started[0] == {"duration_seconds": 2, "bandwidth": "1M", "protocol": "udp"}

    started.clear()
    scheduler.tick()
    assert started == []


def test_loss_profile_only_runs_for_active_vm():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.loss_enabled = True
    scheduler.loss_interval = 10
    scheduler.loss_bandwidth = "1M"
    started = []
    for runner in (iperf_a, iperf_b):
        runner.start_loss = lambda **kwargs: started.append(kwargs) or True

    scheduler.set_active_vm("lightgbm-vm")
    scheduler.tick()

    assert len(started) == 1
    assert started[0] == {"duration_seconds": 2, "bandwidth": "1M", "protocol": "udp"}


def test_switching_active_vm_stops_previous_and_allows_new_one():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.loss_enabled = True
    scheduler.loss_interval = 10
    scheduler.loss_bandwidth = "1M"
    started = []
    for runner in (iperf_a, iperf_b):
        runner.start_loss = lambda **kwargs: started.append(kwargs) or True

    scheduler.set_active_vm("lightgbm-vm")
    scheduler.tick()
    assert len(started) == 1

    started.clear()
    scheduler.set_active_vm("randomforest-vm")
    scheduler.tick()

    assert len(started) == 1
    assert scheduler.active_vm == "randomforest-vm"


def test_loss_interval_gate_is_per_vm():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.loss_enabled = True
    scheduler.loss_interval = 10
    scheduler.loss_bandwidth = "1M"
    started = []
    for runner in (iperf_a, iperf_b):
        runner.start_loss = lambda **kwargs: started.append(kwargs) or True

    scheduler.set_active_vm("lightgbm-vm")
    scheduler.tick()
    assert len(started) == 1

    started.clear()
    scheduler.tick()
    assert started == []

    scheduler._last_loss_at["lightgbm-vm"] = None
    scheduler._last_loss_at.pop("lightgbm-vm", None)
    scheduler._loss_inflight = False
    scheduler.tick()
    assert len(started) == 1


def test_loss_profile_uses_separate_port():
    scheduler, iperf_a, delay_a, iperf_b, delay_b = make_scheduler()
    scheduler.loss_enabled = True
    scheduler.loss_interval = 10
    scheduler.loss_bandwidth = "1M"
    started = []
    for runner in (iperf_a, iperf_b):
        runner.start_loss = lambda **kwargs: started.append(kwargs) or True

    scheduler.set_active_vm("lightgbm-vm")
    scheduler.tick()

    assert len(started) == 1
    assert started[0]["protocol"] == "udp"


def test_status_exposes_active_vm():
    scheduler, _, _, _, _ = make_scheduler()

    assert scheduler.status()["active_vm"] is None
    scheduler.set_active_vm("randomforest-vm")
    assert scheduler.status()["active_vm"] == "randomforest-vm"
