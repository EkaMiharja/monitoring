import { fetchOverview, runDelayTest, runIperfTest, sendTelegramTest } from "./api.js";
import { setHidden, setText } from "./dom.js";
import { formatDateTime } from "./format.js";
import { Poller } from "./polling.js";
import { initAttacks, updateAttacks } from "./panels/attacks.js";
import { updateBlocked } from "./panels/blocked.js";
import { updateQos } from "./panels/qos.js";
import { updateResources } from "./panels/resources.js";
import { updateTelegram } from "./panels/telegram.js";
import { updateTraffic } from "./panels/traffic.js";

const shell = document.querySelector(".app-shell");
const intervalMs = Number(shell?.dataset.pollInterval) || 5000;
const connection = document.getElementById("connection");
const connectionText = document.getElementById("connection-text");
const lastUpdated = document.getElementById("last-updated");
const globalError = document.getElementById("global-error");
const globalErrorMessage = document.getElementById("global-error-message");
const demoBanner = document.getElementById("demo-banner");
const refreshButton = document.getElementById("refresh-button");
const telegramButton = document.getElementById("telegram-test-btn");
const telegramMessage = document.getElementById("telegram-test-message");
const iperfRunButton = document.getElementById("iperf-run-btn");
const delayRunButton = document.getElementById("delay-run-btn");
const qosRunMessage = document.getElementById("qos-run-message");
const qosRunState = document.querySelector("[data-qos-run-state]");
const vmSelect = document.getElementById("vm-select");

let lastGeneratedAt = null;
let demoMode = demoBanner ? !demoBanner.hidden : false;
let qosBusy = false;
let runTimer = null;
let qosVmId = shell?.dataset.qosVm || "";
let currentVm = vmSelect?.value || shell?.dataset.defaultVm || "";

function setConnection(state, text) {
    if (!connection) return;
    connection.dataset.connection = state;
    setText(connectionText, text);
}

function showGlobalError(message) {
    setText(globalErrorMessage, message);
    setHidden(globalError, false);
}

function hideGlobalError() {
    setHidden(globalError, true);
}

function updateDemoBanner(mode) {
    setHidden(demoBanner, mode !== "demo");
    demoMode = mode === "demo";
    syncQosButtons();
}

function syncQosButtons() {
    const qosMismatch = Boolean(qosVmId) && currentVm !== qosVmId;
    [iperfRunButton, delayRunButton].forEach((button) => {
        if (!button) return;
        button.disabled = qosBusy || demoMode || qosMismatch;
        if (demoMode) {
            button.title = "Hanya tersedia pada mode live.";
        } else if (qosMismatch) {
            button.title = `QoS hanya diukur untuk ${qosVmId}.`;
        } else {
            button.removeAttribute("title");
        }
    });
}

function switchVm(vm) {
    if (!vm || vm === currentVm) return;
    currentVm = vm;

    if (runTimer) {
        clearInterval(runTimer);
        runTimer = null;
        setQosBusy(false);
        setQosMessage("Pemantauan tes dihentikan karena VM berubah.");
    }

    const url = new URL(window.location.href);
    url.searchParams.set("vm", vm);
    window.history.replaceState(null, "", url);

    syncQosButtons();
    poller.kick();
}

function setQosMessage(text, kind) {
    if (!qosRunMessage) return;
    qosRunMessage.textContent = text || "";
    qosRunMessage.className = `inline-message${kind ? ` inline-message--${kind}` : ""}`;
    qosRunMessage.hidden = !text;
}

function setQosBusy(busy, label) {
    qosBusy = busy;
    syncQosButtons();
    if (qosRunState) qosRunState.textContent = busy ? label : "Manual";
}

function watchQosRun(estimatedSeconds) {
    if (runTimer) clearInterval(runTimer);
    const deadline = Date.now() + (Number(estimatedSeconds) + 6) * 1000;
    runTimer = setInterval(async () => {
        try {
            await poller.refresh();
        } catch {
        }
        const qosPanel = document.querySelector('[data-panel="qos"]');        const status = qosPanel?.dataset.qosStatus || "";
        const finished = status === "success" || status === "failed";
        if (!finished && Date.now() < deadline) return;

        clearInterval(runTimer);
        runTimer = null;
        setQosBusy(false);
        if (status === "success") {
            setQosMessage("Pengujian selesai. Grafik QoS diperbarui.", "success");
        } else if (status === "failed") {
            setQosMessage("Pengujian gagal. Lihat detail pada panel QoS.", "error");
        } else {
            setQosMessage("Pengujian belum menghasilkan data. Coba lagi.", "error");
        }
    }, 2000);
}

