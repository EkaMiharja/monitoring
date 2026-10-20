import { createChart, destroyChart, updateChart } from "../charts.js";
import { formatDateTime, formatNumber, formatTime, toNumber } from "../format.js";
import { setChartState, updatePanelMeta } from "../ui.js";

const METRICS = [
    { key: "delay", label: "Delay", unit: "ms", color: "#38bdf8" },
    { key: "jitter", label: "Jitter", unit: "ms", color: "#a78bfa" },
    { key: "packet_loss", label: "Packet Loss", unit: "%", color: "#fb7185" },
    { key: "throughput", label: "Throughput", unit: "Mbps", color: "#34d399" },
];

const charts = new Map();

function updateMetricCard(root, config, metric) {
    const card = root?.querySelector(`[data-metric="${config.key}"]`);
    if (!card) return;

    const series = (metric?.series || []).filter((point) => point && point.t);
    const stats = metric?.stats || {};
    const current = series.length ? toNumber(series[series.length - 1].value) : null;

    card.querySelector("[data-value]").textContent =
        current === null ? "—" : formatNumber(current, 2);
    card.querySelector('[data-stat="min"]').textContent = formatNumber(stats.min, 2);
    card.querySelector('[data-stat="max"]').textContent = formatNumber(stats.max, 2);
    card.querySelector('[data-stat="avg"]').textContent = formatNumber(stats.avg, 2);

    const errorNode = card.querySelector("[data-metric-error]");
    if (errorNode) {
        const showError =
            series.length === 0 &&
            Boolean(metric?.error) &&
            ["error", "unavailable"].includes(metric?.status);
        errorNode.textContent = showError ? metric.error : "";
        errorNode.hidden = !showError;
    }

    if (series.length === 0) {
        destroyChart(charts.get(config.key));
        charts.delete(config.key);
        setChartState(card, metric, true);
        return;
    }

    setChartState(card, metric, false);
    const labels = series.map((point) => formatTime(point.t));
    const datasets = [
        {
            label: config.label,
            data: series.map((point) => toNumber(point.value)),
            color: config.color,
            fill: true,
        },
    ];

    const canvas = card.querySelector("canvas");
    if (!charts.has(config.key)) charts.set(config.key, createChart(canvas, datasets, config.unit));
    updateChart(charts.get(config.key), labels, datasets, config.unit);
}

function updateTestMetadata(root, test) {
    const node = root?.querySelector("[data-qos-test]");
    if (root) root.dataset.qosStatus = test?.status || "";
    if (!node) return;
    if (!test) {
        node.textContent = "Metadata tes: —";
        return;
    }

    const parts = [
        test.protocol || "—",
        test.direction || "—",
        `${test.client || "—"} → ${test.server || "—"}`,
        test.duration_seconds ? `${test.duration_seconds}s` : "—",
        `status ${test.status || "—"}`,
        test.timestamp ? formatDateTime(test.timestamp) : "timestamp belum tersedia",
    ];
    node.textContent = `Metadata tes: ${parts.join(" · ")}`;
}

function updateDelayMetadata(root, test) {
    const node = root?.querySelector("[data-qos-delay]");
    if (!node) return;
    if (!test) {
        node.textContent = "Pengukuran delay: —";
        return;
    }

    const parts = [
        test.method || "ICMP",
        test.target || "—",
        test.count ? `${test.count} paket` : "—",
        test.delay_ms !== null && test.delay_ms !== undefined
            ? `${formatNumber(test.delay_ms, 2)} ms`
            : "—",
        `status ${test.status || "—"}`,
        test.timestamp ? formatDateTime(test.timestamp) : "timestamp belum tersedia",
    ];
    node.textContent = `Pengukuran delay: ${parts.join(" · ")}`;
}

export function updateQos(section) {
    const root = updatePanelMeta("qos", section);
    const metrics = section?.metrics || {};
    METRICS.forEach((config) => updateMetricCard(root, config, metrics[config.key] || {}));
    updateTestMetadata(root, section?.test);
    updateDelayMetadata(root, section?.delay_test);
}
