import { clear, el, makeStatusLabel, setHidden } from "../dom.js";
import { formatDateTime, formatNumber } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

const PAGE_SIZE = 30;

let items = [];
let modelFilter = "";
let currentPage = 1;

function predictionTone(value) {
    const text = String(value || "").toLowerCase();
    if (["bruteforce", "brute force", "attack", "malicious", "serangan"].some((word) => text.includes(word))) {
        return "danger";
    }
    if (["benign", "normal", "safe"].some((word) => text.includes(word))) {
        return "success";
    }
    return "neutral";
}

function valueOrDash(value) {
    return value === null || value === undefined || value === "" ? "—" : String(value);
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
    const select = root.querySelector("#detection-model-filter");
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
    if (!modelFilter) return items;
    return items.filter((item) => String(item.model || "").trim() === modelFilter);
}

function renderPagination(root, totalPages) {
    const nav = root.querySelector("[data-detection-pagination]");
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

    const windowSize = Math.min(3, totalPages);
    let startPage = Math.floor((currentPage - 1) / windowSize) * windowSize + 1;
    let endPage = startPage + windowSize - 1;
    if (endPage > totalPages) {
        endPage = totalPages;
        startPage = Math.max(1, endPage - windowSize + 1);
    }

    for (let page = startPage; page <= endPage; page += 1) {
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
    const root = document.querySelector('[data-panel="detections"]');
    const tbody = root?.querySelector("[data-detection-rows]");
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
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.id) }));
        row.appendChild(el("td", { text: formatDateTime(item.detected_at) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.src_ip) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.dst_ip) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.src_port) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.dst_port) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.protocol) }));
        row.appendChild(
            el("td", { className: "mono", text: valueOrDash(item.prediction) }),
        );

        const predictionCell = row.lastChild;
        clear(predictionCell);
        predictionCell.appendChild(
            makeStatusLabel(predictionTone(item.prediction), item.prediction || "—"),
        );

        row.appendChild(
            el("td", { className: "mono", text: formatNumber(item.attack_probability, 4) }),
        );
        row.appendChild(
            el("td", { className: "mono", text: formatNumber(item.confidence, 4) }),
        );
        row.appendChild(el("td", { text: valueOrDash(item.model) }));
        row.appendChild(el("td", { className: "mono", text: valueOrDash(item.status) }));
        tbody.appendChild(row);
    });

    let counterText = "0 baris";
    if (filtered.length > 0) {
        const endIndex = startIndex + visibleItems.length;
        counterText = `${startIndex + 1}–${endIndex} dari ${filtered.length} baris`;
    } else if (items.length > 0) {
        counterText = `0 dari ${items.length} baris`;
    }

    const counter = root.querySelector("[data-detection-count]");
    if (counter && counter.textContent !== counterText) {
        counter.textContent = counterText;
    }

    renderPagination(root, totalPages);
    setHidden(root.querySelector(".table-wrap"), filtered.length === 0);
    setEmptyState(
        root,
        filtered.length === 0,
        items.length === 0 ? "Belum ada log deteksi" : "Tidak ada hasil untuk model ini",
    );
}

export function initDetections() {
    const root = document.querySelector('[data-panel="detections"]');
    if (!root) return;

    const select = root.querySelector("#detection-model-filter");
    if (select) {
        select.addEventListener("change", () => {
            modelFilter = select.value;
            currentPage = 1;
            render();
        });
    }

    const pagination = root.querySelector("[data-detection-pagination]");
    if (pagination) {
        pagination.addEventListener("click", (event) => {
            const button = event.target.closest("[data-page]");
            if (!button || button.disabled) return;
            const page = Number.parseInt(button.dataset.page, 10);
            if (!Number.isInteger(page) || page < 1) return;
            currentPage = page;
            render();
            root.querySelector('[data-detection-pagination] [aria-current="page"]')?.focus({
                preventScroll: true,
            });
        });
    }
}

export function updateDetections(section) {
    updatePanelMeta("detections", section);
    items = Array.isArray(section?.items) ? section.items : [];
    render();
}
