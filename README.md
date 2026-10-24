# SSH Sentinel — Dashboard Monitoring SSH Brute Force

Dashboard web responsif untuk memantau network traffic, QoS, resource VM, blocked IP, attack history, dan notifikasi Telegram selama pengujian SSH Brute Force.

Implementasi mengikuti `PRD2_revisi.md`, `task_revisi.md`, dan `skill_revisi.md` pada repository ini.

## Panduan Menjalankan Setelah Laptop Menyala

Bagian ini adalah urutan operasional dari laptop baru boot sampai dashboard live. Ketiga VM diakses langsung lewat Wi-Fi/LAN yang sama (tanpa tunnel/Tailscale); proses dashboard Flask masih dijalankan manual.

> Untuk integrasi VM, gunakan `DATA_MODE=live` di `.env`. Nilai default `.env.example` adalah `demo`, yang menampilkan data simulasi berlabel DEMO.

### 1. Pastikan VM dan service-nya aktif

VM yang dipakai saat ini: LightGBM `192.168.100.69`, random forest `192.168.100.70`, dan Fail2Ban `192.168.100.71`. Setelah VM selesai boot, cek service dari laptop:

```powershell
ssh -i $env:USERPROFILE\.ssh\ids_audit server@192.168.100.69   # lightgbm
ssh -i $env:USERPROFILE\.ssh\ids_audit server@192.168.100.70   # random forest
ssh -i $env:USERPROFILE\.ssh\ids_audit server@192.168.100.71   # fail2ban
```

Di dalam SSH:

```bash
systemctl --user is-active ids-rf-api.service ids-iperf3.service
systemctl --user is-enabled ids-rf-api.service ids-iperf3.service
systemctl is-active ids-tcpdump.service ids-pcap-worker.service ids-feature-worker.service glances.service glances-qos-api.service
loginctl show-user server | grep Linger
```

Yang diharapkan: `ids-rf-api` dan `ids-iperf3` bernilai `active`/`enabled`, service capture dan Glances `active`, serta `Linger=yes`. `Linger=yes` membuat service user tetap start setelah reboot tanpa menunggu login. Di VM Fail2Ban, cek `glances-web`, `ids-fail2ban-api`, dan `qos-probe-fail2ban.timer` (semua system service).

Jika service user belum aktif:

```bash
systemctl --user start ids-rf-api.service ids-iperf3.service
```

Service sistem yang belum aktif dapat dijalankan dengan `sudo systemctl start <nama-service>`.

### 2. Pastikan akses LAN ke ketiga VM

Tidak ada tunnel/Tailscale. Dashboard mengakses API dan Glances langsung ke IP VM di Wi-Fi/LAN yang sama:

| Dari laptop | Tujuan | Fungsi |
|---|---|---|
| `192.168.100.69:8080` | LightGBM API | `/api/attacks`, `/api/features`, dan `/api/blocked` (Bearer) |
| `192.168.100.69:61208` | Glances LightGBM | quicklook (CPU/memori) |
| `192.168.100.70:8080` | RF API | `/api/attacks` dan `/api/features` |
| `192.168.100.70:61208` | Glances RF | quicklook (CPU/memori) |
| `192.168.100.71:8080` | Fail2Ban API | `/api/blocked`, `/api/attacks`, dan `/api/qos` (Bearer) |
| `192.168.100.71:61208` | Glances Fail2Ban | quicklook (CPU/memori) |
| `192.168.100.69` / `.70:5201` | iperf3 | throughput/jitter; packet loss dari ICMP ping |

Cek statusnya:

```powershell
Test-NetConnection 192.168.100.69 -Port 8080
Test-NetConnection 192.168.100.69 -Port 61208
Test-NetConnection 192.168.100.70 -Port 8080
Test-NetConnection 192.168.100.70 -Port 61208
Test-NetConnection 192.168.100.71 -Port 8080
Test-NetConnection 192.168.100.71 -Port 61208
curl.exe http://192.168.100.69:8080/health
curl.exe http://192.168.100.70:8080/health
curl.exe http://192.168.100.71:8080/health
curl.exe http://192.168.100.69:61208/api/4/quicklook
curl.exe http://192.168.100.71:61208/api/4/quicklook
```

`/health` harus mengembalikan `{"ok": true}`. Endpoint Glances harus mengembalikan JSON yang memuat `cpu` dan `mem`. Dashboard memakai `/api/4/quicklook` dan fallback ke `/api/3/quicklook` untuk Glances lama.

Jika IP VM berubah karena DHCP, cukup ganti satu baris di `.env` atau jalankan helper:

```powershell
.\scripts\set_vm_host.ps1 192.168.100.69                      # VM lightgbm
.\scripts\set_vm_host.ps1 -Variable RF_VM_HOST 192.168.100.70   # VM random forest
```

IP laptop tidak dikonfigurasi di mana pun; perubahan IP laptop tidak memerlukan edit `.env`. `ufw` di VM nonaktif, jadi tidak ada rule subnet/IP yang perlu diubah.

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
- **Network Flow** menampilkan dropdown 17 fitur dan line chart. Pilihan fitur tidak hilang saat polling berikutnya.
- **QoS Monitoring** menampilkan sampel terakhir; tes manual bisa dijalankan dari tombol.
- **System Resource** menampilkan CPU/memori dari Glances.
- **Attack History** menampilkan hasil RF, LightGBM, dan ban Fail2Ban sebanyak 20 baris per halaman; filter model dan pagination bekerja di sisi klien atas maksimal 50 event, dan status blocking `—` muncul jika sumber tidak menyediakannya.
- **Telegram Alerts** menampilkan riwayat di memori; test alert mengirim pesan jika token/chat ID diisi. Dengan `TELEGRAM_BLOCK_NOTIFY_ENABLED=true`, IP yang baru diblokir dan yang sudah lepas dari semua model ikut dikirim selama dashboard polling.

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
- iperf3 (WinGet) dan path binary di `IPERF3_BINARY`.
- `.env` berisi `DATA_MODE=live`, `VM_HOST`, `RF_VM_HOST`, token, target ping, dan konfigurasi Telegram (`TELEGRAM_BLOCK_NOTIFY_ENABLED=true` bila notifikasi blokir otomatis dipakai).
- Akses Wi-Fi/LAN ke `192.168.100.69` (lightgbm) dan `192.168.100.70` (random forest).
- Tidak perlu OpenSSH key, Scheduled Task tunnel, atau konfigurasi IP laptop.

### 6. Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Port 5000 tidak bisa dibuka | Proses `app.py` berjalan? Lihat error di console atau `%TEMP%\ssh-sentinel.err`. |
| `http://192.168.100.70:8080/health` gagal | VM/RF API mati atau IP DHCP berubah; cek `RF_VM_HOST` di `.env`. |
| Glances `61208` gagal | Service Glances VM dan `GLANCES_*_URL` di `.env`. |
| Attack History kosong | Model/prediction di `detection_logs`, token Bearer, `ATTACK_HISTORY_API_URL`, dan `FAIL2BAN_ATTACKS_API_URL`. |
| Ban Fail2Ban tidak muncul di Attack History | Endpoint `/api/attacks` di `.71`, `FAIL2BAN_ATTACKS_API_URL`, token, dan isi `/var/log/fail2ban.log`. |
| Baris "Sumber" Attack History menyebut "N sumber gagal" | Salah satu endpoint tidak terjangkau; detail ada di `attacks.warnings` pada respons `/api/overview`. |
| Network Flow kosong | `capture/processed/*.csv` belum terisi atau `RF_API_FEATURES_DIR` salah. |
| LightGBM API tidak terjangkau | `curl.exe http://192.168.100.69:8080/health`; cek `ids-lightgbm-api` aktif di VM dan `VM_HOST` di `.env` cocok dengan IP DHCP. |
| Traffic VM lightgbm kosong | `LIGHTGBM_API_FEATURES_DIR` di VM dan `FLOW_FEATURES_LIGHTGBM_URL`/`FLOW_FEATURES_LIGHTGBM_TOKEN` di `.env` laptop. |
| Resource VM lightgbm kosong | `glances-web` aktif di VM dan `GLANCES_LIGHTGBM_URL` benar; Glances harus versi 4 (`/api/4/quicklook`). |
| iperf3 gagal | `IPERF3_BINARY` harus path lengkap; port `5201` harus terbuka dari laptop. |
| Delay tidak ada | Target memblokir ICMP atau `PING_TARGET_HOST` salah. |
| Telegram gagal | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `TELEGRAM_BLOCK_NOTIFY_ENABLED`, dan akses internet. |
| Notifikasi blokir tidak masuk | Dashboard harus sedang polling `/api/overview`; snapshot pertama hanya baseline, dan unblock menunggu IP hilang dari semua sumber. |
| Data berhenti lalu pulih | IP VM berubah karena DHCP; ganti `VM_HOST`/`RF_VM_HOST` atau jalankan `set_vm_host.ps1`, lalu restart dashboard. |

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

- Akses Wi-Fi/LAN langsung ke VM (tanpa tunnel).
- iperf3 client di laptop dan `iperf3 -s` di VM.
- `ping` bawaan Windows untuk pengukuran delay ICMP.
- Glances di VM untuk CPU/memori.
- systemd di VM untuk capture, fitur, RF API, Glances, dan iperf3.
- Telegram Bot API untuk test alert, notifikasi blokir/unblock, dan riwayat pengiriman.

## Struktur Dashboard

### Panel UI

