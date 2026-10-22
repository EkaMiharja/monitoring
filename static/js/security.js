import { fetchOverview, sendTelegramTest } from "./api.js";
import { setHidden, setText } from "./dom.js";
import { formatDateTime } from "./format.js";
import { Poller } from "./polling.js";
import { initAttacks, updateAttacks } from "./panels/attacks.js";
import { updateBlocked } from "./panels/blocked.js";
import { updateTelegram } from "./panels/telegram.js";

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

let lastGeneratedAt = null;

function setConnection(state, text) {
    if (!connection) return;
    connection.dataset.connection = state;
    const isLive = state === "ok";
    const isWaiting = state !== "ok";
    const loader = connection.querySelector(".loader");
    if (loader) loader.hidden = isLive;
    setText(connectionText, isLive ? "Live" : isWaiting ? "" : text);
    if (connectionText) connectionText.hidden = connectionText.textContent === "";
}

function showGlobalError(message) {
    setText(globalErrorMessage, message);
    setHidden(globalError, false);
}

function hideGlobalError() {
    setHidden(globalError, true);
}

function applyOverview(data) {
    lastGeneratedAt = data.generated_at || null;
    updateBlocked(data.blocked_ips || {});
    updateAttacks(data.attacks || {});
    updateTelegram(data.telegram || {});
    setHidden(demoBanner, data.data_mode !== "demo");

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
        const data = await fetchOverview({ signal });
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