async function triggerQos(action, initMessage) {
    if (qosBusy || demoMode) return;
    setQosBusy(true, "Menjalankan…");
    setQosMessage(initMessage);
    try {
        const result = await action();
        const seconds = Number(result?.estimated_seconds) || 15;
        setQosMessage(`Pengujian berjalan (± ${Math.round(seconds)} detik)…`);
        watchQosRun(seconds);
    } catch (error) {
        setQosBusy(false);
        setQosMessage(error?.message || "Gagal memulai pengujian.", "error");
    }
}

function applyOverview(data) {
    lastGeneratedAt = data.generated_at || null;
    if (data.qos_vm?.id && data.qos_vm.id !== qosVmId) {
        qosVmId = data.qos_vm.id;
        syncQosButtons();
    }
    updateTraffic(data.traffic || {});
    updateQos(data.qos || {});
    updateResources(data.resources || {});
    updateBlocked(data.blocked_ips || {});
    updateAttacks(data.attacks || {});
    updateTelegram(data.telegram || {});
    updateDemoBanner(data.data_mode);

    setText(lastUpdated, formatDateTime(data.generated_at));
    setConnection("ok", "Terhubung");
    hideGlobalError();
}

function handleError(error) {
    const suffix = lastGeneratedAt
        ? ` Data terakhir yang berhasil dimuat: ${formatDateTime(lastGeneratedAt)}.`
        : "";
    showGlobalError(`${error?.message || "Gagal mengambil data."}${suffix}`);
    setConnection(
        lastGeneratedAt ? "stale" : "error",
        lastGeneratedAt ? "Data mungkin usang" : "Tidak terhubung",
    );
}

const poller = new Poller({
    intervalMs,
    onTick: async (signal) => {
        const requestVm = currentVm;
        const data = await fetchOverview({ vm: requestVm, signal });
        if (requestVm !== currentVm) return;
        applyOverview(data);
    },
    onError: handleError,
});

async function refreshNow() {
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.setAttribute("aria-busy", "true");
    }
    try {
        await poller.refresh();
    } finally {
        if (refreshButton) {
            refreshButton.disabled = false;
            refreshButton.removeAttribute("aria-busy");
        }
    }
}

if (refreshButton) refreshButton.addEventListener("click", refreshNow);

if (vmSelect) {
    vmSelect.addEventListener("change", () => switchVm(vmSelect.value));
}

if (telegramButton) {
    telegramButton.addEventListener("click", async () => {
        telegramButton.disabled = true;
        telegramMessage.hidden = true;
        telegramMessage.className = "inline-message";

        try {
            await sendTelegramTest();
            telegramMessage.textContent = "Test alert diproses. Riwayat Telegram diperbarui.";
            telegramMessage.classList.add("inline-message--success");
            telegramMessage.hidden = false;
            await poller.refresh();
        } catch (error) {
            telegramMessage.textContent = error?.message || "Test alert gagal.";
            telegramMessage.classList.add("inline-message--error");
            telegramMessage.hidden = false;
        } finally {
            telegramButton.disabled = false;
        }
    });
}

if (iperfRunButton) {
    iperfRunButton.addEventListener("click", () =>
        triggerQos(runIperfTest, "Memulai tes iperf3…"),
    );
}

if (delayRunButton) {
    delayRunButton.addEventListener("click", () =>
        triggerQos(runDelayTest, "Memulai pengukuran delay…"),
    );
}

const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarScrim = document.getElementById("sidebar-scrim");

function setNavOpen(open) {
    document.body.classList.toggle("nav-open", open);
    if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", String(open));
    setHidden(sidebarScrim, !open);
}

sidebarToggle?.addEventListener("click", () => {
    setNavOpen(!document.body.classList.contains("nav-open"));
});
sidebarScrim?.addEventListener("click", () => setNavOpen(false));

document.querySelectorAll("[data-nav-link]").forEach((link) => {
    link.addEventListener("click", () => {
        if (window.matchMedia("(max-width: 900px)").matches) setNavOpen(false);
    });
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setNavOpen(false);
});

initAttacks();
if (currentVm) {
    const url = new URL(window.location.href);
    if (url.searchParams.get("vm") !== currentVm) {
        url.searchParams.set("vm", currentVm);
        window.history.replaceState(null, "", url);
    }
}
syncQosButtons();
setConnection("connecting", "Menghubungkan…");
poller.start();

document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        poller.stop();
    } else {
        poller.start();
    }
});

window.addEventListener("pagehide", () => poller.stop());
window.addEventListener("pageshow", (event) => {
    if (event.persisted) poller.start();
});
