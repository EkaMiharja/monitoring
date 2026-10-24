import { clear, el, makeBadge, setHidden } from "../dom.js";
import { capitalize, formatCountdown, formatDateTime, formatShortTime } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

let countdownTimer = null;

function countdownDeadline(item) {
    const raw = item?.remaining_seconds;
    if (raw !== null && raw !== undefined && raw !== "") {
        const remaining = Number(raw);
        if (Number.isFinite(remaining)) {
            return Date.now() + Math.max(0, remaining) * 1000;
        }
    }
    const date = item?.unblock_at ? new Date(item.unblock_at) : null;
    return date && !Number.isNaN(date.getTime()) ? date.getTime() : null;
}

function tickCountdowns() {
    const nodes = document.querySelectorAll("[data-countdown][data-deadline]");
    nodes.forEach((node) => {
        const deadline = Number(node.dataset.deadline);
        if (!Number.isFinite(deadline)) return;
        const remaining = Math.ceil((deadline - Date.now()) / 1000);
        if (remaining <= 0) {
            node.textContent = "Mengunblock…";
            node.classList.add("countdown--expired");
            node.removeAttribute("data-deadline");
            return;
        }
        node.textContent = formatCountdown(remaining);
    });
}

function syncCountdownTimer() {
    const hasDeadline = document.querySelector("[data-countdown][data-deadline]");
    if (hasDeadline && countdownTimer === null) {
        countdownTimer = window.setInterval(tickCountdowns, 1000);
    } else if (!hasDeadline && countdownTimer !== null) {
        window.clearInterval(countdownTimer);
        countdownTimer = null;
    }
}

export function updateBlocked(section) {
    const root = updatePanelMeta("blocked", section);
    const tbody = root?.querySelector("[data-blocked-rows]");
    if (!tbody) return;

    clear(tbody);
    const items = section?.items || [];

    items.forEach((item) => {
        const row = el("tr");
        row.appendChild(el("td", { className: "mono", text: item.ip || "—" }));

        const origin = [item.source, item.jail].filter(Boolean).join(" · ");
        row.appendChild(el("td", { text: origin || "—" }));
        row.appendChild(
            el("td", {
                text: formatShortTime(item.blocked_at),
                attrs: { title: formatDateTime(item.blocked_at) },
            }),
        );

        const countdownCell = el("td");
        const countdown = el("span", { className: "countdown" });
        const deadline = countdownDeadline(item);
        if (deadline === null) {
            countdown.textContent = "Manual";
            countdown.classList.add("countdown--manual");
        } else {
            countdown.dataset.deadline = String(deadline);
            countdown.textContent = formatCountdown((deadline - Date.now()) / 1000);
            if (item.unblock_at) {
                countdown.title = `Unblock: ${formatDateTime(item.unblock_at)}`;
            }
        }
        countdownCell.appendChild(countdown);
        row.appendChild(countdownCell);

        const statusCell = el("td");
        const blocked = String(item.status || "").toLowerCase() === "blocked";
        statusCell.appendChild(
            makeBadge(blocked ? "success" : "neutral", blocked ? "Blocked" : capitalize(item.status)),
        );
        row.appendChild(statusCell);
        tbody.appendChild(row);
    });

    tickCountdowns();
    syncCountdownTimer();
    setHidden(root.querySelector(".table-wrap"), items.length === 0);
    setEmptyState(
        root,
        items.length === 0,
        section?.status === "error" ? "Gagal memuat daftar IP" : "Belum ada IP yang diblokir",
        section?.error || "Daftar ini memuat IP yang diblokir LightGBM dan Fail2Ban.",
    );
}
