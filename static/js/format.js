const numberFormatters = new Map();

function formatter(digits) {
    if (!numberFormatters.has(digits)) {
        numberFormatters.set(
            digits,
            new Intl.NumberFormat("id-ID", {
                maximumFractionDigits: digits,
                minimumFractionDigits: 0,
            }),
        );
    }
    return numberFormatters.get(digits);
}

export function toNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

export function formatNumber(value, digits = 2) {
    const number = toNumber(value);
    if (number === null) return "—";
    return formatter(digits).format(number);
}

export function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value) {
    const date = parseDate(value);
    if (!date) return "—";
    return new Intl.DateTimeFormat("id-ID", {
        dateStyle: "medium",
        timeStyle: "medium",
    }).format(date);
}

export function formatTime(value) {
    const date = parseDate(value);
    if (!date) return "—";
    return new Intl.DateTimeFormat("id-ID", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    }).format(date);
}

export function formatShortTime(value) {
    const date = parseDate(value);
    if (!date) return "—";
    return new Intl.DateTimeFormat("id-ID", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

export function capitalize(value) {
    if (!value) return "—";
    return String(value).charAt(0).toUpperCase() + String(value).slice(1);
}

export function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => {
        const entities = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        };
        return entities[character];
    });
}

export function formatCountdown(totalSeconds) {
    const seconds = Math.max(0, Math.ceil(Number(totalSeconds) || 0));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    const mm = String(minutes).padStart(2, "0");
    const ss = String(remainder).padStart(2, "0");
    return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}
