import { createChart, destroyChart, updateChart } from "../charts.js";
import { clear, el, setHidden, setText } from "../dom.js";
import { formatDateTime, formatShortTime, toNumber } from "../format.js";
import { setChartState, updatePanelMeta } from "../ui.js";

let chart = null;
let chartMode = "";
let featureSection = null;
let featureRoot = null;
let selectedFeature = "";

const featureFormatter = new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: 3,
});

function formatFeatureValue(value) {
    const number = toNumber(value);
    if (number === null) return "—";
    const absolute = Math.abs(number);
    if (absolute !== 0 && (absolute < 0.001 || absolute >= 1e9)) {
        return number.toExponential(3);
    }
    return featureFormatter.format(number);
}

function formatDelta(value) {
    const number = toNumber(value);
    if (number === null) return "—";
    if (number > 0) return `+${formatFeatureValue(number)}`;
    return formatFeatureValue(number);
}

function syncFeatureOptions(select, features, preferred) {
    const names = features.map((feature) => feature?.name).filter(Boolean);
    const existing = Array.from(select.options).map((option) => option.value);
    const changed =
        names.length !== existing.length ||
        names.some((name, index) => name !== existing[index]);

    if (changed) {
        clear(select);
        names.forEach((name) => {
            select.appendChild(el("option", { text: name, attrs: { value: name } }));
        });
    }

    const selected = names.includes(preferred) ? preferred : names[0] || "";
    select.value = selected;
    select.disabled = names.length === 0;
    return selected;
}

function featureWithData(features) {
    return features.find(
        (feature) => Array.isArray(feature?.series) && feature.series.length > 0,
    );
}

function renderFeatureChart() {
    if (!featureRoot || !featureSection) return;

    const features = Array.isArray(featureSection.features) ? featureSection.features : [];
    const select = featureRoot.querySelector("[data-feature-select]");
    const chartWrap = featureRoot.querySelector("[data-traffic-chart]");
    const empty = featureRoot.querySelector("[data-feature-empty]");
    const emptyText = empty?.querySelector(".empty-state__text");
    const currentNode = featureRoot.querySelector("[data-feature-current]");
    const deltaNode = featureRoot.querySelector("[data-feature-delta]");
    const canvas = document.getElementById("traffic-chart");
    const feature =
        features.find((item) => item?.name === selectedFeature) ||
        featureWithData(features) ||
        features[0] ||
        null;
    const points = Array.isArray(feature?.series) ? feature.series : [];
    const delta = toNumber(feature?.delta);

    if (feature?.name) {
        selectedFeature = feature.name;
        if (select.value !== feature.name) select.value = feature.name;
    }

    setText(currentNode, formatFeatureValue(feature?.current));
    setText(deltaNode, formatDelta(delta));
    const deltaStat = deltaNode?.closest(".flow-stat");
    if (deltaStat) {
        deltaStat.classList.toggle("is-up", delta !== null && delta > 0);
        deltaStat.classList.toggle("is-down", delta !== null && delta < 0);
    }

    const hasData = Boolean(featureWithData(features));
    const hasPoints = points.length > 0;
    setHidden(chartWrap, !hasData || !hasPoints);
    setHidden(empty, !hasData || hasPoints);

    if (!hasData || !hasPoints) {
        destroyChart(chart);
        chart = null;
        chartMode = "";
        if (!hasData) {
            setText(emptyText, "Fitur muncul setelah worker memproses autentikasi SSH.");
        } else {
            setText(emptyText, "Fitur ini belum memiliki sampel pada jendela data saat ini.");
        }
        return;
    }

    const labels = points.map((point) => formatShortTime(point?.t));
    const datasets = [
        {
            label: feature?.name || "Fitur",
            data: points.map((point) => toNumber(point?.value)),
            color: "#1f3a5f",
            fill: true,
        },
    ];

    const mode = `feature:${feature?.name || ""}`;
    if (!chart || chartMode !== mode) {
        destroyChart(chart);
        chart = createChart(canvas, datasets, "");
        chartMode = chart ? mode : "";
    }
    updateChart(chart, labels, datasets, "");
    if (canvas) {
        canvas.setAttribute(
            "aria-label",
            `Grafik perubahan ${feature?.name || "fitur network flow"}`,
        );
    }
}

function renderFeaturePanel(root, section) {
    featureRoot = root;
    featureSection = section;

    const container = root.querySelector("[data-flow-features]");
    const legend = root.querySelector("[data-traffic-legend]");
    const select = root.querySelector("[data-feature-select]");
    const features = Array.isArray(section?.features) ? section.features : [];
    const sample = section?.sample || {};

    setHidden(container, false);
    setHidden(legend, true);

    setText(root.querySelector("[data-flow-time]"), formatDateTime(sample.detected_at));
    setText(root.querySelector("[data-flow-source]"), sample.source_ip || "—");
    setText(root.querySelector("[data-flow-target]"), sample.target || "—");
    setText(root.querySelector("[data-flow-auth]"), sample.auth_result || "—");

    const fallback = features.find((feature) => feature?.name)?.name || "";
    selectedFeature = syncFeatureOptions(
        select,
        features,
        selectedFeature || featureWithData(features)?.name || fallback,
    );
    select.onchange = () => {
        selectedFeature = select.value;
        renderFeatureChart();
    };

    renderFeatureChart();
}

function renderDemoPanel(root, section) {
    featureRoot = null;
    featureSection = null;

    const container = root?.querySelector("[data-flow-features]");
    const chartWrap = root?.querySelector("[data-traffic-chart]");
    const legend = root?.querySelector("[data-traffic-legend]");
    setHidden(container, true);
    setHidden(legend, false);

    const series = (section?.series || []).filter((point) => point && point.t);

    if (series.length === 0) {
        setHidden(chartWrap, false);
        destroyChart(chart);
        chart = null;
        chartMode = "";
        setChartState(root, section, true);
        return;
    }

    setHidden(chartWrap, false);
    setChartState(root, section, false);
    const labels = series.map((point) => formatShortTime(point.t));
    const datasets = [
        {
            label: "Inbound",
            data: series.map((point) => toNumber(point.inbound)),
            color: "#1f3a5f",
            fill: true,
        },
        {
            label: "Outbound",
            data: series.map((point) => toNumber(point.outbound)),
            color: "#7a520f",
            fill: false,
        },
    ];

    const canvas = document.getElementById("traffic-chart");
    if (!chart || chartMode !== "demo") {
        destroyChart(chart);
        chart = createChart(canvas, datasets, "Mbps");
        chartMode = chart ? "demo" : "";
    }
    updateChart(chart, labels, datasets, "Mbps");
}

export function updateTraffic(section) {
    const root = updatePanelMeta("traffic", section);
    if (!root) return;

    if (Array.isArray(section?.features)) {
        renderFeaturePanel(root, section);
        return;
    }

    renderDemoPanel(root, section);
}