| Panel | Isi | Sumber utama |
|---|---|---|
| Network Flow | Dropdown fitur dan line chart perubahan (hanya VM ML; Fail2Ban tanpa flow) | RF/LightGBM API `/api/features` |
| Telegram Alerts | Riwayat alert, notifikasi blokir/unblock, dan tombol test | Telegram API / memori proses |
| QoS Monitoring | Delay, jitter, packet loss, throughput | iperf3 dan ICMP ping |
| System Resource | CPU dan memori per host | Glances quicklook |
| Blocked IP | Daftar IP yang diblokir + hitung mundur auto-unblock | LightGBM `.69` + Random Forest `.70` + Fail2Ban `.71` `/api/blocked` |
| Attack History | Riwayat deteksi SSH brute force dan status blokir | RF API `/api/attacks` + LightGBM `.69` `/api/attacks` + Fail2Ban `.71` `/api/attacks` |

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
│  ├─ qos_scheduler.py       # scheduler pengukuran QoS otomatis
│  ├─ delay.py               # runner ping ICMP
│  ├─ blocked_notifier.py    # transisi blocked/unblock saat polling
│  ├─ telegram.py            # kirim alert + riwayat in-memory
│  └─ stats.py               # Min/Max/Avg
├─ templates/                # base, auth, dashboard, error
├─ static/
│  ├─ css/                   # tokens, base, components, dashboard, auth
│  ├─ js/                    # polling, charts, panels
│  └─ vendor/chart.umd.min.js
├─ deploy/
│  ├─ rf_api.py              # API RF read-only di VM random forest
│  ├─ lightgbm_api.py        # API LightGBM read-only di VM lightgbm (17 fitur)
│  ├─ fail2ban_api.py        # API blocked IP + QoS read-only di VM fail2ban
│  ├─ rf-api.env.example
│  ├─ lightgbm-api.env.example
│  ├─ fail2ban-api.env.example
│  ├─ glances-web.service    # unit systemd Glances web API
│  ├─ qos_probe.py           # probe QoS in-VM (iperf3 + ping ke peer)
│  ├─ qos-probe.service      # unit systemd probe QoS (VM ML)
│  ├─ qos-probe.timer        # timer probe tiap 10 detik (VM ML)
│  ├─ qos-probe-fail2ban.service # unit probe QoS VM fail2ban
│  ├─ qos-probe-fail2ban.timer   # timer probe VM fail2ban
│  ├─ ids-iperf3-local-udp2.service # server iperf3 UDP port 5203 (arah probe 2)
│  ├─ ids-iperf3-local.service # unit iperf3 server (build lokal /usr/local)
│  └─ ids-*.service          # unit systemd referensi
├─ scripts/
│  ├─ start_tunnel.ps1       # arsip tunnel SSH (tidak dipakai lagi)
│  └─ set_vm_host.ps1        # ganti IP VM di .env + cek konektivitas
├─ tests/                    # pytest
├─ instance/dashboard.db     # runtime, hanya akun
└─ .env                      # lokal, tidak di-commit
```

`instance/dashboard.db` hanya menyimpan tabel `users`. Riwayat QoS, attack, dan Telegram tidak dipersistenkan oleh dashboard; attack history diambil ulang dari RF API, sedangkan riwayat Telegram, baseline IP terblokir, dan sampel QoS berada di memori proses.

## Cara Kerja dan Alur Data

### Topologi

```text
VM 192.168.100.69 (lightgbm, Wi-Fi/LAN yang sama)
├─ capture/processed/*.csv ──► lightgbm_api.py :8080
│                                  ├─ GET /api/attacks  (model LightGBM)
│                                  └─ GET /api/features (17 fitur CSV)
├─ Glances :61208 (glances-web.service)
└─ iperf3 server :5201 (ids-iperf3-local.service)

VM 192.168.100.70 (random forest, Wi-Fi/LAN yang sama)
├─ capture/processed/*.csv ──► rf_api.py :8080
│                                  ├─ GET /api/attacks  (model RandomForestClassifier)
│                                  └─ GET /api/features (17 fitur CSV)
├─ Glances :61208 (glances-web.service)
└─ iperf3 server :5201 (ids-iperf3.service)

VM 192.168.100.71 (fail2ban, Wi-Fi/LAN yang sama)
├─ fail2ban-api :8080 (ids-fail2ban-api.service)
│    ├─ GET /api/blocked  (Bearer FAIL2BAN_API_TOKEN)
│    ├─ GET /api/attacks  (Ban/Unban dari fail2ban.log)
│    └─ GET /api/qos      (Bearer FAIL2BAN_API_TOKEN)
├─ Glances :61208 (glances-web.service)
└─ qos-probe-fail2ban.timer → /home/server/fail2ban/qos/*.json

Laptop monitoring (IP tidak dikonfigurasi)
├─ Flask dashboard :5000
├─ Akses langsung VM lightgbm
│  ├─ 192.168.100.69:8080 ──► LightGBM API (17 fitur)
│  └─ 192.168.100.69:61208 ──► Glances quicklook
├─ Akses langsung VM random forest
│  ├─ 192.168.100.70:8080 ──► RF API
│  └─ 192.168.100.70:61208 ──► Glances quicklook
├─ Akses langsung VM fail2ban
│  ├─ 192.168.100.71:8080 ──► Fail2Ban blocked + QoS API
│  └─ 192.168.100.71:61208 ──► Glances quicklook
├─ iperf3 client ──► 192.168.100.69/.70:5201
└─ ping ──► 192.168.100.69/.70
```

`192.168.56.102`/`.103` adalah target internal host-only yang terlihat pada data serangan dan dipakai probe QoS in-VM; `.104` adalah IP host-only VM Fail2Ban. Alamat host-only tidak dipakai laptop untuk mengakses dashboard. IP VM `192.168.100.69`/`.70`/`.71` didapat dari DHCP bridge; kalau berubah, cukup ganti `VM_HOST`/`RF_VM_HOST`/`FAIL2BAN_VM_HOST` di `.env`.

### Alur request

1. Laptop login ke Flask; session dan CSRF disimpan di cookie/session.
2. Browser membuka `/dashboard` dan memuat `static/js/dashboard.js`.
3. `Poller` memanggil `GET /api/overview` segera setelah halaman dibuka, lalu setiap `POLL_INTERVAL_MS` (default 5000 ms). Pilihan rentang grafik dikirim sebagai `range=5m|30m|1h`.
4. Route `/api/overview` memilih provider aktif:
   - `MockProvider` jika `DATA_MODE=demo`.
   - `LiveProvider` jika `DATA_MODE=live`.
5. `LiveProvider.get_overview()` mengambil data dari sumber eksternal dan menyusun payload per section.
6. Frontend `applyOverview()` memperbarui semua panel dan grafik tanpa reload halaman.
7. Jika tab browser disembunyikan, polling dihentikan sementara dan dilanjutkan saat tab aktif kembali.

### Sumber live per panel

- **Network Flow**: `GET /api/features?limit=200` dengan Bearer token. Endpoint dan token bisa berbeda per VM (`FLOW_FEATURES_*_URL` dan `FLOW_FEATURES_*_TOKEN`); kalau kosong, memakai `FLOW_FEATURES_API_URL` lalu `ATTACK_HISTORY_API_URL`, dan token memakai `FLOW_FEATURES_API_TOKEN` lalu `ATTACK_HISTORY_API_TOKEN`. Dashboard membentuk `series` per fitur, menghitung `current`, `previous`, dan `delta`. Event per VM disimpan di buffer in-memory (maks 4000, di-downsample saat penuh) lalu difilter sesuai rentang 5m/30m/1h; dropdown memilih satu fitur. Jika tidak ada event dalam rentang, chart menampilkan aktivitas terakhir (maks 50 event dalam jendela yang sama) dan sumber ditandai `event terakhir di luar rentang`. Jumlah fitur mengikuti sumber data (14 untuk VM random forest, 17 untuk VM lightgbm).
- **QoS**: histori probe in-VM dibaca dari `/api/qos` dan difilter sesuai rentang 5m/30m/1h. Runner iperf3 dan ping menyimpan sampel di memori. Tombol tes memulai thread background; hasil muncul pada polling berikutnya.
- **System Resource**: `GET /api/4/quicklook` per host Glances; fallback ke `/api/3/quicklook`.
- **Blocked IP**: gabungan `LIGHTGBM_BLOCKED_API_URL` (Bearer `LIGHTGBM_API_TOKEN`, fallback `FLOW_FEATURES_LIGHTGBM_TOKEN`), `RANDOM_FOREST_BLOCKED_API_URL` (Bearer `RANDOM_FOREST_API_TOKEN`, fallback `FLOW_FEATURES_RANDOM_FOREST_TOKEN` lalu `ATTACK_HISTORY_API_TOKEN`), dan `FAIL2BAN_API_URL` (Bearer `FAIL2BAN_API_TOKEN`). Hanya status blocked/banned/active yang ditampilkan, IP duplikat digabung dengan label sumbernya (mis. `LightGBM + Random Forest + Fail2Ban`), dan `unblock_at`/`remaining_seconds` dipakai untuk hitung mundur. Blokir tanpa jadwal tampil `Manual`; bila satu sumber gagal, sumber lain tetap tampil dengan peringatan. Respons juga memuat `total` dan `truncated`; daftar yang ditampilkan dibatasi 50 IP.
- **Attack History**: `GET /api/attacks`; hasil RF difilter model `RandomForestClassifier`/`RandomForest` dan prediction `SSH-Bruteforce`, lalu diurutkan terbaru. Sumber LightGBM digabung lewat `ATTACK_HISTORY_EXTRA_API_URLS`, dan Fail2Ban lewat `FAIL2BAN_ATTACKS_API_URL` (API `:8080/api/attacks`, Bearer `FAIL2BAN_API_TOKEN`); item dari semua sumber digabung dan diurutkan ulang berdasarkan waktu. Setiap sumber yang berhasil dijamin mendapat minimal satu slot dari 50 item, sehingga ban Fail2Ban tidak tertutup deteksi RF yang lebih rapat. Ban Fail2Ban tampil sebagai baris terpisah dengan `model: Fail2Ban`, sedangkan kolom Blocking memakai `blocking_status` dari sumbernya (membedakan `false` dari data tidak tersedia). Jika satu sumber gagal, panel tetap `ok` dari sumber lain dan baris "Sumber" menambah catatan `N sumber gagal`.
- **Telegram**: riwayat in-memory; test alert mengirim ke Telegram Bot API dari backend. Notifikasi blokir/unblock bersifat request-driven: hanya berjalan saat `/api/overview` dipolling, snapshot valid pertama menjadi baseline senyap, IP baru dikirim sebagai blokir (dengan label model), dan unblock dikirim setelah IP hilang dari semua sumber. Snapshot `warnings`/`truncated` menahan unblock agar tidak false-positive; pengiriman memakai worker queue agar polling tidak tertahan.

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

> Tombol "Jalankan tes iperf3" dan "Ukur delay" **tidak lagi ada di UI**: pengukuran
> QoS berjalan otomatis dari probe in-VM (lihat bagian *Pengukuran QoS di dalam
> VM*). Kedua endpoint tetap hidup dan bisa dipanggil langsung lewat API
> (menerima `?vm=<id>` untuk mengukur VM tertentu).

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

`GET /api/overview` menerima `range=5m|30m|1h` (default `5m`). Nilai lain
ditolak dengan HTTP 400 `invalid_range`. Field `range` dan
`stats_window_seconds` pada respons mengikuti pilihan tersebut.

Contoh ringkas `/api/overview`:

```json
{
  "generated_at": "2026-10-20T08:00:00Z",
  "data_mode": "live",
  "poll_interval_ms": 5000,
  "traffic": {
    "status": "ok",
    "source": "Random Forest flow features",
    "feature_count": 17,
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
  "blocked_ips": { "status": "unavailable", "items": [], "total": 0, "truncated": false },
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
| `GET` | `/api/attacks?limit=50` | Bearer token | Riwayat deteksi RF + `blocking_status` |
| `GET` | `/api/blocked?limit=50` | Bearer token | IP yang sedang diblokir + `unblock_at` |
| `GET` | `/api/features?limit=50` | Bearer token | 17 fitur flow dari CSV |

Ketentuan:

- `limit` 1-200, default 50.
- `/api/attacks` menerima model `RandomForestClassifier` dan alias runtime `RandomForest`, memfilter `prediction=SSH-Bruteforce`, lalu mengisi `blocking_status` dari `blocked_ips` (`true`/`false`/`null`).
- `/api/blocked` hanya mengirim baris berstatus `BLOCKED`; API tetap read-only dan tidak melakukan enforcement.
- `/api/features` membaca `capture/processed/*.csv`; direktori diatur `RF_API_FEATURES_DIR`.
- Token dibaca dashboard lewat `RANDOM_FOREST_API_TOKEN` untuk blocked IP, dan `ATTACK_HISTORY_API_TOKEN` untuk attacks/features.

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
  "blocking_status": false,
  "unblock_at": null
}
```

17 fitur yang dikembalikan `/api/features`:

```text
Protocol, Flow Duration, Tot Fwd Pkts, Tot Bwd Pkts, TotLen Fwd Pkts,
TotLen Bwd Pkts, Flow Pkts/s, Flow IAT Mean, Flow IAT Std, Fwd IAT Mean,
Bwd IAT Mean, Fwd Pkts/s, Bwd Pkts/s, ACK Flag Cnt, Init Fwd Win Byts,
Init Bwd Win Byts, Fwd Seg Size Min
```

### API LightGBM read-only di VM lightgbm

API terpisah di `deploy/lightgbm_api.py` untuk VM yang menjalankan model LightGBM. `LIGHTGBM_API_BIND` default `127.0.0.1`, hanya membaca data, dan memakai prefix env `LIGHTGBM_API_*`.

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| `GET` | `/health` | Tanpa token | Cek database |
| `GET` | `/api/attacks?limit=50` | Bearer token | Riwayat deteksi LightGBM + `blocking_status` |
| `GET` | `/api/blocked?limit=50` | Bearer token | IP yang sedang diblokir + `unblock_at` |
| `GET` | `/api/features?limit=50` | Bearer token | 17 fitur flow dari CSV |

Ketentuan:

- `limit` 1-200, default 50.
- `/api/attacks` memfilter `model=LightGBM` dan `prediction=SSH-Bruteforce`.
- `/api/attacks` mengisi `blocking_status` dari status terakhir IP di `blocked_ips`: `true` bila masih `BLOCKED`, `false` bila sudah `UNBLOCKED`, dan `null` bila IP belum pernah tercatat.
- `/api/blocked` mengembalikan `ip`, `blocked_at`, `last_seen_at`, `unblock_at`, `remaining_seconds`, `jail`, `reason`, `model`, `status`, dan `source`. Hanya baris berstatus `BLOCKED` yang dikirim.
- `/api/features` membaca `capture/processed/*.csv`; direktori diatur `LIGHTGBM_API_FEATURES_DIR`.
- Token dibaca dashboard lewat `FLOW_FEATURES_LIGHTGBM_TOKEN` (fallback `FLOW_FEATURES_API_TOKEN` lalu `ATTACK_HISTORY_API_TOKEN`).

17 fitur yang dikembalikan `/api/features`:

```text
Protocol, Flow Duration, Tot Fwd Pkts, Tot Bwd Pkts, TotLen Fwd Pkts,
TotLen Bwd Pkts, Flow Pkts/s, Flow IAT Mean, Flow IAT Std, Fwd IAT Mean,
Bwd IAT Mean, Fwd Pkts/s, Bwd Pkts/s, ACK Flag Cnt, Init Fwd Win Byts,
Init Bwd Win Byts, Fwd Seg Size Min
```

Deploy di VM lightgbm:

```bash
scp deploy/lightgbm_api.py server@192.168.100.69:/home/server/ids-backend/lightgbm_api.py
scp deploy/ids-lightgbm-api.service server@192.168.100.69:/tmp/ids-lightgbm-api.service
sudo cp /tmp/ids-lightgbm-api.service /etc/systemd/system/ids-lightgbm-api.service
sudo install -m 600 /dev/null /home/server/ids-backend/.lightgbm-api.env
sudo nano /home/server/ids-backend/.lightgbm-api.env   # isi LIGHTGBM_API_* dari deploy/lightgbm-api.env.example
sudo systemctl daemon-reload && sudo systemctl enable --now ids-lightgbm-api
curl.exe http://192.168.100.69:8080/health
```

Auto-unblock LightGBM dikonfigurasi di VM:

```bash
# /home/server/ids-backend/config/auto_block.json
{ "block_seconds": 10 }
```

- `capture/feature_worker.py` dan `services/auto_block_service.py` memanggil helper `/usr/local/sbin/ids-auto-block-ssh` dengan `block` lalu `unblock-after <ip> <detik>`.
- Setiap deteksi baru mereset timer. Durasi valid 1-31536000 detik; file dibaca ulang pada setiap deteksi.
- `database/database.py` menambahkan kolom `blocked_ips.unblock_at` secara idempotent saat `init_database()`.
- Jika pembuatan timer gagal, IP tetap diblokir permanen dan dashboard menampilkan `Manual`.
- Helper menulis/menghapus `unblock_at` saat `unblock-after`, `cancel-unblock`, `unblock`, dan `expire-unblock`.

Glances di VM yang sama (butuh API versi 4):

```bash
python3 -m venv /home/server/glances-venv
/home/server/glances-venv/bin/pip install "glances>=4,<5" fastapi uvicorn
scp deploy/glances-web.service server@192.168.100.69:/tmp/glances-web.service
sudo cp /tmp/glances-web.service /etc/systemd/system/glances-web.service
sudo systemctl daemon-reload && sudo systemctl enable --now glances-web
curl.exe http://192.168.100.69:61208/api/4/quicklook
```

### API Fail2Ban read-only di VM fail2ban

VM `192.168.100.71` menjalankan `fail2ban-api` (`:8080`) dan Glances (`:61208`). API berjalan sebagai root karena socket `fail2ban-client` hanya dapat diakses root; service memakai hardening read-only.

```bash
scp deploy/fail2ban_api.py server@192.168.100.71:/home/server/fail2ban/fail2ban_api.py
scp deploy/ids-fail2ban-api.service server@192.168.100.71:/tmp/ids-fail2ban-api.service
scp deploy/qos_probe.py server@192.168.100.71:/home/server/fail2ban/qos/qos_probe.py
scp deploy/qos-probe-fail2ban.service deploy/qos-probe-fail2ban.timer server@192.168.100.71:/tmp/
scp deploy/glances-web.service server@192.168.100.71:/tmp/glances-web.service

# Di VM: pasang unit + env token (nilai mengikuti deploy/fail2ban-api.env.example)
sudo install -m 600 /dev/null /home/server/fail2ban/.fail2ban-api.env
sudo nano /home/server/fail2ban/.fail2ban-api.env
sudo cp /tmp/ids-fail2ban-api.service /etc/systemd/system/
sudo cp /tmp/qos-probe-fail2ban.service /tmp/qos-probe-fail2ban.timer /etc/systemd/system/
sudo cp /tmp/glances-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now glances-web ids-fail2ban-api qos-probe-fail2ban.timer

# Setelah memperbarui fail2ban_api.py pada instalasi yang sudah berjalan:
sudo systemctl restart ids-fail2ban-api
```

Verifikasi:

```powershell
curl.exe http://192.168.100.71:8080/health
$token = "<token-dari-.env>"
curl.exe -H "Authorization: Bearer $token" http://192.168.100.71:8080/api/blocked
curl.exe -H "Authorization: Bearer $token" "http://192.168.100.71:8080/api/attacks?limit=50"
curl.exe -H "Authorization: Bearer $token" http://192.168.100.71:8080/api/qos
curl.exe http://192.168.100.71:61208/api/4/quicklook
```

`/api/blocked` mengembalikan `{ "generated_at", "source": "Fail2Ban", "items": [...] }`. Item berisi `ip`, `jail`, `blocked_at`, dan `status`; daftar kosong berarti belum ada IP yang sedang diblokir. Dashboard menggabungkannya dengan `/api/blocked` LightGBM dan Random Forest.

`/api/attacks?limit=50` membaca `/var/log/fail2ban.log` dan mengembalikan maksimal 50 event `Ban` terbaru sebagai riwayat serangan. `limit` 1-200, default 50; arsip rotasi mingguan belum dibaca. Setiap baris berisi `detected_at`, `source_ip`, `attack_type`, `detection`, `model: "Fail2Ban"`, `blocking_status`, dan `jail`; `blocking_status` bernilai `true` bila event terakhir IP tersebut adalah `Ban`, atau `false` bila sudah `Unban`. Jika log tidak terbaca, endpoint mengembalikan HTTP 503 `fail2ban_log_unavailable`. Dashboard memakai `FAIL2BAN_ATTACKS_API_URL` dengan Bearer `FAIL2BAN_API_TOKEN`.

`/api/qos` mengembalikan `probe` terakhir dan `history` dari timer `qos-probe-fail2ban` (target `192.168.56.102`, iperf3 `/usr/bin/iperf3`).

### Sumber eksternal lain

| Sumber | Endpoint | Auth | Dipakai untuk |
|---|---|---|---|
| Glances | `GET /api/4/quicklook` (fallback `/api/3/quicklook`) | — | CPU/memori host |
| LightGBM API | `192.168.100.69:8080/api/features` | Bearer token | 17 fitur flow VM lightgbm |
| LightGBM API | `192.168.100.69:8080/api/attacks` | Bearer token | Deteksi LightGBM (opsional) |
| LightGBM API | `192.168.100.69:8080/api/blocked` | Bearer `LIGHTGBM_API_TOKEN` | Blocked IP + jadwal auto-unblock |
| Random Forest API | `192.168.100.70:8080/api/blocked` | Bearer `RANDOM_FOREST_API_TOKEN` | Blocked IP + jadwal auto-unblock |
| Fail2Ban | `192.168.100.71:8080/api/blocked` | Bearer `FAIL2BAN_API_TOKEN` | Blocked IP |
| Fail2Ban | `192.168.100.71:8080/api/attacks` | Bearer `FAIL2BAN_API_TOKEN` | Riwayat Ban/Unban |
| Fail2Ban QoS | `192.168.100.71:8080/api/qos` | Bearer `FAIL2BAN_API_TOKEN` | Delay/jitter/loss/throughput VM Fail2Ban |
| iperf3 | `192.168.100.70:5201` TCP/UDP | — | Throughput/jitter |
| ICMP | `PING_TARGET_HOST` | — | Delay dan packet loss |
| Telegram | `POST https://api.telegram.org/bot<token>/sendMessage` | Bot token | Test alert + notifikasi blokir/unblock |
| Fallback iperf3 | `IPERF3_RESULT_URL` | — | Snapshot hasil iperf3 |
| Fallback delay | `DELAY_API_URL` | — | Sampel delay |

`LIGHTGBM_API_URL`, `RANDOM_FOREST_API_URL`, `API_BASE_URL`, dan `IPERF3_TEST_INTERVAL_SECONDS` masih ada di konfigurasi, tetapi belum dipakai oleh provider live saat ini. Gunakan `ATTACK_HISTORY_API_URL` dan `FLOW_FEATURES_API_URL` untuk integrasi RF yang aktif.

## Konfigurasi Ringkas Mode Live

Salin `.env.example` ke `.env`, lalu isi nilai berikut. Jangan menulis token nyata ke README atau commit `.env`.

```dotenv
DATA_MODE=live
SECRET_KEY=<hasil-generate-acak>
DATABASE_PATH=instance/dashboard.db

VM_HOST=192.168.100.69
RF_VM_HOST=192.168.100.70

GLANCES_RANDOM_FOREST_URL=http://${RF_VM_HOST}:61208
GLANCES_RANDOM_FOREST_LABEL=randomforest-vm

ATTACK_HISTORY_API_URL=http://${RF_VM_HOST}:8080/api/attacks
ATTACK_HISTORY_API_TOKEN=<token-yang-sama-dengan-RF_API_TOKEN>
FLOW_FEATURES_API_URL=http://${RF_VM_HOST}:8080/api/features

IPERF3_ENABLED=true
IPERF3_BINARY=C:\path\lengkap\iperf3.exe
IPERF3_SERVER_HOST=${VM_HOST}
IPERF3_PORT=5201
IPERF3_TEST_PROTOCOL=udp
IPERF3_BANDWIDTH=100M

PING_TARGET_HOST=${VM_HOST}

# VM lightgbm (akses langsung, satu variabel IP)
FLOW_FEATURES_LIGHTGBM_URL=http://${VM_HOST}:8080/api/features
FLOW_FEATURES_LIGHTGBM_TOKEN=<token-dari-.lightgbm-api.env>
GLANCES_LIGHTGBM_URL=http://${VM_HOST}:61208
ATTACK_HISTORY_EXTRA_API_URLS=http://${VM_HOST}:8080/api/attacks
ATTACK_HISTORY_EXTRA_API_TOKENS=<token-dari-.lightgbm-api.env>
LIGHTGBM_BLOCKED_API_URL=http://${VM_HOST}:8080/api/blocked
LIGHTGBM_API_TOKEN=<token-dari-.lightgbm-api.env>
QOS_VM=lightgbm-vm
QOS_SOURCE_MODE=vm
QOS_AUTO_ENABLED=true
QOS_AUTO_INTERVAL_SECONDS=5
QOS_AUTO_METRICS=ping,iperf3
QOS_LOCAL_PROBE=false

# VM fail2ban (blocked IP + attack history + QoS, tanpa Network Flow)
FAIL2BAN_VM_HOST=192.168.100.71
FAIL2BAN_API_URL=http://${FAIL2BAN_VM_HOST}:8080/api/blocked
FAIL2BAN_ATTACKS_API_URL=http://${FAIL2BAN_VM_HOST}:8080/api/attacks
FAIL2BAN_API_TOKEN=<token-dari-.fail2ban-api.env>
GLANCES_FAIL2BAN_URL=http://${FAIL2BAN_VM_HOST}:61208
QOS_VMS=lightgbm-vm,randomforest-vm,fail2ban-vm
```

Catatan:

- Semua URL VM memakai `${VM_HOST}` / `${RF_VM_HOST}` / `${FAIL2BAN_VM_HOST}`, jadi tidak ada IP yang ditulis dua kali.
- IP laptop tidak dikonfigurasi di mana pun; perubahan IP laptop karena DHCP tidak perlu edit `.env`.
- `VM_HOST`, `RF_VM_HOST`, dan `FAIL2BAN_VM_HOST` harus ditulis **di atas** pemakaiannya karena `python-dotenv` menyelesaikan variabel sesuai urutan file.
- `ATTACK_HISTORY_API_TOKEN` harus sama dengan `RF_API_TOKEN` di `/home/server/ids-backend/.rf-api.env`.
- `FLOW_FEATURES_API_TOKEN` boleh dikosongkan; backend akan memakai token attack history.
- Glances LightGBM/RF/Fail2Ban hanya perlu diisi jika host tersebut tersedia.
- `.env` berisi secret dan sudah masuk `.gitignore`.

## Tiga VM Lab, QoS Otomatis, dan Jalur Akses

### Satu variabel IP per VM

Semua URL yang menunjuk VM memakai `${VM_HOST}`, `${RF_VM_HOST}`, atau `${FAIL2BAN_VM_HOST}`, jadi IP hanya ditulis sekali di `.env` (baris IP harus berada **di atas** pemakaiannya karena `python-dotenv` menyelesaikan variabel sesuai urutan file):

```dotenv
VM_HOST=192.168.100.69            # VM lightgbm
RF_VM_HOST=192.168.100.70         # VM random forest
FAIL2BAN_VM_HOST=192.168.100.71   # VM fail2ban

# VM lightgbm
FLOW_FEATURES_LIGHTGBM_URL=http://${VM_HOST}:8080/api/features
GLANCES_LIGHTGBM_URL=http://${VM_HOST}:61208
ATTACK_HISTORY_EXTRA_API_URLS=http://${VM_HOST}:8080/api/attacks
LIGHTGBM_BLOCKED_API_URL=http://${VM_HOST}:8080/api/blocked
LIGHTGBM_API_TOKEN=<token-dari-.lightgbm-api.env>
IPERF3_SERVER_HOST=${VM_HOST}
PING_TARGET_HOST=${VM_HOST}

# VM random forest
ATTACK_HISTORY_API_URL=http://${RF_VM_HOST}:8080/api/attacks
FLOW_FEATURES_API_URL=http://${RF_VM_HOST}:8080/api/features
GLANCES_RANDOM_FOREST_URL=http://${RF_VM_HOST}:61208

# VM fail2ban (blocked IP + QoS; tanpa Network Flow)
FAIL2BAN_API_URL=http://${FAIL2BAN_VM_HOST}:8080/api/blocked
FAIL2BAN_API_TOKEN=<token-dari-.fail2ban-api.env>
GLANCES_FAIL2BAN_URL=http://${FAIL2BAN_VM_HOST}:61208
QOS_VMS=lightgbm-vm,randomforest-vm,fail2ban-vm
```

Saat IP VM berubah, ganti satu baris atau pakai helper:

```powershell
.\scripts\set_vm_host.ps1 192.168.100.69                         # VM lightgbm
.\scripts\set_vm_host.ps1 -Variable RF_VM_HOST 192.168.100.70    # VM random forest
.\scripts\set_vm_host.ps1 -Variable FAIL2BAN_VM_HOST 192.168.100.71 # VM fail2ban
```

Script itu menulis ulang satu baris variabel yang dipilih, lalu memeriksa ping, port `8080`/`61208`/`5201`, `/health`, dan `quicklook`. Tidak ada rule firewall yang perlu diubah karena `ufw` di ketiga VM nonaktif. Setelah itu restart dashboard agar `.env` dibaca ulang.

### Aturan yang sama untuk ketiga VM

| # | Aturan | lightgbm (192.168.100.69) | random forest (192.168.100.70) | fail2ban (192.168.100.71) |
|---|---|---|---|---|
| 1 | Satu variabel IP per VM di `.env`, dipakai `${VAR}` di semua URL | `VM_HOST` | `RF_VM_HOST` | `FAIL2BAN_VM_HOST` |
| 2 | Semua service listen di `0.0.0.0` → IP/subnet berubah tanpa edit di VM | `ids-lightgbm-api`, `glances-web`, `ids-iperf3-local` | `ids-rf-api`, `glances-web`, `ids-iperf3` | `ids-fail2ban-api`, `glances-web`, `qos-probe-fail2ban.timer` |
| 3 | `ufw` nonaktif (allow all); tidak ada rule yang perlu diubah saat IP/subnet berpindah | — | **identik** | **identik** |
| 4 | Token per VM | `FLOW_FEATURES_LIGHTGBM_TOKEN`, `ATTACK_HISTORY_EXTRA_API_TOKENS` | `ATTACK_HISTORY_API_TOKEN` (sama dengan nilai di `.rf-api.env` VM) | `FAIL2BAN_API_TOKEN` |
| 5 | Helper `set_vm_host.ps1` (+ `-Variable`) | ✓ | ✓ | ✓ |
| 6 | Tanpa dependensi IP laptop (rule per-subnet, bukan per-IP) | ✓ | ✓ | ✓ |

### Matriks perubahan IP

Tidak semua alamat perlu disentuh. Yang penting: **semua service di VM listen di `0.0.0.0`**, `IPERF3_OMIT_SECONDS=0`, dan Windows Firewall mengizinkan `iperf3.exe` untuk semua profil.

| Yang berubah | Yang perlu diubah | Cara |
|---|---|---|
| **IP VM berubah, subnet sama** | `VM_HOST=` atau `RF_VM_HOST=` di `.env` (1 baris per VM) | `.\scripts\set_vm_host.ps1 <ip>` atau `... -Variable RF_VM_HOST <ip>`, lalu restart dashboard |
| **IP VM berubah, subnet juga berubah** | variabel IP di `.env` | Tidak ada rule firewall yang perlu diubah (`ufw` nonaktif) |
| **IP laptop berubah** | **tidak ada** | Tidak ada konfigurasi yang menyebut IP laptop; tidak ada rule firewall per-IP |
| **Laptop pindah Wi-Fi, VM ikut jaringan yang sama** | **tidak ada** | Akses langsung lewat IP VM; tidak ada route/tunnel yang perlu diubah |
| **Subnet Wi-Fi berubah** | IP VM di `.env` | `ufw` nonaktif, jadi tidak ada rule subnet baru yang perlu ditambahkan |

`ufw` di ketiga VM nonaktif (`Status: inactive`), sehingga IP DHCP dan subnet bebas berubah tanpa mengubah konfigurasi firewall.


Sisi VM tidak perlu diubah saat IP berpindah karena semua service listen di `0.0.0.0`:

| Service | Unit di VM | Listen | Catatan |
|---|---|---|---|
| LightGBM API | `ids-lightgbm-api` (system) | `0.0.0.0:8080` | `LIGHTGBM_API_BIND=0.0.0.0` di `.lightgbm-api.env` |
| RF API | `ids-rf-api` (user) | `0.0.0.0:8080` | `RF_API_BIND=0.0.0.0` di `.rf-api.env`; `rf_api.py` 17 fitur |
| Glances | `glances-web` (system) | `0.0.0.0:61208` | unit `deploy/glances-web.service` (Glances 4.5.8, API v4) |
| iperf3 | `ids-iperf3-local` (system) | `*:5201` | unit `deploy/ids-iperf3-local.service` (iperf3 3.22) |
| iperf3 TCP | `ids-iperf3-local` (system) | `*:5201` | iperf3 3.22, `--idle-timeout 60` |
| iperf3 UDP | `ids-iperf3-local-udp` (system) | `*:5202` | profil jitter, port terpisah (loss UDP cadangan) |
| iperf3 UDP (arah 2) | `ids-iperf3-local-udp2` (system) | `*:5203` | port UDP untuk arah probe sebaliknya |
| Fail2Ban API | `ids-fail2ban-api` (system) | `0.0.0.0:8080` | `/api/blocked` + `/api/attacks` + `/api/qos`, Bearer `FAIL2BAN_API_TOKEN` |
| Probe QoS Fail2Ban | `qos-probe-fail2ban.timer` + `qos-probe-fail2ban.service` (system) | — | probe in-VM tiap 10 dtk → `/home/server/fail2ban/qos/*.json` |
| Probe QoS ML | `qos-probe.timer` + `qos-probe.service` (system) | — | probe in-VM tiap 10 dtk → `qos/*.json` |

### Firewall VM

`ufw` di **ketiga VM** nonaktif dan service-nya tidak dijalankan saat boot. Semua port service (API `8080`, Glances `61208`, iperf3 `5201`–`5203`) terbuka untuk siapa pun di jaringan, jadi perubahan IP atau subnet DHCP tidak memerlukan rule baru.

Konfigurasi ini hanya untuk jaringan lab. Jangan mengekspos VM ke internet.

Port `5201/udp` wajib ada untuk data iperf3; tanpa itu client menunggu laporan server sampai timeout.

### Pengukuran QoS di dalam VM (menggambarkan beban saat serangan)

Panel QoS **tidak** mengukur jalur laptop→VM, melainkan **diukur di dalam VM**
lewat `deploy/qos_probe.py` (dijalankan `qos-probe.timer` untuk VM ML dan
`qos-probe-fail2ban.timer` untuk VM Fail2Ban, tiap 10 detik). Probe mengukur ke
VM peer lewat **interface host-only VirtualBox** (`192.168.56.0/24`) — link yang
sama dipakai trafik SSH brute force dan dibaca pipeline ML. Jadi
delay/jitter/packet-loss/throughput di panel menggambarkan beban pada jalur yang
diproses deteksi ML (probe Fail2Ban memakai link host-only yang sama sebagai
pembanding), bukan beban jaringan laptop.

Probe menulis dua file di `qos/` (di luar `capture/`, jadi tidak pernah disentuh
worker ML):

| File | Isi |
|---|---|
| `qos/last.json` | Hasil probe terakhir |
| `qos/history.json` | Riwayat probe (480 titik = 80 menit @10 detik), ditulis atomik |

Dashboard membentuk seri grafik dari `history.json` sesuai rentang yang dipilih
(5 menit, 30 menit, atau 1 jam), sehingga grafik QoS bisa menampilkan seluruh
durasi pengujian.

Isi satu titik probe:

| Metrik | Cara ukur | Port |
|---|---|---|
| `delay_ms` | ICMP ping ke peer | — |
| `packet_loss_percent` | ICMP ping ke peer (10 paket, interval 0.2 dtk) | — |
| `jitter_ms` | iperf3 UDP 1 Mbps | `5202` / `5203` (per arah) |
| `throughput_mbps` | iperf3 TCP | `5201` |

Packet loss memakai ping sebagai sumber utama; loss UDP hanya fallback bila
ICMP tidak tersedia. Nilai ping juga disimpan sebagai
`ping_packet_loss_percent`, sedangkan loss UDP tetap ada di
`udp_packet_loss_percent` pada `last.json`.

Endpoint baca-saja `GET /api/qos` di kedua API VM juga mengembalikan
`load` (loadavg), `network` (counter `enp0s8`: rx/tx/error/drop) dan
`capture_backlog` (jumlah & umur PCAP yang menunggu diproses) — untuk melihat
apakah pipeline ML tertinggal saat server kewalahan.

Proteksi agar pipeline ML tidak terganggu:

1. Probe memakai port `5201`/`5202`, sedangkan `ids-tcpdump` hanya menangkap
   `tcp port 22` → trafik probe **tidak pernah** masuk `capture/raw`.
2. Folder hasil probe `qos/` berada **di luar** `capture/`.
3. Probe ringan (1 Mbps, 2–3 detik, tiap 10 detik) dan diberi `Nice=10` +
   `CPUWeight=10` sehingga tidak merebut sumber daya dari worker ML.
4. Server iperf3 TCP (`5201`) dan UDP (`5202`/`5203`) dipisah, memakai
   `--idle-timeout 60` agar sesi yang nyangkut tidak memblokir server.
   Probe **saling mengukur** dengan port UDP berbeda per arah: probe VM
   lightgbm memakai `5203` di VM random forest, probe VM random forest memakai
   `5202` di VM lightgbm — sehingga tidak pernah mengukur ke server yang
   sedang dipakai probe dari arah sebaliknya.
5. Probe dari laptop dimatikan saat `QOS_SOURCE_MODE=vm`
   (`QOS_LOCAL_PROBE=false`) supaya tidak berebut port iperf3 dengan probe
   in-VM.

Arah pengukuran (saling mengukur lewat host-only):

```text
VM random forest 192.168.56.103  ──probe──►  VM lightgbm 192.168.56.102
VM lightgbm     192.168.56.102  ──probe──►  VM random forest 192.168.56.103
VM fail2ban     192.168.56.104  ──probe──►  VM lightgbm 192.168.56.102
```

Dampak serangan pada pipeline ML terukur di `capture_backlog.oldest_age_seconds`
(umur PCAP tertua) dan `network.enp0s8` (`tx_errors`/`rx_dropped`).

### Jalur capture IDS

`ids-tcpdump` di kedua VM menangkap di interface **host-only** (`-i enp0s8`, yaitu `192.168.56.0/24`) dengan filter `tcp port 22`. Interface host-only harus tetap aktif agar trafik serangan masuk ke pipeline fitur maupun `detection_logs`; `ufw` nonaktif sehingga tidak memblokir trafik tersebut.

### Server iperf3 di VM lightgbm

Versi di repositori Ubuntu (3.9) sering membuat client Windows menutup control socket lebih dulu. VM memakai build 3.22 yang sama dengan client:

```bash
curl -sSL -o /tmp/iperf-3.22.tar.gz https://github.com/esnet/iperf/archive/refs/tags/3.22.tar.gz
cd /tmp && tar xzf iperf-3.22.tar.gz && cd iperf-3.22
./configure --prefix=/usr/local && make -j4 && sudo make install
sudo cp /tmp/ids-iperf3-local.service /etc/systemd/system/ids-iperf3-local.service
sudo systemctl daemon-reload && sudo systemctl enable --now ids-iperf3-local
```

### QoS otomatis (per VM)

`QOS_AUTO_ENABLED=true` membuat `services/qos_scheduler.py` menjalankan pengukuran sendiri tiap `QOS_AUTO_INTERVAL_SECONDS` tanpa perlu menekan tombol, tetapi hanya jika `QOS_LOCAL_PROBE=true`. Pada konfigurasi saat ini `QOS_LOCAL_PROBE=false`, jadi angka QoS berasal dari probe in-VM. Scheduler hanya berjalan di mode `live` dan tidak aktif saat `TESTING`.

QoS diukur **per VM**: `QOS_VMS` mendaftarkan VM yang diukur, dan target ping/iperf3 tiap VM diambil dari `VM_HOST` (lightgbm), `RF_VM_HOST` (random forest), dan `FAIL2BAN_VM_HOST` (fail2ban) — jadi hanya ada satu tempat per IP. Untuk ketiga VM, panel membaca histori dari `/api/qos` in-VM; scheduler laptop hanya aktif bila `QOS_LOCAL_PROBE=true`. Panel QoS memakai runner milik VM yang sedang dipilih, dan tombol manual mengukur VM terpilih.

Dua profil iperf3 berjalan supaya keempat metrik tetap terpantau:

| Profil | Protokol | Port | Cadangan | Interval | Menghasilkan |
|---|---|---|---|---|---|
| Throughput | `tcp` (`QOS_AUTO_IPERF3_PROTOCOL`) | `5201` | `QOS_AUTO_IPERF3_BANDWIDTH` | tiap `QOS_AUTO_INTERVAL_SECONDS` + cooldown | Throughput |
| Jitter | `udp` | `5202` (`QOS_AUTO_LOSS_PORT`) | `QOS_AUTO_LOSS_BANDWIDTH` | tiap `QOS_AUTO_LOSS_INTERVAL_SECONDS` | Jitter (loss UDP cadangan) |

Di mode `QOS_SOURCE_MODE=vm`, **packet loss** diambil dari probe ICMP ping
in-VM setiap 10 detik, bukan dari profil UDP di atas; profil UDP tetap dipakai
untuk jitter.

Kedua profil memakai **server iperf3 terpisah** (`ids-iperf3-local` di `:5201` dan `ids-iperf3-local-udp` di `:5202`) dengan `--idle-timeout 60`. Pemisahan port ini penting: kalau tes UDP macet, sesi itu hanya memblokir port UDP — tes TCP (throughput) tetap jalan. Dengan satu port, sesi UDP yang macet membuat server melapor `the server is busy` dan throughput ikut hilang.

Profil UDP hanya dijalankan untuk **VM yang sedang dibuka** di dashboard (backend mencatat VM dari poll `/api/overview?vm=...`; halaman Security yang poll tanpa `vm` tidak mengubahnya). Jadi jitter yang tampil adalah milik VM aktif, dan angka VM lain membeku selama tabnya tidak dibuka. Packet loss tetap mengikuti probe ICMP in-VM untuk VM yang dipilih.

> TCP dipilih untuk profil throughput karena lebih andal; profil UDP terpisah (dengan laju kecil & jadwal sendiri) dipakai khusus untuk jitter. Packet loss berasal dari ping probe in-VM.

| Variabel | Default | Fungsi |
|---|---|---|
| `QOS_AUTO_ENABLED` | `false` | Mengaktifkan mode otomatis |
| `QOS_AUTO_INTERVAL_SECONDS` | `5` | Interval tick |
| `QOS_AUTO_METRICS` | `ping,iperf3` | Metrik yang dijalankan |
| `QOS_AUTO_IPERF3_DURATION_SECONDS` | `0` (pakai `IPERF3_TEST_DURATION_SECONDS`) | Durasi tes mode otomatis |
| `QOS_AUTO_IPERF3_BANDWIDTH` | kosong (pakai `IPERF3_BANDWIDTH`) | Bandwidth mode otomatis |
| `QOS_AUTO_IPERF3_COOLDOWN_SECONDS` | `2` | Jeda minimal setelah tes sebelumnya |

Label di pojok toolbar panel QoS berubah dari `Manual` menjadi `Otomatis · 5 dtk` saat mode otomatis aktif.

Catatan praktis:

- Server iperf3 hanya melayani satu tes pada satu waktu, jadi scheduler menunggu `durasi + cooldown` sebelum tes berikutnya.
- `IPERF3_OMIT_SECONDS=0` dipakai agar sebagian besar sampel tes ikut terhitung.
- Windows Firewall harus mengizinkan inbound `iperf3.exe` pada semua profil jaringan:
  ```powershell
  New-NetFirewallRule -DisplayName "iperf3.exe inbound (all profiles)" -Direction Inbound `
    -Program "C:\Users\eka\AppData\Local\Microsoft\WinGet\Packages\ar51an.iPerf3_Microsoft.Winget.Source_8wekyb3d8bbwe\iperf3.exe" `
    -Action Allow -Profile Any
  ```
- Cepatkan atau matikan: `QOS_AUTO_INTERVAL_SECONDS`, `QOS_AUTO_METRICS=ping`, atau `QOS_AUTO_ENABLED=false`.
- Histori QoS hanya di memori proses; restart dashboard mengosongkan seri.

### Jalur akses: LAN langsung

Laptop dan ketiga VM berada di Wi-Fi/LAN yang sama. Dashboard mengakses LightGBM (`192.168.100.69`), random forest (`192.168.100.70`), dan fail2ban (`192.168.100.71`) langsung tanpa Tailscale atau tunnel SSH.

| Yang berubah | Detail |
|---|---|
| Routing laptop | Tidak ada konfigurasi khusus; pastikan satu subnet dengan VM |
| `.env` | Hanya `VM_HOST` / `RF_VM_HOST` / `FAIL2BAN_VM_HOST`; IP laptop tidak disimpan |
| Firewall VM | `ufw` nonaktif; tidak ada rule yang perlu diubah |
| Kode dashboard | Tidak ada perubahan |
| Angka QoS | Probe in-VM tetap memakai link host-only `192.168.56.0/24` (jalur yang diproses ML), bukan jalur laptop |

Jika IP VM berubah akibat DHCP, ganti satu baris di `.env` atau jalankan `scripts/set_vm_host.ps1`, lalu restart dashboard. `ufw` di VM nonaktif, jadi perubahan IP/subnet tidak memerlukan rule firewall baru.

## Autostart Dashboard dan VM

### Dashboard di laptop

Dashboard Flask tidak start otomatis. Buat Scheduled Task terpisah jika ingin ikut start saat login:

```powershell
$project = "$env:USERPROFILE\PycharmProjects\Dashboard"
$action = New-ScheduledTaskAction -Execute "$project\.venv\Scripts\pythonw.exe" `
  -Argument "app.py" -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "SSH Sentinel Dashboard" `
  -Action $action -Trigger $trigger -Force
```

Tunnel SSH dan Tailscale tidak dipakai lagi. `scripts/start_tunnel.ps1` disimpan hanya sebagai arsip/referensi dan tidak perlu dijalankan atau dijadwalkan.

### Service VM

| Unit | Jenis | Fungsi |
|---|---|---|
| `ids-tcpdump` | system | Capture trafik |
| `ids-pcap-worker` | system | Pemrosesan PCAP |
| `ids-feature-worker` | system | Pembentukan fitur flow |
| `glances` / `glances-qos-api` | system | Metrik resource |
| `ids-rf-api` | user | API RF read-only `:8080` |
| `ids-lightgbm-api` | system | API LightGBM read-only `:8080` (VM lightgbm) |
| `glances-web` | system | Glances web API `:61208` (VM lightgbm, unit di `deploy/glances-web.service`) |
| `ids-iperf3` | user | Server iperf3 `:5201` |

Service user berada di `~/.config/systemd/user/` dan berjalan karena linger aktif. Perintah cek/restart:

```bash
systemctl --user is-enabled ids-rf-api.service ids-iperf3.service
systemctl --user restart ids-rf-api.service ids-iperf3.service
journalctl --user -u ids-rf-api.service -n 50
```

Setelah VM reboot, pastikan service kembali `active`. Dashboard akan terhubung lagi pada polling berikutnya; tidak ada tunnel yang perlu dipulihkan.

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
| Telegram: status/riwayat + test alert + notifikasi blokir/unblock | Selesai (simulasi di mode demo) |
| Adapter API live | RF API (attack + blocked), LightGBM, Glances, dan Fail2Ban (blocked + QoS) terintegrasi |
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

Bagian ini adalah referensi lama untuk alat ukur di laptop. Pada topologi saat ini Glances berjalan di dalam VM dan diakses langsung di `192.168.100.69:61208` / `192.168.100.70:61208`; lihat panduan di atas.

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

Contoh konfigurasi live minimal:

```dotenv
DATA_MODE=live
GLANCES_LIGHTGBM_URL=http://${VM_HOST}:61208
GLANCES_LIGHTGBM_LABEL=lightgbm-vm
IPERF3_ENABLED=true
IPERF3_SERVER_HOST=${VM_HOST}
IPERF3_TEST_PROTOCOL=udp
IPERF3_BANDWIDTH=100M
PING_TARGET_HOST=${VM_HOST}
```

## Konfigurasi

Semua konfigurasi dibaca dari `.env` melalui `config.py`. Jangan commit `.env` berisi secret.

| Variabel | Default | Keterangan |
|---|---|---|
| `SECRET_KEY` | `dev-only-change-me` | Wajib diganti untuk deployment |
| `DATABASE_PATH` | `instance/dashboard.db` | SQLite khusus akun |
| `DATA_MODE` | `demo` | `demo` atau `live` |
| `POLL_INTERVAL_MS` | `5000` | Interval polling UI |
| `STATS_WINDOW_SECONDS` | `300` | Jendela fallback bila `range` tidak dikirim |
| `HISTORY_MAX_POINTS` | `900` | Retensi sampel in-memory resource/traffic (cukup 1 jam @5 detik) |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` saat memakai HTTPS |
| `CSRF_ENABLED` | `true` | Proteksi form/aksi POST |
| `LIGHTGBM_API_URL`, `RANDOM_FOREST_API_URL` | kosong | Reserved; belum dipakai provider live saat ini |
| `LIGHTGBM_BLOCKED_API_URL` | kosong | Endpoint blocked IP LightGBM `http://${VM_HOST}:8080/api/blocked` |
| `LIGHTGBM_API_TOKEN` | kosong | Bearer token blocked IP LightGBM; fallback ke `FLOW_FEATURES_LIGHTGBM_TOKEN` |
| `RANDOM_FOREST_BLOCKED_API_URL` | kosong | Endpoint blocked IP Random Forest `http://${RF_VM_HOST}:8080/api/blocked` |
| `RANDOM_FOREST_API_TOKEN` | kosong | Bearer token blocked IP Random Forest; fallback ke `FLOW_FEATURES_RANDOM_FOREST_TOKEN` lalu `ATTACK_HISTORY_API_TOKEN` |
| `FAIL2BAN_VM_HOST` | kosong | IP VM Fail2Ban; dipakai `${FAIL2BAN_VM_HOST}` di URL |
| `FAIL2BAN_API_TOKEN` | kosong | Bearer token API blocked + attack history + QoS VM Fail2Ban |
| `FAIL2BAN_API_URL` | kosong | Sumber daftar IP terblokir `http://${FAIL2BAN_VM_HOST}:8080/api/blocked` |
| `FAIL2BAN_ATTACKS_API_URL` | kosong | Sumber riwayat Ban/Unban `http://${FAIL2BAN_VM_HOST}:8080/api/attacks` |
| `GLANCES_FAIL2BAN_URL` | kosong | Glances VM Fail2Ban `http://${FAIL2BAN_VM_HOST}:61208` |
| `ATTACK_HISTORY_API_URL` | kosong | Sumber riwayat serangan |
| `ATTACK_HISTORY_API_TOKEN` | kosong | Token Bearer untuk API attack history; hanya backend |
| `ATTACK_HISTORY_EXTRA_API_URLS` | kosong | Sumber deteksi tambahan (dipisah koma), digabung dengan sumber utama |
| `ATTACK_HISTORY_EXTRA_API_TOKENS` | kosong | Token untuk sumber tambahan, sepadan urutan dengan URL |
| `FLOW_FEATURES_API_URL` | kosong | Endpoint 17 fitur flow Random Forest |
| `FLOW_FEATURES_API_TOKEN` | kosong | Opsional; fallback ke `ATTACK_HISTORY_API_TOKEN` |
| `FLOW_FEATURES_*_URL` | kosong | Endpoint flow features per VM (`LIGHTGBM`, `RANDOM_FOREST`, `FAIL2BAN`) |
| `FLOW_FEATURES_*_TOKEN` | kosong | Token Bearer per VM; fallback ke `FLOW_FEATURES_API_TOKEN` lalu `ATTACK_HISTORY_API_TOKEN` |
| `GLANCES_*_URL` | kosong | Base URL Glances per VM/laptop (`quicklook` API) |
| `GLANCES_*_LABEL` | nama host | Label host yang ditampilkan di UI |
| `QOS_HISTORY_POINTS` | `480` | Retensi titik runner QoS manual (80 menit @10 detik) |
| `QOS_VM` | `randomforest-vm` | VM legacy bila `QOS_VMS` kosong |
| `QOS_AUTO_ENABLED` | `false` | Scheduler otomatis menjalankan pengukuran QoS |
| `QOS_AUTO_INTERVAL_SECONDS` | `5` | Interval tick scheduler otomatis |
| `QOS_AUTO_METRICS` | `ping,iperf3` | Metrik yang dijalankan otomatis |
| `QOS_AUTO_IPERF3_DURATION_SECONDS` | `0` (pakai `IPERF3_TEST_DURATION_SECONDS`) | Durasi tes iperf3 mode otomatis |
| `QOS_AUTO_IPERF3_BANDWIDTH` | kosong (pakai `IPERF3_BANDWIDTH`) | Bandwidth iperf3 mode otomatis |
| `QOS_AUTO_IPERF3_COOLDOWN_SECONDS` | `2` | Jeda minimal sebelum iperf3 berikutnya |
| `QOS_VMS` | kosong | VM yang diukur QoS-nya (csv); contoh `lightgbm-vm,randomforest-vm,fail2ban-vm` |
| `QOS_AUTO_IPERF3_PROTOCOL` | `tcp` | Protokol iperf3 mode otomatis (tcp lebih andal lewat relay) |
| `QOS_AUTO_LOSS_ENABLED` | `true` | Jalankan tes UDP ringan untuk jitter (loss UDP cadangan) |
| `QOS_AUTO_LOSS_DURATION_SECONDS` | `2` | Durasi tes jitter UDP |
| `QOS_AUTO_LOSS_BANDWIDTH` | `1M` | Bandwidth tes jitter UDP |
| `QOS_AUTO_LOSS_INTERVAL_SECONDS` | `10` | Interval tes jitter UDP (terpisah dari tes throughput) |
| `QOS_AUTO_LOSS_PORT` | `5202` | Port server iperf3 untuk profil UDP |
| `QOS_SOURCE_MODE` | `vm` | Sumber angka QoS: `vm` = probe in-VM, `laptop` = probe dari laptop |
| `QOS_LOCAL_PROBE` | `false` | Jalankan probe iperf3/ping dari laptop (hanya saat sumber = laptop) |
| `QOS_PROBE_INTERVAL_SECONDS` | `10` | Interval probe in-VM; harus sama dengan `qos-probe.timer` (ping loss: 10 paket @0.2 dtk) |
| `VM_HOST` | kosong | IP VM lightgbm; dipakai `${VM_HOST}` pada URL sumber data VM tersebut |
| `RF_VM_HOST` | kosong | IP VM random forest; dipakai `${RF_VM_HOST}` pada URL sumber data VM tersebut |
| `IPERF3_ENABLED` | `false` | Aktifkan runner iperf3 |
| `IPERF3_BINARY` | `iperf3` | Nama/path binari iperf3 |
| `IPERF3_SERVER_HOST`, `IPERF3_PORT` | kosong, `5201` | Host server iperf3 tujuan |
| `IPERF3_TEST_PROTOCOL`, `IPERF3_BANDWIDTH` | `udp`, `100M` | Jitter/loss hanya dari UDP; bandwidth target UDP |
| `IPERF3_TEST_DURATION_SECONDS`, `IPERF3_OMIT_SECONDS` | `10`, `1` | Durasi tes dan detik pemanasan yang diabaikan |
| `IPERF3_TIMEOUT_MARGIN_SECONDS` | `30` | Batas waktu tambahan sebelum proses iperf3 dihentikan |
| `IPERF3_RESULT_URL` | kosong | Fallback membaca snapshot hasil iperf3 |
| `DELAY_API_URL` | kosong | Fallback sumber delay terpisah |
| `PING_TARGET_HOST`, `PING_COUNT` | kosong, `5` | Target dan jumlah paket ICMP |
| `PING_TIMEOUT_MS` | `1000` | Timeout per balasan ICMP |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | kosong | Hanya dibaca backend |
| `TELEGRAM_BLOCK_NOTIFY_ENABLED` | `false` | Kirim notifikasi blokir/unblock saat dashboard polling |

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
    ├── blocked_notifier.py transisi blocked/unblock dari polling
    └── telegram.py         kirim + riwayat (in-memory)
```

- SQLite hanya menyimpan akun (`users`), bukan telemetry.
- Frontend tidak pernah menerima token Telegram atau kredensial.
- Kegagalan satu sumber tidak menghentikan panel lain: setiap section memiliki `status`, `error`, `source`, dan timestamp.
- Riwayat Telegram dan baseline IP terblokir disimpan di memori proses (bukan SQLite); notifikasi hanya berjalan selama dashboard polling.

## Kontrak API Internal

`GET /api/overview` (login required) mengembalikan bentuk berikut. Kontrak ini adalah kontrak internal dashboard; mapping ke API tim masih provisional.

```json
{
  "generated_at": "2026-10-20T10:15:00Z",
  "data_mode": "demo",
  "poll_interval_ms": 5000,
  "range": "5m",
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
  "blocked_ips": { "status": "ok", "source": "LightGBM + Random Forest + Fail2Ban", "error": null, "items": [], "total": 0, "truncated": false },
  "attacks": { "status": "ok", "source": "API deteksi", "error": null, "items": [] },
  "telegram": { "status": "ok", "source": "Telegram Bot API", "error": null, "items": [] },
  "errors": []
}
```

`status` per section: `ok`, `empty`, `error`, `unavailable`. Nilai yang tidak tersedia dikirim sebagai `null`, bukan `0`.

Pada mode live, panel **Network Flow** memakai 17 fitur input Random Forest:
`Protocol`, `Flow Duration`, `Tot Fwd Pkts`, `Tot Bwd Pkts`, `TotLen Fwd Pkts`,
`TotLen Bwd Pkts`, `Flow Pkts/s`, `Flow IAT Mean`, `Flow IAT Std`,
`Fwd IAT Mean`, `Bwd IAT Mean`, `Fwd Pkts/s`, `Bwd Pkts/s`, `ACK Flag Cnt`,
`Init Fwd Win Byts`, `Init Bwd Win Byts`, dan `Fwd Seg Size Min`. Setiap fitur
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

`POST /api/telegram/test` mengirim alert uji. Di mode demo hasilnya disimulasikan; di mode live endpoint mengembalikan `502` jika Telegram gagal/tidak dikonfigurasi. Notifikasi blokir/unblock otomatis terpisah dari endpoint ini dan hanya dipicu polling `/api/overview` saat `TELEGRAM_BLOCK_NOTIFY_ENABLED=true`.

`POST /api/iperf3/run` dan `POST /api/delay/run` memulai pengukuran manual di background lalu mengembalikan `202` beserta `estimated_seconds`. Keduanya memerlukan login + CSRF, dan mengembalikan `409` bila runner tidak tersedia (mode demo) atau pengukuran masih berjalan. Hasil muncul pada polling `/api/overview` berikutnya melalui `qos.test` (iperf3) dan `qos.delay_test` (ICMP).

### Bentuk data yang diharapkan adapter live

- `LIGHTGBM_BLOCKED_API_URL`: list item atau `{ "items": [...] }`; field `ip`, `blocked_at`, `unblock_at`, `remaining_seconds`, `jail`, `status` (Bearer `LIGHTGBM_API_TOKEN`).
- `RANDOM_FOREST_BLOCKED_API_URL`: format sama dengan LightGBM; sumber `Random Forest` (Bearer `RANDOM_FOREST_API_TOKEN`).
- `FAIL2BAN_API_URL`: list item atau `{ "items": [...] }`; field `ip`, `blocked_at`, `jail`, `status` (endpoint baru di VM Fail2Ban memakai Bearer `FAIL2BAN_API_TOKEN`).
- `ATTACK_HISTORY_API_URL`: list item atau `{ "items": [...] }`; field `detected_at`, `source_ip`, `attack_type`, `detection`, `model`, `blocking_status`.
- `IPERF3_RESULT_URL`: `{ "timestamp", "throughput_mbps", "jitter_ms", "packet_loss_percent", "protocol" }` (fallback bila runner lokal tidak aktif).
- `DELAY_API_URL`: `{ "timestamp", "delay_ms" }` (fallback bila `PING_TARGET_HOST` kosong).
- `GLANCES_*_URL`: base URL Glances; backend memanggil `/api/4/quicklook` (fallback `/api/3/quicklook`) dan membaca `cpu` serta `mem`.

Jika `IPERF3_ENABLED=true` dan `IPERF3_SERVER_HOST` diisi, backend menjalankan `iperf3 -c <host> -J` sendiri (UDP memakai `-u -b <bandwidth>`) sehingga `IPERF3_RESULT_URL` tidak diperlukan. Jika `PING_TARGET_HOST` diisi, delay diukur langsung via ICMP. Pada mode `QOS_SOURCE_MODE=vm`, packet loss juga diambil dari ICMP ping in-VM (fallback ke loss UDP bila ping gagal).

Semua bentuk di atas **provisional** dan harus disesuaikan dengan kontrak API tim.

## Integrasi VM Random Forest (read-only)

API RF ada di `deploy/rf_api.py`. Endpoint `/api/attacks` membaca `detection_logs`
dengan filter model `RandomForestClassifier`/`RandomForest` dan `prediction = 'SSH-Bruteforce'`;
endpoint `/api/features` membaca 17 fitur dari `capture/processed/*.csv`; endpoint
`/api/blocked` membaca IP berstatus `BLOCKED` beserta `unblock_at`. Semua endpoint
read-only dan mewajibkan Bearer token (`RF_API_TOKEN`). API tidak menulis DB;
auto-block dilakukan worker + helper firewall di VM.

`/api/attacks` mengisi `blocking_status` dari status terakhir IP di `blocked_ips`:
`true` bila masih `BLOCKED`, `false` bila sudah `UNBLOCKED`, dan `null` bila IP belum
pernah tercatat. `/api/blocked` mengembalikan `ip`, `blocked_at`, `last_seen_at`,
`unblock_at`, `remaining_seconds`, `jail`, `reason`, `model`, `status`, dan
`source: "Random Forest"`.

Akses langsung dari laptop (tanpa tunnel) menggunakan IP VM yang sama dengan
`VM_HOST` / `RF_VM_HOST`:

```dotenv
GLANCES_RANDOM_FOREST_URL=http://${RF_VM_HOST}:61208
ATTACK_HISTORY_API_URL=http://${RF_VM_HOST}:8080/api/attacks
ATTACK_HISTORY_API_TOKEN=<token-dari-VM>
RANDOM_FOREST_BLOCKED_API_URL=http://${RF_VM_HOST}:8080/api/blocked
RANDOM_FOREST_API_TOKEN=<token-dari-VM>
FLOW_FEATURES_API_URL=http://${RF_VM_HOST}:8080/api/features
IPERF3_ENABLED=true
IPERF3_SERVER_HOST=${RF_VM_HOST}
PING_TARGET_HOST=${RF_VM_HOST}
```

Server iperf3 berjalan langsung di VM agar pengukuran mencerminkan jalur LAN.
Izinkan `5201/tcp` dan `5201/udp` hanya dari subnet monitoring. Jika VM tidak
terjangkau (IP DHCP berubah/mati), panel RF menampilkan error/unavailable, bukan
data demo.

Auto-unblock Random Forest memakai konfigurasi yang sama dengan LightGBM:

```bash
# /home/server/ids-backend/config/auto_block.json
{ "block_seconds": 10 }
```

- `capture/feature_worker.py` memanggil `/usr/local/sbin/ids-auto-block-ssh`
  dengan `block` lalu `unblock-after <ip> <detik>` setelah baris `blocked_ips`
  di-commit.
- Setiap deteksi baru mereset timer; durasi valid 1-31536000 detik dan file
  dibaca ulang pada setiap deteksi.
- `database/database.py` menambahkan kolom `blocked_ips.unblock_at` secara
  idempotent saat `init_database()`.
- Helper menulis/menghapus `unblock_at` saat `block`, `unblock-after`,
  `cancel-unblock`, `unblock`, dan `expire-unblock`.
- Jika pembuatan timer gagal, IP tetap diblokir permanen dan dashboard
  menampilkan `Manual`.

Tidak ada Scheduled Task tunnel yang perlu dijalankan. Jika IP VM berubah,
cukup ganti `RF_VM_HOST` di `.env` lalu restart dashboard.

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

Cakupan saat ini: register/login/logout, proteksi route/API, CSRF, kontrak overview, konsistensi statistik, mode live tanpa endpoint, endpoint test Telegram, notifikasi blokir/unblock (baseline, batch, partial/truncated, pengiriman gagal), parsing keluaran iperf3 (TCP/UDP) dan ping (locale ID/EN/Linux), endpoint trigger QoS, serta API RF read-only (filter model, token, limit, timestamp, endpoint 17 fitur flow, blocked IP, dan `blocking_status`).

## Batasan yang Masih Terbuka

- `desain.md` tidak tersedia; tema gelap dibuat sementara dan mudah diganti melalui token CSS.
- Endpoint serta skema API LightGBM/RF, Fail2Ban, dan Glances sudah dipakai untuk data live; perubahan kontrak harus disertai update provider + tes.
- Panel Network Flow menampilkan line chart per fitur RF yang dipilih lewat dropdown; metrik throughput/flow mentah belum dikoleksi terpisah.
- Server iperf3 berjalan di VM; hasil throughput/jitter/loss bergantung pada jalur LAN dan aturan UFW.
- Delay memakai ICMP ping. Jaringan yang memblokir ICMP (termasuk jaringan laptop saat ini untuk target internet) tidak dapat diukur; gunakan target LAN/VPN yang mengizinkan ICMP.
- Statistik QoS dihitung dari seri yang sudah difilter sesuai `range` terpilih (5m/30m/1h).
- Grafik resource dan buffer Network Flow bersifat in-memory; tampilan 1 jam baru penuh setelah dashboard berjalan ±1 jam. Setelah restart, buffer flow diisi ulang dari 200 event terakhir API.
- Network Flow adalah data per event autentikasi. Bila tidak ada event pada rentang terpilih, panel menampilkan aktivitas terakhir dengan penanda bahwa event tersebut di luar rentang.
- Glances di Windows mendukung CPU/memori/disk via psutil; sensor suhu/GPU tidak tersedia.
- Threshold baik/buruk QoS sengaja tidak diimplementasikan.
- Histori serangan tidak dipersistenkan oleh dashboard; data dibaca dari API RF. Riwayat Telegram dan baseline notifikasi hanya ada di memori proses.
- Notifikasi blokir/unblock hanya berjalan saat dashboard polling; tab tertutup, restart, atau periode tanpa polling tidak mengirim notifikasi susulan.
