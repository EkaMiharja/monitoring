import { clear, debounce, el, makeBadge, setHidden } from "../dom.js";
import { formatDateTime, formatShortTime } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

let items = [];
let query = "";

function detectionTone(value) {
    const text = String(value || "").toLowerCase();
    if (["malicious", "attack", "serangan"].some((word) => text.includes(word))) return "danger";
    if (["normal", "benign", "safe"].some((word) => text.includes(word))) return "success";
    return "neutral";
}

function blockingValue(value) {
    if (typeof value === "boolean") return value;
    if (value === null || value === undefined) return null;
    const text = String(value).trim().toLowerCase();
    if (!text) return null;
    if (["blocked", "true", "banned", "yes", "1"].includes(text)) return true;
    if (["not blocked", "false", "no", "0", "unblocked"].includes(text)) return false;
    return null;
}

function render() {
    const root = document.querySelector('[data-panel="attacks"]');
    const tbody = root?.querySelector("[data-attack-rows]");
    if (!root || !tbody) return;

    clear(tbody);
    const normalized = query.toLowerCase();
    const filtered = items.filter((item) => {
        if (!normalized) return true;
        return [item.source_ip, item.attack_type, item.model, item.detection, item.target]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(normalized));
    });

    filtered.forEach((item) => {
        const row = el("tr");
        row.appendChild(
            el("td", {
                text: formatShortTime(item.detected_at),
                attrs: { title: formatDateTime(item.detected_at) },
            }),
        );
        row.appendChild(el("td", { className: "mono", text: item.source_ip || "—" }));
        row.appendChild(el("td", { text: item.attack_type || "—" }));

        const detectionCell = el("td");
        detectionCell.appendChild(
            makeBadge(detectionTone(item.detection), item.detection || "—"),
        );
        row.appendChild(detectionCell);

        row.appendChild(el("td", { text: item.model || "—" }));

        const blockingCell = el("td");
        const blocked = blockingValue(item.blocking_status);
        if (blocked === null) {
            blockingCell.textContent = "—";
        } else {
            blockingCell.appendChild(
                makeBadge(blocked ? "danger" : "neutral", blocked ? "Blocked" : "Not blocked"),
            );
        }
        row.appendChild(blockingCell);
        tbody.appendChild(row);
    });

    const counter = root.querySelector("[data-attack-count]");
    if (counter) {
        counter.textContent = normalized
            ? `${filtered.length} dari ${items.length} kejadian`
            : `${items.length} kejadian`;
    }

    setHidden(root.querySelector(".table-wrap"), filtered.length === 0);
    setEmptyState(
        root,
        filtered.length === 0,
        items.length === 0 ? "Belum ada riwayat serangan" : "Tidak ada hasil yang cocok",
        items.length === 0
            ? "Riwayat akan muncul ketika backend menyediakan data deteksi."
            : "Ubah kata kunci filter untuk melihat kejadian lain.",
    );
}

export function initAttacks() {
    const input = document.getElementById("attack-filter");
    if (input) {
        input.addEventListener(
            "input",
            debounce(() => {
                query = input.value.trim();
                render();
            }),
        );
    }
}

export function updateAttacks(section) {
    updatePanelMeta("attacks", section);
    items = section?.items || [];
    render();
}
