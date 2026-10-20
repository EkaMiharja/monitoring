export class Poller {
    constructor({ intervalMs, onTick, onError }) {
        this.intervalMs = Math.max(Number(intervalMs) || 5000, 1000);
        this.onTick = onTick;
        this.onError = onError;
        this.running = false;
        this.inFlight = false;
        this.timer = null;
        this.controller = null;
    }

    start() {
        if (this.running) return;
        this.running = true;
        this._schedule(0);
    }

    stop() {
        this.running = false;
        clearTimeout(this.timer);
        this.timer = null;
        if (this.controller) {
            this.controller.abort();
            this.controller = null;
        }
    }

    refresh() {
        if (!this.running) return Promise.resolve();
        clearTimeout(this.timer);
        this.timer = null;
        return this._run();
    }

    _schedule(delay) {
        clearTimeout(this.timer);
        if (!this.running) return;
        this.timer = setTimeout(() => this._run(), delay);
    }

    async _run() {
        if (!this.running || this.inFlight) return;
        this.inFlight = true;
        this.controller = new AbortController();
        try {
            await this.onTick(this.controller.signal);
        } catch (error) {
            if (error?.name !== "AbortError") this.onError(error);
        } finally {
            this.inFlight = false;
            this.controller = null;
            if (this.running) this._schedule(this.intervalMs);
        }
    }
}
