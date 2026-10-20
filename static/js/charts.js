import { formatNumber } from "./format.js";

const TICK_COLOR = "#6f819e";
const GRID_COLOR = "rgba(148, 166, 194, 0.10)";

function withAlpha(hex, alpha) {
    const value = hex.replace("#", "");
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function options(datasets, unit) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
            legend: {
                display: datasets.length > 1,
                labels: {
                    color: "#94a6c2",
                    boxWidth: 14,
                    boxHeight: 3,
                    font: { size: 10 },
                },
            },
            tooltip: {
                backgroundColor: "#0b1220",
                borderColor: "#2f4363",
                borderWidth: 1,
                titleColor: "#e8eefb",
                bodyColor: "#94a6c2",
                padding: 10,
                callbacks: {
                    label(context) {
                        const label = context.dataset.label ? `${context.dataset.label}: ` : "";
                        const value = formatNumber(context.parsed.y);
                        return `${label}${unit ? `${value} ${unit}` : value}`;
                    },
                },
            },
        },
        scales: {
            x: {
                grid: { display: false },
                border: { display: false },
                ticks: {
                    color: TICK_COLOR,
                    maxTicksLimit: 6,
                    maxRotation: 0,
                    autoSkip: true,
                    font: { size: 10 },
                },
            },
            y: {
                beginAtZero: false,
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: {
                    color: TICK_COLOR,
                    maxTicksLimit: 5,
                    font: { size: 10 },
                    callback: (value) => formatNumber(value, 1),
                },
            },
        },
        elements: {
            point: { radius: 0, hitRadius: 8, hoverRadius: 2 },
            line: { tension: 0.32, borderWidth: 2 },
        },
    };
}

export function createChart(canvas, datasets, unit) {
    if (!window.Chart || !canvas) return null;
    const prepared = datasets.map((dataset) => ({
        label: dataset.label,
        data: dataset.data,
        borderColor: dataset.color,
        backgroundColor: dataset.fill ? withAlpha(dataset.color, 0.14) : dataset.color,
        fill: Boolean(dataset.fill),
        borderWidth: 2,
    }));

    return new window.Chart(canvas.getContext("2d"), {
        type: "line",
        data: { labels: [], datasets: prepared },
        options: options(prepared, unit),
    });
}

export function updateChart(chart, labels, datasets, unit) {
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets.forEach((dataset, index) => {
        dataset.data = datasets[index]?.data || [];
    });
    if (chart.options.plugins?.tooltip?.callbacks) {
        chart.options.plugins.tooltip.callbacks.label = (context) => {
            const label = context.dataset.label ? `${context.dataset.label}: ` : "";
            const value = formatNumber(context.parsed.y);
            return `${label}${unit ? `${value} ${unit}` : value}`;
        };
    }
    chart.update("none");
}

export function destroyChart(chart) {
    if (chart) chart.destroy();
}
