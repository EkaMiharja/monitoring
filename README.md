# SSH Sentinel — Dashboard Monitoring SSH Brute Force

Dashboard web responsif untuk memantau network traffic, QoS, resource VM, blocked IP, attack history, dan notifikasi Telegram selama pengujian SSH Brute Force.

Implementasi mengikuti `PRD2_revisi.md`, `task_revisi.md`, dan `skill_revisi.md` pada repository ini.

## Panduan Menjalankan Setelah Laptop Menyala

Bagian ini adalah urutan operasional dari laptop baru boot sampai dashboard live. Tunnel SSH sudah autostart; proses dashboard Flask masih dijalankan manual.

> Untuk integrasi VM, gunakan `DATA_MODE=live` di `.env`. Nilai default `.env.example` adalah `demo`, yang menampilkan data simulasi berlabel DEMO.

### 1. Pastikan VM dan service-nya aktif

VM yang dipakai saat ini: `10.207.241.187`. Setelah VM selesai boot, cek service dari laptop:

```powershell
ssh -i $env:USERPROFILE\.ssh\ids_audit server@10.207.241.187
```

Di dalam SSH:

```bash
systemctl --user is-active ids-rf-api.service ids-iperf3.service
systemctl --user is-enabled ids-rf-api.service ids-iperf3.service
systemctl is-active ids-tcpdump.service ids-pcap-worker.service ids-feature-worker.service glances.service glances-qos-api.service
loginctl show-user server | grep Linger
```

Yang diharapkan: `ids-rf-api` dan `ids-iperf3` bernilai `active`/`enabled`, service capture dan Glances `active`, serta `Linger=yes`. `Linger=yes` membuat service user tetap start setelah reboot tanpa menunggu login.

Jika service user belum aktif:

```bash
systemctl --user start ids-rf-api.service ids-iperf3.service
```

Service sistem yang belum aktif dapat dijalankan dengan `sudo systemctl start <nama-service>`.

### 2. Pastikan tunnel SSH aktif

Tunnel berjalan di laptop dan memakai SSH key, bukan password:

| Port laptop | Tujuan di VM | Fungsi |
|---|---|---|
| `127.0.0.1:18080` | `127.0.0.1:8080` | RF API `/api/attacks` dan `/api/features` |
| `127.0.0.1:61210` | `127.0.0.1:61208` | Glances quicklook |

Scheduled Task `SSH Sentinel Tunnel` menjalankan `scripts/start_tunnel.ps1` saat login dan mengecek ulang setiap 5 menit. Script tidak membuka tunnel ganda jika kedua port sudah listen, dan akan mencoba menyambung ulang jika tunnel putus.

Cek statusnya:

```powershell
Get-ScheduledTask -TaskName "SSH Sentinel Tunnel"
Get-ScheduledTaskInfo -TaskName "SSH Sentinel Tunnel"
Test-NetConnection 127.0.0.1 -Port 18080
Test-NetConnection 127.0.0.1 -Port 61210
curl.exe http://127.0.0.1:18080/health
curl.exe http://127.0.0.1:61210/api/3/quicklook
```

`/health` harus mengembalikan `{"ok": true}`. Endpoint Glances harus mengembalikan JSON yang memuat `cpu` dan `mem`. Glances yang terpasang di VM saat ini memakai API versi 3; dashboard mencoba `/api/4/quicklook` lebih dulu lalu fallback ke `/api/3/quicklook`.

Jika tunnel belum aktif, jalankan manual:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\PycharmProjects\Dashboard\scripts\start_tunnel.ps1"
```

Log tunnel ada di `%TEMP%\ssh-sentinel-tunnel.out` dan `%TEMP%\ssh-sentinel-tunnel.err`. Jika IP VM, user SSH, atau lokasi key berubah, sesuaikan `scripts/start_tunnel.ps1` dan URL di `.env`.

### 3. Jalankan dashboard

Jika `.venv` dan `.env` sudah ada:

```powershell
cd $env:USERPROFILE\PycharmProjects\Dashboard
.\.venv\Scripts\python.exe app.py
```

Buka <http://127.0.0.1:5000>, lalu login. Jika akun belum ada, pilih Register terlebih dahulu. Dashboard akan memanggil `/api/overview` setiap 5 detik.

Alternatif menjalankan di background:

```powershell
$project = "$env:USERPROFILE\PycharmProjects\Dashboard"
Start-Process -FilePath "$project\.venv\Scripts\python.exe" `
  -ArgumentList "app.py" `
  -WorkingDirectory $project `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$env:TEMP\ssh-sentinel.out" `
  -RedirectStandardError "$env:TEMP\ssh-sentinel.err"
