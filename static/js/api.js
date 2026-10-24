export async function fetchOverview({ vm, range, signal } = {}) {
    const params = new URLSearchParams();
    if (vm) params.set("vm", vm);
    if (range) params.set("range", range);
    const query = params.toString() ? `?${params.toString()}` : "";
    let response;
    try {
        response = await fetch(`/api/overview${query}`, {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
            cache: "no-store",
            signal,
        });
    } catch (error) {
        if (error.name === "AbortError") throw error;
        throw new Error("Backend tidak dapat dijangkau.");
    }

    if (response.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent("/dashboard")}`);
        throw new Error("Sesi berakhir. Silakan login kembali.");
    }

    let payload = null;
    try {
        payload = await response.json();
    } catch {
        throw new Error("Respons backend bukan JSON yang valid.");
    }

    if (!response.ok) {
        throw new Error(payload?.message || `Permintaan gagal (HTTP ${response.status}).`);
    }
    return payload;
}

export async function sendTelegramTest() {
    const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
    const response = await fetch("/api/telegram/test", {
        method: "POST",
        headers: {
            Accept: "application/json",
            "X-CSRF-Token": token,
        },
        credentials: "same-origin",
    });

    let payload = null;
    try {
        payload = await response.json();
    } catch {
        payload = null;
    }

    if (!response.ok) {
        throw new Error(payload?.message || `Test alert gagal (HTTP ${response.status}).`);
    }
    return payload;
}

async function postAction(url, fallbackMessage) {
    const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
    let response;
    try {
        response = await fetch(url, {
            method: "POST",
            headers: {
                Accept: "application/json",
                "X-CSRF-Token": token,
            },
            credentials: "same-origin",
        });
    } catch {
        throw new Error("Backend tidak dapat dijangkau.");
    }

    let payload = null;
    try {
        payload = await response.json();
    } catch {
        payload = null;
    }

    if (!response.ok) {
        throw new Error(payload?.message || `${fallbackMessage} (HTTP ${response.status}).`);
    }
    return payload;
}
