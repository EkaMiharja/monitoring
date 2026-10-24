import { formatNumber } from "./format.js";

const TICK_COLOR = "#8a8a8a";
const GRID_COLOR = "rgba(255, 255, 255, 0.07)";
const DATA_FONT = "'Montserrat', 'Segoe UI', sans-serif";

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
                    color: "#b3b3b3",
                    boxWidth: 14,
                    boxHeight: 3,
                    font: { size: 10 },
                },
            },
            tooltip: {
                backgroundColor: "#282828",
                borderColor: "rgba(255, 255, 255, 0.12)",
                borderWidth: 1,
                titleColor: "#ffffff",
                bodyColor: "#b3b3b3",
                padding: 10,
                titleFont: { family: DATA_FONT, size: 11, weight: "500" },
                bodyFont: { family: DATA_FONT, size: 11 },
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
                    font: { family: DATA_FONT, size: 10 },
                },
            },
            y: {
                beginAtZero: false,
                grid: { color: GRID_COLOR },
                border: { display: false },
                ticks: {
                    color: TICK_COLOR,
                    maxTicksLimit: 5,
                    font: { family: DATA_FONT, size: 10 },
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
        backgroundColor: dataset.fill ? withAlpha(dataset.color, 0.08) : dataset.color,
        fill: Boolean(dataset.fill),
        borderWidth: 2,
        pointRadius: dataset.pointRadius ?? 0,
        pointHoverRadius: dataset.pointHoverRadius ?? 2,
        pointBackgroundColor: dataset.color,
        pointBorderColor: dataset.color,
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
        const next = datasets[index];
        dataset.data = next?.data || [];
        if (next?.pointRadius !== undefined) dataset.pointRadius = next.pointRadius;
        if (next?.pointHoverRadius !== undefined) dataset.pointHoverRadius = next.pointHoverRadius;
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
