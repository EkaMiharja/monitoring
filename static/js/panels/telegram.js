import { clear, el, makeBadge, setHidden } from "../dom.js";
import { capitalize, formatDateTime, formatShortTime } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

const STATUS_LABELS = {
    delivered: "Terkirim",
    failed: "Gagal",
    pending: "Menunggu",
    unavailable: "Tidak tersedia",
};

function statusText(status) {
    return STATUS_LABELS[status] || capitalize(status);
}

function renderItem(item) {
    const entry = el("li", { className: "alert-item" });

    const head = el("div", { className: "alert-item__head" });
    head.appendChild(el("span", { className: "alert-item__event", text: item.event || "Notifikasi" }));
    head.appendChild(makeBadge(item.status || "pending", statusText(item.status)));
    entry.appendChild(head);

    const meta = el("div", { className: "alert-item__meta" });
    meta.appendChild(el("span", { className: "mono", text: item.source_ip || "—" }));
    meta.appendChild(
        el("span", {
            text: formatShortTime(item.timestamp),
            attrs: { title: formatDateTime(item.timestamp) },
        }),
    );
    entry.appendChild(meta);

    entry.appendChild(el("p", { className: "alert-item__detail", text: item.detail || "—" }));
    return entry;
}

export function updateTelegram(section) {
    const root = updatePanelMeta("telegram", section);
    const list = root?.querySelector("[data-telegram-list]");
    if (!list) return;

    clear(list);
    const items = section?.items || [];
    const delivered = items.filter((item) => item.status === "delivered").length;
    const failed = items.filter((item) => item.status === "failed").length;

    items.forEach((item) => list.appendChild(renderItem(item)));

    const lastNode = root.querySelector("[data-telegram-last]");
    if (lastNode) lastNode.textContent = items.length ? statusText(items[0].status) : "—";
    const deliveredNode = root.querySelector("[data-telegram-delivered]");
    if (deliveredNode) deliveredNode.textContent = String(delivered);
    const failedNode = root.querySelector("[data-telegram-failed]");
    if (failedNode) failedNode.textContent = String(failed);

    setHidden(list, items.length === 0);
    setEmptyState(
        root,
        items.length === 0,
        section?.status === "error" ? "Gagal memuat riwayat Telegram" : "Belum ada riwayat notifikasi",
        section?.error || "Riwayat akan muncul setelah backend mencatat pengiriman alert.",
    );
}
