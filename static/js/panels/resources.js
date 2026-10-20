import { createChart, destroyChart, updateChart } from "../charts.js";
import { applyBadge, setHidden } from "../dom.js";
import { formatNumber, formatTime, toNumber } from "../format.js";
import { setEmptyState, updatePanelMeta } from "../ui.js";

const charts = new Map();

function chartKey(host, metric) {
    return `${host}::${metric}`;
}

function updateMetricBlock(card, host, key, color) {
    const metric = host[key] || {};
    const series = (metric.series || []).filter((point) => point && point.t);
    const stats = metric.stats || {};
    const current = series.length ? toNumber(series[series.length - 1].value) : null;

    card.querySelector(`[data-${key}-value]`).textContent =
        current === null ? "—" : formatNumber(current, 1);
    ["min", "max", "avg"].forEach((stat) => {
        const node = card.querySelector(`[data-${key}-stat="${stat}"]`);
        if (node) node.textContent = formatNumber(stats[stat], 1);
    });

    const mapKey = chartKey(host.host, key);
    if (series.length === 0) {
        destroyChart(charts.get(mapKey));
        charts.delete(mapKey);
        return;
    }

    const labels = series.map((point) => formatTime(point.t));
    const datasets = [
        {
            label: key === "cpu" ? "CPU" : "Memory",
            data: series.map((point) => toNumber(point.value)),
            color,
            fill: true,
        },
    ];
    const canvas = card.querySelector(`[data-${key}-chart]`);
    if (!charts.has(mapKey)) charts.set(mapKey, createChart(canvas, datasets, "%"));
    updateChart(charts.get(mapKey), labels, datasets, "%");
}

function updateHostCard(card, host) {
    const hostName = String(host.host || "unknown");
    card.dataset.host = hostName;
    card.querySelector("[data-host-name]").textContent = hostName;

    const badge = card.querySelector("[data-host-status]");
    applyBadge(badge, host.status || "unavailable");
    const badgeText = badge?.querySelector("span:last-child");
    if (badgeText) {
        badgeText.textContent =
            host.status === "ok"
                ? "Live"
                : host.status === "empty"
                  ? "Kosong"
                  : host.status === "error"
                    ? "Error"
                    : "Tidak tersedia";
    }

    const errorNode = card.querySelector("[data-host-error]");
    if (errorNode) {
        const visible = Boolean(host.error) && host.status !== "ok";
        errorNode.textContent = host.error || "";
        setHidden(errorNode, !visible);
    }

    card.classList.toggle("host-card--unavailable", host.status !== "ok");
    updateMetricBlock(card, host, "cpu", "#38bdf8");
    updateMetricBlock(card, host, "memory", "#fbbf24");
}

export function updateResources(section) {
    const root = updatePanelMeta("resources", section);
    const container = root?.querySelector("[data-hosts]");
    const template = document.getElementById("host-card-template");
    if (!container || !template) return;

    const hosts = section?.hosts || [];
    const existing = new Map(
        Array.from(container.querySelectorAll(".host-card")).map((card) => [card.dataset.host, card]),
    );
    const seen = new Set();

    hosts.forEach((host) => {
        const name = String(host.host || "unknown");
        seen.add(name);
        let card = existing.get(name);
        if (!card) {
            card = template.content.firstElementChild.cloneNode(true);
            card.dataset.host = name;
            container.appendChild(card);
        }
        updateHostCard(card, host);
    });

    existing.forEach((card, name) => {
        if (seen.has(name)) return;
        ["cpu", "memory"].forEach((metric) => {
            const key = chartKey(name, metric);
            destroyChart(charts.get(key));
            charts.delete(key);
        });
        card.remove();
    });

    setEmptyState(
        root,
        hosts.length === 0,
        "Belum ada host yang dipantau",
        section?.error || "Konfigurasi URL Glances untuk setiap VM pada backend.",
    );
}
