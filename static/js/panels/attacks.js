import { clear, debounce, el, makeBadge, setHidden } from "../dom.js";
import { formatDateTime, formatShortTime } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

const PAGE_SIZE = 20;

let items = [];
let query = "";
let modelFilter = "";
let currentPage = 1;

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

function modelsInUse() {
    const models = new Set();
    items.forEach((item) => {
        const model = String(item.model || "").trim();
        if (model) models.add(model);
    });
    return [...models].sort((left, right) => left.localeCompare(right));
}

function syncModelFilter(root) {
    const select = root.querySelector("#attack-model-filter");
    if (!select) return;

    const models = modelsInUse();
    if (modelFilter && !models.includes(modelFilter)) {
        modelFilter = "";
        currentPage = 1;
    }

    const signature = JSON.stringify(models);
    if (select.dataset.options !== signature) {
        clear(select);
        select.appendChild(el("option", { attrs: { value: "" }, text: "Semua model" }));
        models.forEach((model) => {
            select.appendChild(el("option", { attrs: { value: model }, text: model }));
        });
        select.dataset.options = signature;
    }

    if (select.value !== modelFilter) select.value = modelFilter;
}

function filteredItems() {
    const normalized = query.toLowerCase();
    return items.filter((item) => {
        if (modelFilter && String(item.model || "").trim() !== modelFilter) return false;
        if (!normalized) return true;
        return [item.source_ip, item.attack_type, item.model, item.detection, item.target]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(normalized));
    });
}

function renderPagination(root, totalPages) {
    const nav = root.querySelector("[data-attack-pagination]");
    if (!nav) return;

    clear(nav);
    if (totalPages <= 1) {
        setHidden(nav, true);
        return;
    }

    setHidden(nav, false);

    const addButton = (
        label,
        page,
        { current = false, disabled = false, navLabel = "", isNav = false } = {},
    ) => {
        const button = el("button", {
            className: isNav
                ? "pagination__button pagination__button--nav"
                : "pagination__button",
            text: label,
            attrs: { type: "button", "data-page": String(page) },
        });
        if (navLabel) button.setAttribute("aria-label", navLabel);
        if (current) button.setAttribute("aria-current", "page");
        if (disabled) button.disabled = true;
        nav.appendChild(button);
    };

    addButton("‹", currentPage - 1, {
        disabled: currentPage <= 1,
        navLabel: "Halaman sebelumnya",
        isNav: true,
    });
    for (let page = 1; page <= totalPages; page += 1) {
        addButton(String(page), page, {
            current: page === currentPage,
            navLabel: `Halaman ${page}`,
        });
    }
    addButton("›", currentPage + 1, {
        disabled: currentPage >= totalPages,
        navLabel: "Halaman berikutnya",
        isNav: true,
    });
}

function render() {
    const root = document.querySelector('[data-panel="attacks"]');
    const tbody = root?.querySelector("[data-attack-rows]");
    if (!root || !tbody) return;

    syncModelFilter(root);

    const filtered = filteredItems();
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    currentPage = Math.min(Math.max(currentPage, 1), totalPages);

    const startIndex = (currentPage - 1) * PAGE_SIZE;
    const visibleItems = filtered.slice(startIndex, startIndex + PAGE_SIZE);

    clear(tbody);
    visibleItems.forEach((item) => {
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

    const hasFilters = Boolean(query || modelFilter);
    let counterText = "0 kejadian";
    if (filtered.length > 0) {
        const endIndex = startIndex + visibleItems.length;
        counterText = `${startIndex + 1}–${endIndex} dari ${filtered.length} ${
            hasFilters ? "hasil" : "kejadian"
        }`;
    } else if (hasFilters) {
        counterText = `0 dari ${items.length} hasil`;
    }

    const counter = root.querySelector("[data-attack-count]");
    if (counter && counter.textContent !== counterText) {
        counter.textContent = counterText;
    }

    renderPagination(root, totalPages);
    setHidden(root.querySelector(".table-wrap"), filtered.length === 0);
    setEmptyState(
        root,
        filtered.length === 0,
        items.length === 0 ? "Belum ada riwayat serangan" : "Tidak ada hasil yang cocok",
        items.length === 0
            ? "Riwayat akan muncul ketika backend menyediakan data deteksi."
            : "Ubah kata kunci atau pilih model lain.",
    );
}

export function initAttacks() {
    const root = document.querySelector('[data-panel="attacks"]');
    if (!root) return;

    const input = root.querySelector("#attack-filter");
    if (input) {
        input.addEventListener(
            "input",
            debounce(() => {
                query = input.value.trim();
                currentPage = 1;
                render();
            }),
        );
    }

    const select = root.querySelector("#attack-model-filter");
    if (select) {
        select.addEventListener("change", () => {
            modelFilter = select.value;
            currentPage = 1;
            render();
        });
    }

    const pagination = root.querySelector("[data-attack-pagination]");
    if (pagination) {
        pagination.addEventListener("click", (event) => {
            const button = event.target.closest("[data-page]");
            if (!button || button.disabled) return;
            const page = Number.parseInt(button.dataset.page, 10);
            if (!Number.isInteger(page) || page < 1) return;
            currentPage = page;
            render();
            root.querySelector('[data-attack-pagination] [aria-current="page"]')?.focus({
                preventScroll: true,
            });
        });
    }
}

export function updateAttacks(section) {
    updatePanelMeta("attacks", section);
    items = Array.isArray(section?.items) ? section.items : [];
    render();
}
