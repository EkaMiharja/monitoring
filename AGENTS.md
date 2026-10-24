# AGENTS.md

Flask dashboard for SSH brute-force monitoring (Windows laptop, WSL working dir). Indonesian-language UI copy.

## Commands

```bash
# venv lives in the Windows tree; run it from WSL via the Scripts/ entrypoint
/mnt/c/Users/eka/PycharmProjects/Dashboard/.venv/Scripts/python.exe -m pytest -q
/mnt/c/Users/eka/PycharmProjects/Dashboard/.venv/Scripts/python.exe app.py   # port 5000
```

- No linter/formatter/typechecker config exists — `pytest` is the only gate. Suite: 119 tests.
- If pytest fails with `PermissionError` on `%TEMP%\pytest-of-*`, pass `--basetemp=C:\Users\eka\PycharmProjects\Dashboard\.pytest_tmp` (delete it after).
- Single test: `... -m pytest tests/test_api.py::test_name -q`.
- `requirements.txt` = Flask, requests, python-dotenv, pytest only. `playwright` is also present in `.venv` (not in requirements) and works for screenshots via `p.chromium.launch(channel="chrome")`.
- Headless Chrome CLI (`chrome.exe --screenshot`) silently produces nothing from WSL — use Playwright instead.

## Config & runtime