```

Hentikan dashboard yang sedang memakai port 5000:

```powershell
$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Stop-Process -Id ($conn | Select-Object -First 1).OwningProcess -Force }
```

### 4. Verifikasi tampilan live

Setelah login, cek:

- Badge koneksi di kanan atas menunjukkan `Terhubung` dan `Last updated` terus berubah.
- **Network Flow** menampilkan dropdown 14 fitur dan line chart. Pilihan fitur tidak hilang saat polling berikutnya.
- **QoS Monitoring** menampilkan sampel terakhir; tes manual bisa dijalankan dari tombol.
- **System Resource** menampilkan CPU/memori dari Glances.
- **Attack History** menampilkan hasil RF dan status blocking `—` jika belum ada enforcement.
- **Telegram Alerts** menampilkan riwayat di memori; test alert mengirim pesan jika token/chat ID diisi.

Jika satu panel error, panel lain tetap berjalan. Pesan dan status sumber ditampilkan pada panel masing-masing.

### 5. Pemasangan awal di laptop baru

Jika proyek dan `.venv` belum ada di laptop tersebut:

```powershell
cd $env:USERPROFILE\PycharmProjects\Dashboard
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
.\.venv\Scripts\python.exe app.py
```

Yang perlu disiapkan di laptop baru:

- Python 3.13 dan virtual environment `.venv`.
- OpenSSH client (`ssh.exe`).
- SSH private key, misalnya `C:\Users\<user>\.ssh\ids_audit`.
- iperf3 (WinGet) dan path binary di `IPERF3_BINARY`.
- `.env` berisi `DATA_MODE=live`, URL tunnel, token RF, target ping, dan konfigurasi Telegram jika dipakai.
- Scheduled Task tunnel (lihat bagian **Autostart Tunnel dan VM** di bawah).
- Akses jaringan ke `10.207.241.187`.

### 6. Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Port 5000 tidak bisa dibuka | Proses `app.py` berjalan? Lihat error di console atau `%TEMP%\ssh-sentinel.err`. |
| `http://127.0.0.1:18080/health` gagal | Tunnel mati atau VM/RF API mati. Jalankan script tunnel dan cek service VM. |
| Glances `61210` gagal | Service Glances VM dan tunnel port `61208`. |
| Attack History kosong | Model/prediction di `detection_logs`, token Bearer, dan `ATTACK_HISTORY_API_URL`. |
| Network Flow kosong | `capture/processed/*.csv` belum terisi atau `RF_API_FEATURES_DIR` salah. |
| iperf3 gagal | `IPERF3_BINARY` harus path lengkap; port `5201` harus terbuka dari laptop. |
| Delay tidak ada | Target memblokir ICMP atau `PING_TARGET_HOST` salah. |
| Telegram gagal | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` dan akses internet. |
| Data berhenti lalu pulih | Tunnel putus; Scheduled Task akan mencoba menyambung ulang dalam maksimal sekitar 5 menit. |

## Library yang Dipakai

### Runtime Python

| Library | Versi di `requirements.txt` | Fungsi |
|---|---|---|
| Python | 3.13.x (venv proyek) | Runtime backend dan test |
| Flask | `>=3.1,<4` | Web framework, routing, session, Jinja2 |
| requests | `>=2.31,<3` | HTTP client ke Glances, RF API, dan Telegram |
| python-dotenv | `>=1.0,<2` | Membaca `.env` saat aplikasi start |
| pytest | `>=8,<9` | Test suite |

Library standar yang dipakai langsung: `sqlite3` untuk akun, `subprocess`/`threading` untuk runner iperf3 dan ping, `csv`/`math` untuk membaca fitur RF, `hmac`/`secrets` untuk token dan CSRF, serta `http.server` untuk API RF di VM.

### Frontend

- Chart.js **4.4.7** disajikan lokal dari `static/vendor/chart.umd.min.js`.
- Vanilla JavaScript ES modules; tidak ada Node/npm atau proses build.
- Jinja2 untuk template HTML.
- CSS memakai custom properties di `static/css/tokens.css`.

### Tools dan layanan eksternal

- OpenSSH client di Windows untuk tunnel.
- iperf3 client di laptop dan `iperf3 -s` di VM.
- `ping` bawaan Windows untuk pengukuran delay ICMP.
- Glances di VM untuk CPU/memori.
- systemd di VM untuk capture, fitur, RF API, Glances, dan iperf3.
- Telegram Bot API untuk test alert dan riwayat pengiriman.

## Struktur Dashboard

### Panel UI

| Panel | Isi | Sumber utama |
|---|---|---|
| Network Flow | Dropdown 14 fitur RF dan line chart perubahan | RF API `/api/features` |
| Telegram Alerts | Riwayat alert dan tombol test | Telegram API / memori proses |
| QoS Monitoring | Delay, jitter, packet loss, throughput | iperf3 dan ICMP ping |
| System Resource | CPU dan memori per host | Glances quicklook |
| Blocked IP | Daftar IP yang diblokir | Fail2Ban API (jika dikonfigurasi) |
| Attack History | Riwayat deteksi SSH brute force | RF API `/api/attacks` |

### Struktur direktori

```text
Dashboard/
├─ app.py                    # application factory, blueprint, provider, security headers
├─ config.py                 # konfigurasi dari .env
├─ db.py                     # SQLite akun users
├─ security.py               # CSRF
├─ utils.py                  # waktu ISO/UTC
├─ auth/
│  ├─ routes.py              # register, login, logout
│  └─ decorators.py          # login_required
├─ api/routes.py             # /api/overview dan aksi manual
├─ services/
│  ├─ providers/mock.py      # data demo berlabel DEMO
│  ├─ providers/live.py      # adapter sumber live + QoS
│  ├─ iperf3.py              # runner iperf3 (subprocess -J)
│  ├─ delay.py               # runner ping ICMP
│  ├─ telegram.py            # kirim alert + riwayat in-memory
│  └─ stats.py               # Min/Max/Avg
├─ templates/                # base, auth, dashboard, error
├─ static/
│  ├─ css/                   # tokens, base, components, dashboard, auth
│  ├─ js/                    # polling, charts, panels
│  └─ vendor/chart.umd.min.js
├─ deploy/
│  ├─ rf_api.py              # API RF read-only di VM
│  ├─ rf-api.env.example
│  └─ ids-*.service          # unit systemd referensi
├─ scripts/start_tunnel.ps1  # autostart/recovery tunnel Windows
├─ tests/                    # pytest
├─ instance/dashboard.db     # runtime, hanya akun
└─ .env                      # lokal, tidak di-commit
```

`instance/dashboard.db` hanya menyimpan tabel `users`. Riwayat QoS, attack, dan Telegram tidak dipersistenkan oleh dashboard; attack history diambil ulang dari RF API, sedangkan riwayat Telegram dan sampel QoS berada di memori proses.

## Cara Kerja dan Alur Data

### Topologi

```text
VM 10.207.241.187
├─ capture/processed/*.csv ──► rf_api.py :8080
│                                  ├─ GET /api/attacks  (detection_logs)
│                                  └─ GET /api/features (14 fitur CSV)
├─ Glances :61208
└─ iperf3 server :5201

Laptop monitoring
├─ SSH tunnel
│  ├─ 127.0.0.1:18080 ──► VM 127.0.0.1:8080
│  └─ 127.0.0.1:61210 ──► VM 127.0.0.1:61208
├─ Flask dashboard :5000
├─ iperf3 client ──► 10.207.241.187:5201 (langsung, tanpa tunnel)
└─ ping ──► 10.207.241.187
```

`192.168.56.103` adalah target internal yang terlihat pada data serangan; bukan alamat yang dipakai laptop untuk tunnel.

### Alur request

1. Laptop login ke Flask; session dan CSRF disimpan di cookie/session.
2. Browser membuka `/dashboard` dan memuat `static/js/dashboard.js`.
3. `Poller` memanggil `GET /api/overview` segera setelah halaman dibuka, lalu setiap `POLL_INTERVAL_MS` (default 5000 ms).
4. Route `/api/overview` memilih provider aktif:
   - `MockProvider` jika `DATA_MODE=demo`.
   - `LiveProvider` jika `DATA_MODE=live`.
5. `LiveProvider.get_overview()` mengambil data dari sumber eksternal dan menyusun payload per section.
6. Frontend `applyOverview()` memperbarui semua panel dan grafik tanpa reload halaman.
7. Jika tab browser disembunyikan, polling dihentikan sementara dan dilanjutkan saat tab aktif kembali.

### Sumber live per panel

- **Network Flow**: `GET /api/features` dengan Bearer token. Dashboard membentuk `series` per fitur, menghitung `current`, `previous`, dan `delta`. Dropdown memilih satu fitur; chart menampilkan nilai per sampel autentikasi.
- **QoS**: runner iperf3 dan ping menyimpan sampel di memori. Tombol tes memulai thread background; hasil muncul pada polling berikutnya.
- **System Resource**: `GET /api/4/quicklook` per host Glances; fallback ke `/api/3/quicklook`.
- **Blocked IP**: `FAIL2BAN_API_URL`; daftar dinormalisasi dan hanya status blocked/banned/active yang ditampilkan.
- **Attack History**: `GET /api/attacks`; hasil difilter model `RandomForestClassifier` dan prediction `SSH-Bruteforce`, lalu diurutkan terbaru.
- **Telegram**: riwayat in-memory; test alert mengirim ke Telegram Bot API dari backend.

### Status data

Setiap section memiliki `status`, `source`, `error`, dan data. Nilai status:

- `ok`: data tersedia.
- `empty`: sumber dapat diakses tetapi belum ada sampel.
- `error`: sumber gagal diakses atau format respons salah.
- `unavailable`: endpoint/konfigurasi belum tersedia.

Kegagalan satu section tidak menghentikan section lain. `/api/overview` juga menambahkan `generated_at`, `data_mode`, `poll_interval_ms`, dan daftar `errors`.

### Aksi manual

- `POST /api/telegram/test`: mengirim alert uji.
- `POST /api/iperf3/run`: menjalankan iperf3 di background.
- `POST /api/delay/run`: menjalankan ping ICMP di background.

Ketiganya memerlukan session login dan CSRF token. Aksi iperf3/delay mengembalikan `202` dan `estimated_seconds`; UI memantau hasil lewat polling.

## API yang Dipakai

### API internal dashboard

| Method | Path | Auth | Fungsi |
|---|---|---|---|
| `GET` | `/` | — | Redirect ke login/dashboard |
| `GET/POST` | `/register` | CSRF saat POST | Registrasi akun |
| `GET/POST` | `/login` | CSRF saat POST | Login session |
| `POST` | `/logout` | Session + CSRF | Logout |
| `GET` | `/dashboard` | Session | Halaman dashboard |
| `GET` | `/api/overview` | Session | Snapshot seluruh panel |
| `POST` | `/api/telegram/test` | Session + CSRF | Kirim test alert |
| `POST` | `/api/iperf3/run` | Session + CSRF | Mulai tes iperf3 |
| `POST` | `/api/delay/run` | Session + CSRF | Mulai pengukuran delay |

Contoh ringkas `/api/overview`:

```json
{
  "generated_at": "2026-10-20T08:00:00Z",
  "data_mode": "live",
  "poll_interval_ms": 5000,
  "traffic": {
    "status": "ok",
    "source": "Random Forest flow features",
    "feature_count": 14,
    "sample": {
      "detected_at": "2026-10-20T07:20:01Z",
      "source_ip": "192.168.56.101",
      "target": "192.168.56.103:22",
      "auth_result": "FAILED"
    },
    "features": [
      {
        "name": "Protocol",
        "current": 6.0,
        "previous": 6.0,
        "delta": 0.0,
        "series": [{ "t": "2026-10-20T07:20:01Z", "value": 6.0 }]
      }
    ]
  },
  "qos": { "status": "ok", "metrics": {} },
  "resources": { "status": "ok", "hosts": [] },
  "blocked_ips": { "status": "unavailable", "items": [] },
  "attacks": { "status": "ok", "items": [] },
  "telegram": { "status": "empty", "items": [] },
  "errors": []
}
```

### API RF read-only di VM

API ini ada di `deploy/rf_api.py`, bind ke `127.0.0.1:8080`, dan hanya membaca data.

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/health` | Tanpa token | Cek database |
| `GET` | `/api/attacks?limit=50` | Bearer token | Riwayat deteksi RF |
| `GET` | `/api/features?limit=50` | Bearer token | 14 fitur flow dari CSV |

Ketentuan:

- `limit` 1-200, default 50.
- `/api/attacks` memfilter `model=RandomForestClassifier` dan `prediction=SSH-Bruteforce`.
- `blocking_status` selalu `null` karena API tidak menyimpulkan enforcement.
- `/api/features` membaca `capture/processed/*.csv`; direktori diatur `RF_API_FEATURES_DIR`.
- Token yang sama dipakai dashboard melalui `ATTACK_HISTORY_API_TOKEN`; `FLOW_FEATURES_API_TOKEN` opsional sebagai override.

Contoh item `/api/attacks`:

```json
{
  "id": 123,
  "detected_at": "2026-10-20T07:20:01Z",
  "source_ip": "192.168.56.101",
  "target": "192.168.56.103:22",
  "attack_type": "SSH Brute Force",
  "detection": "Malicious",
  "model": "RandomForestClassifier",
  "blocking_status": null
}
```

14 fitur yang dikembalikan `/api/features`:

```text
Protocol, Flow Duration, Tot Fwd Pkts, Tot Bwd Pkts, TotLen Bwd Pkts,
Flow Pkts/s, Flow IAT Mean, Flow IAT Std, Fwd IAT Mean, Bwd IAT Mean,
Fwd Pkts/s, Bwd Pkts/s, SYN Flag Cnt, ACK Flag Cnt
```

### Sumber eksternal lain

| Sumber | Endpoint | Auth | Dipakai untuk |
|---|---|---|---|
| Glances | `GET /api/4/quicklook` (fallback `/api/3/quicklook`) | — | CPU/memori host |
| Fail2Ban | `FAIL2BAN_API_URL` | sesuai sumber | Blocked IP |
| iperf3 | `10.207.241.187:5201` TCP/UDP | — | Throughput/jitter/loss |
| ICMP | `PING_TARGET_HOST` | — | Delay |
| Telegram | `POST https://api.telegram.org/bot<token>/sendMessage` | Bot token | Test alert |
| Fallback iperf3 | `IPERF3_RESULT_URL` | — | Snapshot hasil iperf3 |
| Fallback delay | `DELAY_API_URL` | — | Sampel delay |

`LIGHTGBM_API_URL`, `RANDOM_FOREST_API_URL`, `API_BASE_URL`, dan `IPERF3_TEST_INTERVAL_SECONDS` masih ada di konfigurasi, tetapi belum dipakai oleh provider live saat ini. Gunakan `ATTACK_HISTORY_API_URL` dan `FLOW_FEATURES_API_URL` untuk integrasi RF yang aktif.

## Konfigurasi Ringkas Mode Live

Salin `.env.example` ke `.env`, lalu isi nilai berikut. Jangan menulis token nyata ke README atau commit `.env`.

```dotenv
DATA_MODE=live
SECRET_KEY=<hasil-generate-acak>
DATABASE_PATH=instance/dashboard.db

GLANCES_RANDOM_FOREST_URL=http://127.0.0.1:61210
GLANCES_RANDOM_FOREST_LABEL=randomforest-vm

ATTACK_HISTORY_API_URL=http://127.0.0.1:18080/api/attacks
ATTACK_HISTORY_API_TOKEN=<token-yang-sama-dengan-RF_API_TOKEN>
FLOW_FEATURES_API_URL=http://127.0.0.1:18080/api/features

IPERF3_ENABLED=true
IPERF3_BINARY=C:\path\lengkap\iperf3.exe
IPERF3_SERVER_HOST=10.207.241.187
IPERF3_PORT=5201
IPERF3_TEST_PROTOCOL=udp
IPERF3_BANDWIDTH=100M

PING_TARGET_HOST=10.207.241.187
```

Catatan:

- Port lokal tunnel (`18080`, `61210`) harus sama dengan yang ada di `scripts/start_tunnel.ps1`.
- `ATTACK_HISTORY_API_TOKEN` harus sama dengan `RF_API_TOKEN` di `/home/server/ids-backend/.rf-api.env`.
- `FLOW_FEATURES_API_TOKEN` boleh dikosongkan; backend akan memakai token attack history.
- Glances LightGBM/Fail2Ban hanya perlu diisi jika host tersebut tersedia.
- `.env` berisi secret dan sudah masuk `.gitignore`.

## Autostart Tunnel dan VM

### Tunnel di laptop

- Nama task: `SSH Sentinel Tunnel`.
- Script: `scripts/start_tunnel.ps1`.
- Trigger: saat login dan pengulangan setiap 5 menit.
- Key: `C:\Users\eka\.ssh\ids_audit`.
- Server: `server@10.207.241.187`.
- Log: `%TEMP%\ssh-sentinel-tunnel.out` dan `%TEMP%\ssh-sentinel-tunnel.err`.

Perintah verifikasi dan pemulihan:

```powershell
Get-ScheduledTask -TaskName "SSH Sentinel Tunnel"
Get-ScheduledTaskInfo -TaskName "SSH Sentinel Tunnel"
Start-ScheduledTask -TaskName "SSH Sentinel Tunnel"
```

Jika task belum ada di laptop baru, buat setelah script dan key tersedia:

```powershell
$project = "$env:USERPROFILE\PycharmProjects\Dashboard"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$project\scripts\start_tunnel.ps1`""
$logon = New-ScheduledTaskTrigger -AtLogOn
$watch = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "SSH Sentinel Tunnel" `
  -Action $action -Trigger @($logon, $watch) -Principal $principal -Force
```

Dashboard Flask **tidak** termasuk task ini. Jika ingin dashboard ikut start saat login, buat task terpisah:

```powershell
$project = "$env:USERPROFILE\PycharmProjects\Dashboard"
$action = New-ScheduledTaskAction -Execute "$project\.venv\Scripts\pythonw.exe" `
  -Argument "app.py" -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "SSH Sentinel Dashboard" `
  -Action $action -Trigger $trigger -Force
```

### Service VM

| Unit | Jenis | Fungsi |
|---|---|---|
| `ids-tcpdump` | system | Capture trafik |
| `ids-pcap-worker` | system | Pemrosesan PCAP |
| `ids-feature-worker` | system | Pembentukan fitur flow |
| `glances` / `glances-qos-api` | system | Metrik resource |
| `ids-rf-api` | user | API RF read-only `:8080` |
| `ids-iperf3` | user | Server iperf3 `:5201` |

Service user berada di `~/.config/systemd/user/` dan berjalan karena linger aktif. Perintah cek/restart:

```bash
systemctl --user is-enabled ids-rf-api.service ids-iperf3.service
systemctl --user restart ids-rf-api.service ids-iperf3.service
journalctl --user -u ids-rf-api.service -n 50
```

Setelah VM reboot, tunggu service dan tunnel pulih. Tunnel akan mencoba menyambung ulang dalam siklus watchdog sekitar 5 menit.

> Bagian **Status Implementasi**, **Menjalankan**, **Konfigurasi**, **Arsitektur**, **Kontrak API Internal**, **Integrasi VM Random Forest**, **Autostart VM**, **Pengujian**, dan **Batasan** di bawah dipertahankan sebagai referensi rinci. Jika ada perbedaan, gunakan panduan operasional di atas sebagai acuan terbaru.

## Status Implementasi

| Area | Status |
|---|---|
| Struktur proyek, konfigurasi `.env`, SQLite akun | Selesai |
| Register, Login, Logout, proteksi halaman/API | Selesai |
| Dashboard shell responsif (desktop/tablet/mobile) | Selesai |
| API JSON terpusat `/api/overview` + polling 5 detik | Selesai |
| Enam panel Overview dengan grafik Chart.js | Selesai (demo dan live) |
| Statistik Min/Max/Avg dari sampel grafik | Selesai |
| Loading, empty, error, dan stale state | Selesai |
| Telegram: status/riwayat + test alert | Selesai (simulasi di mode demo) |
| Adapter API live | RF API dan Glances terintegrasi; LightGBM/Fail2Ban menunggu kontrak |
| Runner iperf3 (manual) + delay ICMP ping | Selesai dan terverifikasi |
| Glances VM untuk resource | Terpasang dan terverifikasi |

**Mode default adalah `demo`.** Semua data demo diberi label DEMO di UI dan tidak boleh dianggap sebagai data live.

## Menjalankan

Prasyarat: Python 3.13 dan virtual environment `.venv` pada proyek (sudah tersedia).

Windows (PowerShell/CMD):

```bat
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Alternatif tanpa mengaktifkan venv:

```bat
.venv\Scripts\python.exe app.py
```

Buka <http://127.0.0.1:5000>, lalu Register akun baru dan Login.

Dari WSL/Linux pada proyek Windows ini:

```bash
./.venv/Scripts/python.exe app.py
```

## Alat ukur di laptop (Windows)

Bagian ini adalah referensi lama untuk alat ukur di laptop. Pada topologi VM RF yang dipakai saat ini, Glances berjalan di VM dan diakses lewat tunnel port `61210`; lihat panduan di atas.

Pengukuran QoS dijalankan backend dari laptop monitoring.

### iperf3

```powershell
winget install --id ar51an.iPerf3 -e
iperf3 --version
```

Jika `iperf3` belum masuk PATH setelah instalasi, isi `IPERF3_BINARY` dengan path lengkap exe hasil winget.

### Glances

Gunakan virtual environment terpisah agar dependensi dashboard tidak tercampur.

```powershell
py -3.13 -m venv %USERPROFILE%\glances-venv
%USERPROFILE%\glances-venv\Scripts\python.exe -m pip install glances fastapi uvicorn
%USERPROFILE%\glances-venv\Scripts\glances.exe -w --bind 127.0.0.1 -p 61208 --disable-webui
```

Verifikasi <http://127.0.0.1:61208/api/4/quicklook> mengembalikan `cpu` dan `mem`. Glances di Windows mendukung CPU/memori/disk via psutil; sensor suhu/GPU tidak tersedia.

### Delay

Delay diukur dengan `ping` bawaan Windows (ICMP). Target harus mengizinkan ICMP; bila diblokir panel delay menampilkan "Belum tersedia".

### Contoh konfigurasi live untuk laptop

Contoh berikut adalah ilustrasi lama, bukan konfigurasi VM RF yang dipakai saat ini.

```dotenv
DATA_MODE=live
GLANCES_LIGHTGBM_URL=http://127.0.0.1:61208
GLANCES_LIGHTGBM_LABEL=laptop-monitoring
IPERF3_ENABLED=true
IPERF3_SERVER_HOST=192.168.56.10
IPERF3_TEST_PROTOCOL=udp
IPERF3_BANDWIDTH=100M
PING_TARGET_HOST=192.168.56.10
```

## Konfigurasi

Semua konfigurasi dibaca dari `.env` melalui `config.py`. Jangan commit `.env` berisi secret.

| Variabel | Default | Keterangan |
|---|---|---|
| `SECRET_KEY` | `dev-only-change-me` | Wajib diganti untuk deployment |
| `DATABASE_PATH` | `instance/dashboard.db` | SQLite khusus akun |
| `DATA_MODE` | `demo` | `demo` atau `live` |
| `POLL_INTERVAL_MS` | `5000` | Interval polling UI |
| `STATS_WINDOW_SECONDS` | `300` | Jendela sampel statistik |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` saat memakai HTTPS |
| `CSRF_ENABLED` | `true` | Proteksi form/aksi POST |
| `LIGHTGBM_API_URL`, `RANDOM_FOREST_API_URL` | kosong | Reserved; belum dipakai provider live saat ini |
| `FAIL2BAN_API_URL` | kosong | Sumber daftar IP terblokir |
| `ATTACK_HISTORY_API_URL` | kosong | Sumber riwayat serangan |
| `ATTACK_HISTORY_API_TOKEN` | kosong | Token Bearer untuk API attack history; hanya backend |
| `FLOW_FEATURES_API_URL` | kosong | Endpoint 14 fitur flow Random Forest |
| `FLOW_FEATURES_API_TOKEN` | kosong | Opsional; fallback ke `ATTACK_HISTORY_API_TOKEN` |
| `GLANCES_*_URL` | kosong | Base URL Glances per VM/laptop (`quicklook` API) |
| `GLANCES_*_LABEL` | nama host | Label host yang ditampilkan di UI |
| `QOS_HISTORY_POINTS` | `240` | Jumlah titik sampel QoS yang disimpan |
| `IPERF3_ENABLED` | `false` | Aktifkan runner iperf3 |
| `IPERF3_BINARY` | `iperf3` | Nama/path binari iperf3 |
| `IPERF3_SERVER_HOST`, `IPERF3_PORT` | kosong, `5201` | Host server iperf3 tujuan |
| `IPERF3_TEST_PROTOCOL`, `IPERF3_BANDWIDTH` | `udp`, `100M` | Jitter/loss hanya dari UDP; bandwidth target UDP |
| `IPERF3_TEST_DURATION_SECONDS`, `IPERF3_OMIT_SECONDS` | `10`, `1` | Durasi tes dan detik pemanasan yang diabaikan |
| `IPERF3_RESULT_URL` | kosong | Fallback membaca snapshot hasil iperf3 |
| `DELAY_API_URL` | kosong | Fallback sumber delay terpisah |
| `PING_TARGET_HOST`, `PING_COUNT` | kosong, `5` | Target dan jumlah paket ICMP |
| `PING_TIMEOUT_MS` | `1000` | Timeout per balasan ICMP |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | kosong | Hanya dibaca backend |

## Arsitektur

```text
Browser (HTML/CSS/JS + Chart.js)
        │  polling /api/overview setiap 5 detik
        ▼
Flask (laptop monitoring)
├── auth/       session + SQLite akun
├── api/        JSON terpusat
└── services/
    ├── providers/mock.py   data simulasi berlabel DEMO
    ├── providers/live.py   adapter API eksternal + runner QoS
    ├── iperf3.py           runner iperf3 manual (subprocess `-J`)
    ├── delay.py            runner ICMP ping manual
    ├── stats.py            Min/Max/Avg dari sampel yang sama
    └── telegram.py         kirim + riwayat (in-memory)
```

- SQLite hanya menyimpan akun (`users`), bukan telemetry.
- Frontend tidak pernah menerima token Telegram atau kredensial.
- Kegagalan satu sumber tidak menghentikan panel lain: setiap section memiliki `status`, `error`, `source`, dan timestamp.
- Riwayat Telegram disimpan di memori proses (bukan SQLite), sesuai PRD.

## Kontrak API Internal

`GET /api/overview` (login required) mengembalikan bentuk berikut. Kontrak ini adalah kontrak internal dashboard; mapping ke API tim masih provisional.

```json
{
  "generated_at": "2026-10-20T10:15:00Z",
  "data_mode": "demo",
  "poll_interval_ms": 5000,
  "stats_window_seconds": 300,
  "traffic": {
    "status": "ok",
    "source": "Pengukuran lokal laptop monitoring (DEMO)",
    "unit": "Mbps",
    "error": null,
    "series": [{ "t": "...", "inbound": 78.2, "outbound": 31.4 }]
  },
  "qos": {
    "status": "ok",
    "source": "...",
    "error": null,
    "metrics": {
      "delay": {
        "status": "ok",
        "unit": "ms",
        "source": "...",
        "error": null,
        "series": [{ "t": "...", "value": 18.4 }],
        "stats": { "min": 18.1, "max": 27.8, "avg": 23.5, "count": 60 }
      },
      "jitter": {},
      "packet_loss": {},
      "throughput": {}
    },
    "test": {
      "protocol": "UDP",
      "direction": "upload",
      "client": "...",
      "server": "...",
      "duration_seconds": 10,
      "status": "success",
      "timestamp": "..."
    },
    "delay_test": {
      "method": "ICMP",
      "target": "192.168.56.10",
      "count": 5,
      "delay_ms": 21.4,
      "min_ms": 18.0,
      "max_ms": 27.0,
      "packet_loss_percent": 0.0,
      "status": "success",
      "timestamp": "..."
    }
  },
  "resources": {
    "status": "ok",
    "source": "Glances",
    "error": null,
    "hosts": [
      {
        "host": "lightgbm-vm",
        "status": "ok",
        "source": "Glances",
        "error": null,
        "cpu": { "unit": "%", "series": [], "stats": {} },
        "memory": { "unit": "%", "series": [], "stats": {} }
      }
    ]
  },
  "blocked_ips": { "status": "ok", "source": "Fail2Ban", "error": null, "items": [] },
  "attacks": { "status": "ok", "source": "API deteksi", "error": null, "items": [] },
  "telegram": { "status": "ok", "source": "Telegram Bot API", "error": null, "items": [] },
  "errors": []
}
```

`status` per section: `ok`, `empty`, `error`, `unavailable`. Nilai yang tidak tersedia dikirim sebagai `null`, bukan `0`.

Pada mode live, panel **Network Flow** memakai 14 fitur input Random Forest:
`Protocol`, `Flow Duration`, `Tot Fwd Pkts`, `Tot Bwd Pkts`, `TotLen Bwd Pkts`,
`Flow Pkts/s`, `Flow IAT Mean`, `Flow IAT Std`, `Fwd IAT Mean`, `Bwd IAT Mean`,
`Fwd Pkts/s`, `Bwd Pkts/s`, `SYN Flag Cnt`, dan `ACK Flag Cnt`. Setiap fitur
membawa `current`, `previous`, `delta`, dan `series` untuk melihat perubahan.
Panel memakai dropdown untuk memilih satu fitur dan menampilkan `series`-nya
sebagai line chart, sehingga perubahan nilai terbaca dari naik/turunnya garis.
Bentuk `traffic` live:

```json
{
  "status": "ok",
  "source": "Random Forest flow features",
  "error": null,
  "feature_count": 14,
  "sample": {
    "detected_at": "2026-10-20T07:19:40Z",
    "source_ip": "192.168.56.2",
    "target": "192.168.56.103:22",
    "auth_result": "FAILED"
  },
  "features": [
    {
      "name": "Protocol",
      "current": 6.0,
      "previous": 6.0,
      "delta": 0.0,
      "series": [{ "t": "2026-10-20T07:19:40Z", "value": 6.0 }]
    }
  ]
}
```

Mode demo tetap memakai bentuk lama `series` inbound/outbound agar grafik demo
tidak berubah.

`POST /api/telegram/test` mengirim alert uji. Di mode demo hasilnya disimulasikan; di mode live endpoint mengembalikan `502` jika Telegram gagal/tidak dikonfigurasi.

`POST /api/iperf3/run` dan `POST /api/delay/run` memulai pengukuran manual di background lalu mengembalikan `202` beserta `estimated_seconds`. Keduanya memerlukan login + CSRF, dan mengembalikan `409` bila runner tidak tersedia (mode demo) atau pengukuran masih berjalan. Hasil muncul pada polling `/api/overview` berikutnya melalui `qos.test` (iperf3) dan `qos.delay_test` (ICMP).

### Bentuk data yang diharapkan adapter live

- `FAIL2BAN_API_URL`: list item atau `{ "items": [...] }`; field `ip`, `blocked_at`, `jail`, `status`.
- `ATTACK_HISTORY_API_URL`: list item atau `{ "items": [...] }`; field `detected_at`, `source_ip`, `attack_type`, `detection`, `model`, `blocking_status`.
- `IPERF3_RESULT_URL`: `{ "timestamp", "throughput_mbps", "jitter_ms", "packet_loss_percent", "protocol" }` (fallback bila runner lokal tidak aktif).
- `DELAY_API_URL`: `{ "timestamp", "delay_ms" }` (fallback bila `PING_TARGET_HOST` kosong).
- `GLANCES_*_URL`: base URL Glances; backend memanggil `/api/4/quicklook` (fallback `/api/3/quicklook`) dan membaca `cpu` serta `mem`.

Jika `IPERF3_ENABLED=true` dan `IPERF3_SERVER_HOST` diisi, backend menjalankan `iperf3 -c <host> -J` sendiri (UDP memakai `-u -b <bandwidth>`) sehingga `IPERF3_RESULT_URL` tidak diperlukan. Jika `PING_TARGET_HOST` diisi, delay diukur langsung via ICMP.

Semua bentuk di atas **provisional** dan harus disesuaikan dengan kontrak API tim.

## Integrasi VM Random Forest (read-only)

API RF ada di `deploy/rf_api.py`. Endpoint `/api/attacks` membaca `detection_logs`
dengan filter `model = 'RandomForestClassifier'` dan `prediction = 'SSH-Bruteforce'`;
endpoint `/api/features` membaca 14 fitur dari `capture/processed/*.csv`. Keduanya
read-only dan mewajibkan Bearer token. API tidak menulis DB dan tidak menganggap
`action = 'WOULD_BLOCK'` sebagai IP terblokir; `blocking_status` dikirim `null`
sampai ada enforcement yang terkonfirmasi.

Jalankan tunnel dari laptop (port lokal 61210/18080 agar tidak bentrok dengan
Glances laptop di 61208):

```powershell
ssh -N -i $env:USERPROFILE\.ssh\ids_audit `
  -L 61210:127.0.0.1:61208 `
  -L 18080:127.0.0.1:8080 `
  server@10.207.241.187
```

Konfigurasi `.env` terkait:

```dotenv
GLANCES_RANDOM_FOREST_URL=http://127.0.0.1:61210
ATTACK_HISTORY_API_URL=http://127.0.0.1:18080/api/attacks
ATTACK_HISTORY_API_TOKEN=<token-dari-VM>
FLOW_FEATURES_API_URL=http://127.0.0.1:18080/api/features
IPERF3_ENABLED=true
IPERF3_SERVER_HOST=10.207.241.187
PING_TARGET_HOST=10.207.241.187
```

Server iperf3 berjalan langsung di VM (bukan lewat tunnel) agar pengukuran
mencerminkan jalur LAN. Izinkan `5201/tcp` dan `5201/udp` hanya dari subnet
monitoring. Jika tunnel mati, panel RF menampilkan error/unavailable, bukan data
demo.

Autostart tunnel di laptop memakai Scheduled Task `SSH Sentinel Tunnel` yang
menjalankan `scripts/start_tunnel.ps1` saat login dan dicek ulang setiap 5 menit.
Script bersifat idempotent: jika kedua port lokal sudah listen, script tidak
membuka tunnel baru; jika tunnel putus, script membersihkan proses lama lalu
mencoba menyambung ulang. Log ada di `%TEMP%\ssh-sentinel-tunnel.out` dan
`%TEMP%\ssh-sentinel-tunnel.err`.

```powershell
Get-ScheduledTask -TaskName "SSH Sentinel Tunnel"
Start-ScheduledTask -TaskName "SSH Sentinel Tunnel"
Get-ScheduledTaskInfo -TaskName "SSH Sentinel Tunnel"
```

## Autostart VM

Di VM, `ids-rf-api.service` dan `ids-iperf3.service` adalah unit **systemd user**
di `~/.config/systemd/user/` yang di-enable dengan linger aktif, sehingga ikut start setelah reboot tanpa
perlu login. Unit capture (`ids-tcpdump`, `ids-pcap-worker`,
`ids-feature-worker`) dan Glances sudah berupa service sistem yang enabled.

```bash
systemctl --user is-enabled ids-rf-api.service ids-iperf3.service
systemctl --user restart ids-rf-api.service ids-iperf3.service
journalctl --user -u ids-rf-api.service -n 50
```

## Pengujian

```bat
.venv\Scripts\python.exe -m pytest
```

Cakupan saat ini: register/login/logout, proteksi route/API, CSRF, kontrak overview, konsistensi statistik, mode live tanpa endpoint, endpoint test Telegram, parsing keluaran iperf3 (TCP/UDP) dan ping (locale ID/EN/Linux), endpoint trigger QoS, serta API RF read-only (filter model, token, limit, timestamp, dan endpoint 14 fitur flow).

## Batasan yang Masih Terbuka

- `desain.md` tidak tersedia; tema gelap dibuat sementara dan mudah diganti melalui token CSS.
- Endpoint serta skema API LightGBM, Fail2Ban, dan Glances belum final. API RF read-only sudah dipakai untuk attack history dan 14 fitur flow.
- Panel Network Flow menampilkan line chart per fitur RF yang dipilih lewat dropdown; metrik throughput/flow mentah belum dikoleksi terpisah.
- Server iperf3 berjalan di VM; hasil throughput/jitter/loss bergantung pada jalur LAN dan aturan UFW.
- Delay memakai ICMP ping. Jaringan yang memblokir ICMP (termasuk jaringan laptop saat ini untuk target internet) tidak dapat diukur; gunakan target LAN/VPN yang mengizinkan ICMP.
- Statistik QoS dihitung dari `QOS_HISTORY_POINTS` sampel terakhir, bukan `STATS_WINDOW_SECONDS`, agar tes manual yang jarang tidak langsung kosong.
- Glances di Windows mendukung CPU/memori/disk via psutil; sensor suhu/GPU tidak tersedia.
- Threshold baik/buruk QoS sengaja tidak diimplementasikan.
- Histori serangan tidak dipersistenkan oleh dashboard; data dibaca dari API RF. Riwayat Telegram hanya ada di memori proses.
