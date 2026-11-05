import { fetchDetections } from "./api.js";
import { setHidden, setText } from "./dom.js";
import { formatDateTime } from "./format.js";
import { Poller } from "./polling.js";
import { initDetections, updateDetections } from "./panels/detections.js";

const shell = document.querySelector(".app-shell");
const intervalMs = Number(shell?.dataset.pollInterval) || 5000;
const connection = document.getElementById("connection");
const connectionText = document.getElementById("connection-text");
const lastUpdated = document.getElementById("last-updated");
const globalError = document.getElementById("global-error");
const globalErrorMessage = document.getElementById("global-error-message");
const demoBanner = document.getElementById("demo-banner");
const refreshButton = document.getElementById("refresh-button");

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

function applyDetections(data) {
    lastGeneratedAt = data.generated_at || null;
    updateDetections(data);
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
        const data = await fetchDetections({ signal });
        applyDetections(data);
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

initDetections();
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
