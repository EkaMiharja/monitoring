export function el(tag, { className, text, attrs } = {}) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    if (attrs) {
        Object.entries(attrs).forEach(([key, value]) => {
            if (value !== null && value !== undefined) node.setAttribute(key, value);
        });
    }
    return node;
}

export function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
}

export function setText(node, text) {
    if (node) node.textContent = text;
}

export function setHidden(node, hidden) {
    if (node) node.hidden = Boolean(hidden);
}

const PANEL_TONES = {
    ok: "ok",
    success: "success",
    empty: "empty",
    error: "error",
    unavailable: "unavailable",
    stale: "warning",
    pending: "warning",
    warning: "warning",
    delivered: "success",
    failed: "error",
    danger: "danger",
};

const PANEL_LABELS = {
    ok: "Aktif",
    success: "OK",
    empty: "Kosong",
    error: "Error",
    unavailable: "Tidak tersedia",
    stale: "Stale",
    pending: "Menunggu",
    delivered: "Terkirim",
    failed: "Gagal",
};

export function badgeTone(status) {
    return PANEL_TONES[status] || "neutral";
}

export function statusLabel(status) {
    return PANEL_LABELS[status] || status || "Tidak diketahui";
}

export function makeBadge(status, label) {
    const badge = el("span", { className: `badge badge--${badgeTone(status)}` });
    badge.appendChild(el("span", { className: "status-dot", attrs: { "aria-hidden": "true" } }));
    badge.appendChild(el("span", { text: label || statusLabel(status) }));
    return badge;
}

export function applyBadge(badge, status, label) {
    if (!badge) return;
    const tone = badgeTone(status);
    const isLive = tone === "ok";
    const isPlain = tone === "empty";
    const isWaiting = ["neutral", "warning", "error", "unavailable"].includes(tone);
    badge.className = isLive ? "status-live" : isPlain ? "status-text" : `badge badge--${tone}`;
    const loader = badge.querySelector(".loader");
    if (loader) loader.hidden = isLive || isPlain;
    const textNode = badge.querySelector("[data-status-text]") || badge.querySelector("span:last-child");
    if (!textNode) return;
    if (isLive) textNode.textContent = "Live";
    else if (isWaiting) textNode.textContent = "";
    else textNode.textContent = label || statusLabel(status);
    textNode.hidden = textNode.textContent === "";
}

export function debounce(callback, wait = 160) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => callback(...args), wait);
    };
}
