# AGENTS.md

Flask dashboard for SSH brute-force monitoring (Windows laptop, WSL working dir). Indonesian-language UI copy.

## Commands

```bash
# venv lives in the Windows tree; run it from WSL via the Scripts/ entrypoint
/mnt/c/Users/eka/PycharmProjects/Dashboard/.venv/Scripts/python.exe -m pytest -q
/mnt/c/Users/eka/PycharmProjects/Dashboard/.venv/Scripts/python.exe app.py   # port 5000
```

- No linter/formatter/typechecker config exists — `pytest` is the only gate. Suite: 41 tests, ~14 s.
- Single test: `... -m pytest tests/test_api.py::test_name -q`.
- `requirements.txt` = Flask, requests, python-dotenv, pytest only. `playwright` is also present in `.venv` (not in requirements) and works for screenshots via `p.chromium.launch(channel="chrome")`.
- Headless Chrome CLI (`chrome.exe --screenshot`) silently produces nothing from WSL — use Playwright instead.

## Config & runtime

- `config.py` loads `.env` at import; `DATA_MODE=demo` → `MockProvider`, `live` → `LiveProvider` (chosen in `app.py`).
- `DATA_MODE` and every source URL live in `.env`; `.env.example` documents all of them. Never commit `.env`.
- Live mode needs the SSH tunnel (`scripts/start_tunnel.ps1`, ports 18080 RF API / 61210 Glances). Tunnel is a Windows Scheduled Task, not part of the app.
- Sources are often absent. Missing data must surface as honest `unavailable`/`error` section status — never fabricate per-VM numbers.

## API contract (do not change silently)

- `GET /api/overview?vm=<id>` — sections: `traffic, qos, resources, blocked_ips, attacks, telegram`; response also carries `vm`, `qos_vm`, `generated_at`, `data_mode`, `poll_interval_ms`, `errors[]`.
- Unknown `vm` → HTTP 400 `invalid_vm`. Omitting `vm` keeps the legacy payload (`resources.hosts` length 3).
- State-changing endpoints (`/api/telegram/test`, `/api/iperf3/run`, `/api/delay/run`, auth routes) require session + CSRF (`security.csrf_protect`).
- `VM_SPECS` in `config.py` is the single source for VM ids/labels; `QOS_VM` is the only VM with QoS data.

## Frontend

- No build step: plain ES modules (`static/js/*.js`, `static/js/panels/*.js`), Chart.js vendored at `static/vendor/chart.umd.min.js`.
- CSP in `app.py` is `self`-only (`font-src 'self'`, `script-src 'self'`) — no CDN fonts/scripts, no inline `<script>`.
- Fonts are self-hosted Montserrat only (`static/fonts/montserrat-latin-wght.woff2`); `--font-sans` and `--font-mono` both map to it, and `static/js/charts.js` hardcodes the family string — update both when fonts change.
- Theme is dark-only and follows `DESIGN.md` (Spotify system): near-black surfaces (`#121212`/`#181818`/`#1f1f1f`), achromatic UI, Spotify green `#1ed760` used only for functional highlights (active nav index, primary CTA, OK status), pill buttons/selects, 8px cards, 2px badges. Tokens live in `static/css/tokens.css` — change values there, not in component files.
- Chart series colors are hardcoded in `static/js/charts.js` and `static/js/panels/*.js` (not CSS vars) — keep them inside the DESIGN.md palette.
- Two pages share partials: `templates/dashboard/_sidebar.html` and `_topbar.html` are included by both `index.html` (Overview) and `security.html` (Security Feed) — an edit there hits both. Overview is VM-scoped; Security Feed is global.
- VM dropdown lives in the topbar (`#vm-select`); changing it rewrites `?vm=` in the URL and kicks the poller.
- Status indicators follow one rule: success = plain green `Live` text (`.status-live`, no badge chrome); every other state (waiting/connecting/error/unavailable) = the 3-dot `.loader` with **no label**, inside a pill-shaped `.badge`; the no-badge `empty` state = plain `.status-text`. `applyBadge()` in `static/js/dom.js` owns this mapping; the topbar connection uses the same rule in `setConnection()`.
- The owner prefers minimal chrome: recent passes removed redundant labels, section headers, divider lines and footer notes. Don't reintroduce explanatory copy, and delete CSS for markup you remove.

## Workflow notes

- Tests are the only automated check — run them after edits (`41 passed` is the current baseline).
- `git status` currently shows a large uncommitted redesign; don't commit unless asked.