- `config.py` loads `.env` at import; `DATA_MODE=demo` → `MockProvider`, `live` → `LiveProvider` (chosen in `app.py`).
- `DATA_MODE` and every source URL live in `.env`; `.env.example` documents all of them. Never commit `.env`.
- `TELEGRAM_BLOCK_NOTIFY_ENABLED=true` enables automatic block/unblock notifications; `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required. The notifier has no polling loop of its own — it only observes `/api/overview` polls.
- Live mode accesses three VMs directly over the same Wi-Fi/LAN (no Tailscale/SSH tunnel). `VM_HOST`, `RF_VM_HOST`, and `FAIL2BAN_VM_HOST` in `.env` are the only per-VM IPs (all URLs use those variables); the laptop IP is never configured, so a DHCP change needs at most one line. QoS probes stay in-VM over host-only `192.168.56.0/24` (`QOS_SOURCE_MODE=vm`, `QOS_LOCAL_PROBE=false`); packet loss comes from ICMP ping (10 pings @0.2 s), jitter from iperf3 UDP. `ufw` is disabled on all three VMs (allow all), so IP/subnet changes need no firewall edits.
- Sources are often absent. Missing data must surface as honest `unavailable`/`error` section status — never fabricate per-VM numbers.
- Chart retention: `HISTORY_MAX_POINTS=900` for resource/traffic buffers, `QOS_HISTORY_POINTS=480` for manual QoS runners; the in-VM probe keeps 480 points (~80 min @10 s). The 1-hour view needs ~1 hour of dashboard uptime for in-memory resource/flow buffers; QoS backfills from VM history.

## API contract (do not change silently)

- `GET /api/overview?vm=<id>&range=5m|30m|1h` — sections: `traffic, qos, resources, blocked_ips, attacks, telegram`; response also carries `vm`, `qos_vm`, `generated_at`, `data_mode`, `poll_interval_ms`, `range`, `stats_window_seconds`, `errors[]`. `traffic` is event-based: if no event is inside the range it falls back to the latest events within the same-sized window before the newest event (max 50), sets `range_empty`/`fallback_used`, and appends `event terakhir di luar rentang` to `source`.
- Unknown `vm` → HTTP 400 `invalid_vm`; invalid `range` → HTTP 400 `invalid_range`. Omitting `vm` keeps the legacy payload (`resources.hosts` length 3). Omitting `range` defaults to `5m`.
- State-changing endpoints (`/api/telegram/test`, `/api/iperf3/run`, `/api/delay/run`, auth routes) require session + CSRF (`security.csrf_protect`).
- `VM_SPECS` in `config.py` is the single source for VM ids/labels/capabilities. `fail2ban-vm` has `traffic: False` and is resource + QoS only; `QOS_VMS` controls which VMs have QoS, with targets from `VM_HOST` / `RF_VM_HOST` / `FAIL2BAN_VM_HOST`.
- Fail2Ban's own VM exposes `GET /api/blocked`, `GET /api/attacks?limit=50`, and `GET /api/qos` on port 8080 (Bearer `FAIL2BAN_API_TOKEN`); `/api/attacks` parses `fail2ban.log` Ban/Unban events (separate row per Ban, `blocking_status` from the latest event), and QoS history comes from the in-VM `qos_probe` timer.
- `blocked_ips` merges LightGBM `GET /api/blocked` (`LIGHTGBM_BLOCKED_API_URL`, Bearer `LIGHTGBM_API_TOKEN` fallback `FLOW_FEATURES_LIGHTGBM_TOKEN`), Random Forest `/api/blocked` (`RANDOM_FOREST_BLOCKED_API_URL`, Bearer `RANDOM_FOREST_API_TOKEN` fallback `FLOW_FEATURES_RANDOM_FOREST_TOKEN` then `ATTACK_HISTORY_API_TOKEN`), and Fail2Ban `/api/blocked`. Duplicate IPs are deduped with source labels such as `LightGBM + Random Forest + Fail2Ban`; `unblock_at`/`remaining_seconds` drive the countdown, and a missing `unblock_at` means manual/permanent. If one source fails, the others stay visible and `warnings` is populated. The section also carries `total` and `truncated` because `items` is capped at 50.
- Telegram block/unblock alerts are request-driven: the first valid `blocked_ips` snapshot is a silent baseline, new IPs notify, and unblocks notify only after the IP is absent from every source. `warnings`/`truncated` hold unblocks to avoid false positives; sends run on a queue worker, state is in-memory, and stopping dashboard polling also stops notifications.
- Attack history merges `ATTACK_HISTORY_API_URL`, `ATTACK_HISTORY_EXTRA_API_URLS`, and `FAIL2BAN_ATTACKS_API_URL` (Bearer `FAIL2BAN_API_TOKEN`); duplicate URLs are skipped, Fail2Ban rows appear as separate `model: Fail2Ban` entries, and each successful source is guaranteed at least one of the 50 displayed items.
- LightGBM and Random Forest `/api/blocked` read only `blocked_ips` rows with status `BLOCKED`; both `/api/attacks` endpoints return `blocking_status` as `true` (BLOCKED), `false` (UNBLOCKED), or `null` (IP never recorded). The RF API accepts both `RandomForestClassifier` and runtime alias `RandomForest`; do not collapse `false` to `null` in providers or JS.
- LightGBM auto-block duration lives in `/home/server/ids-backend/config/auto_block.json` as `{"block_seconds": 10}` (valid 1-31536000). `capture/feature_worker.py` and `services/auto_block_service.py` call `/usr/local/sbin/ids-auto-block-ssh block` then `unblock-after <ip> <seconds>`; every detection resets the timer. The helper maintains `blocked_ips.unblock_at`; if scheduling fails the IP stays blocked permanently.
- Random Forest uses the same timed auto-block on `.70`: `config/auto_block.json`, `capture/feature_worker.py` schedules after committing `blocked_ips`, and its helper/table maintain `unblock_at`. The RF API (`rf_api.py`) exposes `/api/blocked` and `blocking_status` read-only.

## Frontend

- No build step: plain ES modules (`static/js/*.js`, `static/js/panels/*.js`), Chart.js vendored at `static/vendor/chart.umd.min.js`.
- CSP in `app.py` is `self`-only (`font-src 'self'`, `script-src 'self'`) — no CDN fonts/scripts, no inline `<script>`.
- Fonts are self-hosted Montserrat only (`static/fonts/montserrat-latin-wght.woff2`); `--font-sans` and `--font-mono` both map to it, and `static/js/charts.js` hardcodes the family string — update both when fonts change.
- Theme is dark-only and follows `DESIGN.md` (Spotify system): near-black surfaces (`#121212`/`#181818`/`#1f1f1f`), achromatic UI, Spotify green `#1ed760` used only for functional highlights (active nav index, primary CTA, OK status), pill buttons/selects, 8px cards, 2px badges. Tokens live in `static/css/tokens.css` — change values there, not in component files.
- Chart series colors are hardcoded in `static/js/charts.js` and `static/js/panels/*.js` (not CSS vars) — keep them inside the DESIGN.md palette.
- Two pages share partials: `templates/dashboard/_sidebar.html` and `_topbar.html` are included by both `index.html` (Overview) and `security.html` (Security Feed) — an edit there hits both. Overview is VM-scoped; Security Feed is global.
- VM dropdown (`#vm-select`) and chart range dropdown (`#range-select`, only on Overview) live in the topbar. Changing VM reloads with `?vm=` so server-rendered panels (e.g. no Network Flow for `fail2ban-vm`) re-render; changing range rewrites `?range=` and kicks the poller.
- Blocked IP rows show source (`LightGBM · sshd`), `Auto Unblock` countdown (`mm:ss`, or `Manual` when no schedule); the countdown timer is owned by `static/js/panels/blocked.js` and refreshes every second while visible. Attack History renders `Blocking` from `blocking_status` (`Blocked` / `Not blocked` / `—`); it shows 20 rows per page, a `Semua model` dropdown filter in the toolbar, and client-side pagination over the API's 50-item payload.
- Status indicators follow one rule: success = plain green `Live` text (`.status-live`, no badge chrome); every other state (waiting/connecting/error/unavailable) = the 3-dot `.loader` with **no label**, inside a pill-shaped `.badge`; the no-badge `empty` state = plain `.status-text`. `applyBadge()` in `static/js/dom.js` owns this mapping; the topbar connection uses the same rule in `setConnection()`.
- The owner prefers minimal chrome: recent passes removed redundant labels, section headers, divider lines and footer notes. Don't reintroduce explanatory copy, and delete CSS for markup you remove.

## Workflow notes

- Tests are the only automated check — run them after edits (`105 passed` is the current baseline).
- `git status` currently shows a large uncommitted redesign; don't commit unless asked.
