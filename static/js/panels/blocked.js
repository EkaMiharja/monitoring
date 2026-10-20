import { clear, el, makeBadge, setHidden } from "../dom.js";
import { capitalize, formatDateTime, formatShortTime } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

export function updateBlocked(section) {
    const root = updatePanelMeta("blocked", section);
    const tbody = root?.querySelector("[data-blocked-rows]");
    if (!tbody) return;

    clear(tbody);
    const items = section?.items || [];

    items.forEach((item) => {
        const row = el("tr");
        row.appendChild(el("td", { className: "mono", text: item.ip || "—" }));
        row.appendChild(
            el("td", {
                text: formatShortTime(item.blocked_at),
                attrs: { title: formatDateTime(item.blocked_at) },
            }),
        );
        row.appendChild(el("td", { text: item.jail || "—" }));
        row.appendChild(el("td", { text: item.source || "—" }));

        const statusCell = el("td");
        const blocked = String(item.status || "").toLowerCase() === "blocked";
        statusCell.appendChild(
            makeBadge(blocked ? "success" : "neutral", blocked ? "Blocked" : capitalize(item.status)),
        );
        row.appendChild(statusCell);
        tbody.appendChild(row);
    });

    setHidden(root.querySelector(".table-wrap"), items.length === 0);
    setEmptyState(
        root,
        items.length === 0,
        section?.status === "error" ? "Gagal memuat daftar IP" : "Belum ada IP yang diblokir",
        section?.error || "Daftar ini hanya memuat status yang dikonfirmasi Fail2Ban.",
    );
}
