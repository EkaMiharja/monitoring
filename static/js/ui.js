import { applyBadge, setHidden, setText, statusLabel } from "./dom.js";

export function panel(name) {
    return document.querySelector(`[data-panel="${name}"]`);
}

export function updatePanelMeta(name, section) {
    const root = panel(name);
    if (!root) return null;

    applyBadge(root.querySelector("[data-status]"), section?.status || "unavailable");
    setText(root.querySelector("[data-source]"), section?.source || "—");

    const errorNode = root.querySelector("[data-section-error]");
    if (errorNode) {
        const message = section?.error || "";
        const visible = Boolean(message) && !["ok", "empty"].includes(section?.status);
        errorNode.textContent = message;
        setHidden(errorNode, !visible);
    }
    return root;
}

const STATE_TITLES = {
    empty: "Belum ada data",
    error: "Gagal memuat data",
    unavailable: "Belum tersedia",
};

export function setChartState(root, section, visible) {
    const overlay = root?.querySelector("[data-state]");
    if (!overlay) return;
    overlay.hidden = !visible;
    if (!visible) return;

    const status = section?.status || "unavailable";
    setText(overlay.querySelector("[data-state-title]"), STATE_TITLES[status] || statusLabel(status));
    setText(overlay.querySelector("[data-state-message]"), section?.error || "Menunggu data berikutnya.");
}

export function setEmptyState(root, visible, title, message) {
    const empty = root?.querySelector("[data-empty]");
    if (!empty) return;
    empty.hidden = !visible;
    if (title) setText(empty.querySelector(".empty-state__title"), title);
    if (message) setText(empty.querySelector(".empty-state__text"), message);
}

export function lastValue(series) {
    if (!Array.isArray(series) || series.length === 0) return null;
    return series[series.length - 1]?.value ?? null;
}
