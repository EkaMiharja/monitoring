# Task List: Dashboard Monitoring Deteksi SSH Brute Force

## Tujuan

Dokumen ini membagi kebutuhan dalam PRD menjadi pekerjaan implementasi yang dapat dikerjakan dan diverifikasi. Cakupan mengikuti PRD terbaru: dashboard web responsif yang dapat dibuka melalui browser laptop/desktop, tablet, dan HP; autentikasi pengguna; integrasi API dari server LightGBM, Random Forest, dan Fail2Ban; metrik resource melalui Glances pada setiap server; pengukuran traffic/QoS di laptop monitoring; serta notifikasi Telegram. Backend Flask berjalan di laptop monitoring. SQLite hanya digunakan untuk data akun pengguna, bukan penyimpanan telemetry atau riwayat monitoring.

## Status dan Prioritas

**Status:** `Todo` · `In Progress` · `Blocked` · `Done`

**Prioritas:** `P0` wajib untuk MVP; `P1` penting untuk melengkapi dan menstabilkan sistem; `P2` opsional setelah MVP stabil.

Task yang bergantung pada backend atau sumber data belum dianggap selesai hanya karena UI menggunakan data dummy. Data dummy boleh digunakan sementara untuk pengembangan tampilan, tetapi harus diberi label dan diganti sebelum acceptance criteria dinyatakan terpenuhi.

---

## 1. Project Setup

### TASK-001 — Siapkan struktur proyek
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Siapkan repository dan struktur folder frontend/backend sesuai teknologi yang dipilih.
- **Checklist:**
  - [ ] Buat struktur direktori yang konsisten.
  - [ ] Siapkan konfigurasi development.
  - [ ] Tambahkan README cara menjalankan proyek.
  - [ ] Siapkan backend Flask di laptop monitoring dan frontend web yang diakses melalui browser.
  - [ ] Catat konfigurasi akses API ketiga server serta Glances tanpa mengasumsikan endpoint yang belum disepakati.
  - [ ] Siapkan SQLite khusus data akun pengguna.
- **Kriteria selesai:** Struktur proyek jelas, instruksi menjalankan proyek tersedia, dan lokasi backend/sumber data sesuai arsitektur PRD.

### TASK-002 — Tetapkan kontrak data monitoring
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Sepakati struktur response API/JSON untuk seluruh komponen dashboard.
- **Checklist:**
  - [ ] Tentukan field, tipe data, unit, timestamp, dan identitas VM.
  - [ ] Tentukan format error, data kosong, dan status data kedaluwarsa.
  - [ ] Dokumentasikan endpoint dan contoh response bersama tim backend.
  - [ ] Catat API yang sudah tersedia dari server LightGBM, Random Forest, dan Fail2Ban.
  - [ ] Tentukan akses Glances untuk CPU/memori pada setiap server.
  - [ ] Sepakati topologi uji iperf3: host client/server, arah pengujian, protokol TCP/UDP, durasi dan interval tes, serta cara memicu/menjadwalkan tes.
  - [ ] Tentukan metode/sumber pengukuran delay/latency secara terpisah jika metrik ini wajib ditampilkan.
  - [ ] Sepakati metode, arah, antarmuka, dan periode pengamatan network traffic/flow yang diukur pada laptop monitoring.
  - [ ] Pastikan refresh UI 5 detik tidak dianggap sebagai interval sampling semua sumber.
- **Kriteria selesai:** Frontend dan backend memakai kontrak data yang sama; setiap metrik memiliki sumber, satuan, timestamp, dan waktu pengukuran yang jelas.

---

## 2. Authentication

### TASK-003 — Buat halaman Register
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Buat form registrasi pengguna sesuai `desain.md`.
- **Checklist:** 
  - [ ] Tambahkan field sesuai kebutuhan backend.
  - [ ] Tambahkan validasi input dan pesan kesalahan.
  - [ ] Hubungkan form dengan endpoint registrasi.
- **Kriteria selesai:** Pengguna dapat mengirim registrasi dan respons sukses/gagal ditangani dengan jelas.

### TASK-004 — Buat halaman Login
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Buat form login dan integrasikan dengan autentikasi backend.
- **Checklist:**
  - [ ] Validasi input.
  - [ ] Tampilkan pesan ketika kredensial tidak valid.
  - [ ] Arahkan pengguna ke Overview setelah login berhasil.
- **Kriteria selesai:** Login berhasil membuka dashboard; login gagal tidak memberikan akses.

### TASK-005 — Implementasikan Logout dan proteksi halaman
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Pastikan hanya pengguna terautentikasi dapat mengakses dashboard.
- **Checklist:**
  - [ ] Implementasikan logout.
  - [ ] Periksa status autentikasi saat membuka halaman yang dilindungi.
  - [ ] Tangani sesi kedaluwarsa atau akses ditolak.
- **Kriteria selesai:** Pengguna belum login tidak dapat mengakses dashboard; logout mengakhiri sesi.

---

## 3. Dashboard Shell dan Navigasi

### TASK-006 — Bangun layout utama dashboard
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Buat layout dashboard konsisten dengan `desain.md`.
- **Checklist:**
  - [ ] Buat sidebar dan area konten utama.
  - [ ] Buat top bar sesuai kebutuhan.
  - [ ] Terapkan hierarki judul, spacing, border, dan warna sesuai style guide.
  - [ ] Pastikan layout responsif pada ukuran layar yang ditargetkan.
- **Kriteria selesai:** Layout konsisten dan navigasi tetap dapat digunakan pada laptop/desktop, tablet, dan HP; keenam komponen Overview tetap dapat diakses dan dibaca di layar kecil.

### TASK-007 — Implementasikan navigasi halaman
- **Prioritas:** P1
- **Status:** Todo
- **Deskripsi:** Buat navigasi sesuai Information Architecture terbaru.
- **Checklist:**
  - [ ] Tetapkan item navigasi berdasarkan halaman yang benar-benar masuk cakupan.
  - [ ] Tunjukkan item navigasi aktif.
  - [ ] Jangan menampilkan evaluasi model atau perbandingan ML vs Fail2Ban sebagai komponen Overview.
- **Kriteria selesai:** Navigasi mengarah ke halaman yang benar dan tidak mengklaim fitur belum tersedia.

---

## 4. Dashboard Overview

Overview memuat enam komponen: network traffic/flow, QoS, CPU/memory, blocked IP list, attack history, dan Telegram alert. Evaluasi LightGBM vs Random Forest serta perbandingan ML vs Fail2Ban tidak ditampilkan pada Overview.

### TASK-008 — Buat Network Traffic / Flow Graph
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan grafik trafik atau flow jaringan berdasarkan data aktual backend.
- **Checklist:**
  - [ ] Pilih grafik sesuai struktur data yang tersedia.
  - [ ] Tampilkan sumbu waktu, label, dan unit yang benar.
  - [ ] Buat loading, empty, dan error state.
  - [ ] Pisahkan trafik normal dan serangan hanya jika klasifikasi tersedia.
- **Kriteria selesai:** Grafik memakai data aktual dan timestamp; label/unit sesuai sumber.

### TASK-009 — Integrasikan iperf3 dan tampilkan QoS
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan delay, jitter, packet loss, dan throughput selama pengujian.
- **Checklist:**
  - [ ] Integrasikan eksekusi/pengambilan hasil iperf3 melalui backend sesuai topologi dan konfigurasi yang disepakati.
  - [ ] Catat konfigurasi dan metadata tes: host client/server, protokol TCP/UDP, arah, durasi/interval, timestamp, serta status berhasil/gagal.
  - [ ] Tampilkan throughput dari hasil iperf3 dan, untuk tes UDP bila tersedia, jitter serta packet loss.
  - [ ] Tentukan metode/sumber delay (ms) secara terpisah; jika belum tersedia, tampilkan “Belum tersedia” alih-alih mengarang nilai.
  - [ ] Pilih visualisasi yang sesuai untuk tiap metrik tanpa mengunci layout tertentu; bila statistik ditampilkan, hitung dari periode/sampel yang konsisten.
  - [ ] Isi tabel dengan Min, Max, dan Avg (Mean) yang dihitung dari sampel pada periode yang sama dengan grafik.
  - [ ] Tampilkan satuan, rentang waktu, timestamp pengukuran, dan sumber data yang relevan.
  - [ ] Pastikan grafik dan tabel menggunakan rentang data yang konsisten.
  - [ ] Gunakan hasil pengukuran aktual; data dummy tidak boleh ditampilkan seolah-olah data live.
  - [ ] Tangani nilai kosong atau pengukuran gagal tanpa mengubahnya menjadi nol.
  - [ ] Konfirmasikan periode statistik dengan tim; jangan mengasumsikan periode yang belum disepakati.
  - [ ] Pertahankan refresh UI setiap 5 detik sesuai rancangan, tanpa menganggap sumber menghasilkan sampel baru setiap 5 detik.
  - [ ] Jangan membuat threshold/batas baik-buruk pada tahap ini karena ditunda.
- **Kriteria selesai:** Backend dapat menjalankan/mengambil hasil tes iperf3 sesuai konfigurasi yang disepakati; UI menampilkan hanya metrik yang benar-benar dihasilkan, dengan satuan, timestamp, status tes, dan metadata sumber/protokol. Delay ditampilkan hanya jika metode pengukurannya telah ditentukan. Statistik, bila ditampilkan, memakai sampel dan periode yang konsisten.

### TASK-010 — Buat System Resource Monitoring
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan CPU usage dan memory usage pada setiap VM yang dipantau.
- **Checklist:**
  - [ ] Tampilkan CPU Usage (%) dan Memory Usage (%) dengan identitas VM yang jelas.
  - [ ] Integrasikan sumber data resource, misalnya Glances melalui backend/API yang disepakati.
  - [ ] Pilih visualisasi yang sesuai untuk tiap metrik tanpa mengunci layout tertentu; bila statistik ditampilkan, hitung dari periode/sampel yang konsisten.
  - [ ] Isi tabel dengan Min, Max, dan Mean berdasarkan sampel pada periode yang sama dengan grafik.
  - [ ] Tampilkan satuan, rentang waktu, identitas VM, timestamp, dan sumber data yang relevan.
  - [ ] Pastikan grafik dan tabel memakai rentang data/periode yang konsisten.
  - [ ] Gunakan data monitoring aktual; jangan menampilkan data dummy seolah-olah data live.
  - [ ] Tangani nilai kosong, sumber tidak tersedia, atau VM yang tidak dapat dihubungi tanpa menampilkannya sebagai 0%.
  - [ ] Pertahankan refresh UI setiap 5 detik sesuai rancangan, tetapi jangan menganggap sumber monitoring menghasilkan sampel baru setiap 5 detik.
  - [ ] Konfirmasikan periode statistik dengan tim.
- **Kriteria selesai:** CPU dan memori untuk setiap VM yang dipantau ditampilkan dengan grafik time series di kiri dan tabel Min, Max, Mean di kanan. Statistik dan grafik memakai periode yang sama, disertai satuan, rentang waktu, identitas VM, timestamp, serta sumber data yang relevan. Glances hanya menjadi sumber metrik resource, bukan prediksi serangan.

### TASK-011 — Buat Blocked IP List
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan daftar IP yang status pemblokirannya dikonfirmasi oleh data Fail2Ban.
- **Checklist:**
  - [ ] Tampilkan IP dan waktu pemblokiran jika tersedia.
  - [ ] Tampilkan status blokir berdasarkan respons sumber.
  - [ ] Buat empty state jika belum ada IP diblokir.
  - [ ] Tampilkan error atau status sumber tidak tersedia.
- **Kriteria selesai:** Daftar hanya memuat IP yang didukung data aktual Fail2Ban. Prediksi ML saja bukan bukti bahwa IP sudah diblokir.

### TASK-012 — Buat Attack History
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan riwayat kejadian deteksi SSH Brute Force.
- **Checklist:**
  - [ ] Tampilkan waktu, source IP, jenis serangan/hasil prediksi, dan status blocking jika tersedia.
  - [ ] Tambahkan pencarian/filter dasar jika sesuai cakupan.
  - [ ] Tampilkan loading, empty, dan error state.
- **Kriteria selesai:** Riwayat menampilkan field yang benar-benar disediakan backend dan waktu kejadian dibedakan dari waktu data diterima dashboard.

### TASK-013 — Tampilkan status/riwayat Telegram Alert
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Tampilkan status integrasi atau riwayat notifikasi Telegram jika backend menyediakan datanya.
- **Checklist:**
  - [ ] Sepakati field alert yang tersedia.
  - [ ] Tampilkan status pengiriman berdasarkan respons backend.
  - [ ] Buat empty state jika belum ada notifikasi.
- **Kriteria selesai:** Dashboard tidak mengklaim alert terkirim tanpa status terkonfirmasi dan token bot tidak pernah ditampilkan di frontend.

---

## 5. API dan Pembaruan Data

### TASK-014 — Integrasikan endpoint monitoring
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Hubungkan dashboard ke backend/API yang menyajikan JSON dari sumber monitoring.
- **Checklist:**
  - [ ] Integrasikan endpoint network traffic/flow.
  - [ ] Integrasikan endpoint QoS.
  - [ ] Integrasikan endpoint resource VM.
  - [ ] Integrasikan endpoint blocked IP dan attack history.
  - [ ] Integrasikan endpoint status/riwayat Telegram alert jika tersedia.
  - [ ] Tangani timeout, HTTP error, dan response tidak sesuai.
- **Kriteria selesai:** Setiap komponen memakai endpoint yang sesuai; kegagalan satu sumber tidak membuat seluruh dashboard berhenti.

### TASK-015 — Implementasikan polling setiap 5 detik
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Perbarui data secara berkala tanpa reload halaman.
- **Checklist:**
  - [ ] Atur interval polling 5 detik.
  - [ ] Hindari request bertumpuk jika request sebelumnya belum selesai.
  - [ ] Bersihkan polling saat halaman ditinggalkan.
  - [ ] Tampilkan waktu pembaruan terakhir.
  - [ ] Tampilkan indikator data stale/koneksi bermasalah jika dapat diketahui.
- **Kriteria selesai:** Data diperbarui tanpa reload, request tidak menumpuk, dan timestamp mencerminkan waktu data yang benar.

---

## 6. Telegram Integration

### TASK-016 — Integrasikan pengiriman alert Telegram melalui backend
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Pastikan backend mengirim notifikasi saat kondisi deteksi SSH Brute Force memenuhi aturan sistem.
- **Checklist:**
  - [ ] Sepakati payload alert dengan backend.
  - [ ] Tentukan aturan pemicu alert.
  - [ ] Sertakan waktu, source IP, jenis serangan, hasil deteksi, dan status blocking jika terkonfirmasi.
  - [ ] Ekspos status pengiriman jika dibutuhkan dashboard.
  - [ ] Simpan token Telegram secara aman di backend/environment configuration.
- **Kriteria selesai:** Alert uji diterima saat kondisi pemicu terpenuhi; kegagalan Telegram dicatat dan tidak menghentikan monitoring; token tidak ada di frontend.

---

## 7. Visual Design dan Responsiveness

### TASK-017 — Terapkan design system dari `desain.md`
- **Prioritas:** P1
- **Status:** Todo
- **Deskripsi:** Samakan warna, tipografi, spacing, border, card, tabel, dan status visual dengan style guide.
- **Checklist:**
  - [ ] Terapkan palet warna dan tipografi.
  - [ ] Gunakan komponen berulang untuk card, badge, tabel, dan state.
  - [ ] Pastikan status memiliki label/ikon pendukung, bukan hanya warna.
- **Kriteria selesai:** Tampilan konsisten, profesional, dan mudah dibaca.

### TASK-018 — Implementasikan loading, empty, dan error states
- **Prioritas:** P1
- **Status:** Todo
- **Deskripsi:** Beri feedback ketika data sedang dimuat, belum tersedia, atau gagal diambil.
- **Checklist:**
  - [ ] Buat loading/skeleton state.
  - [ ] Buat empty state dengan penjelasan.
  - [ ] Buat error state dan aksi coba lagi bila sesuai.
- **Kriteria selesai:** Panel utama tidak kosong tanpa penjelasan dan status tanpa data dapat dibedakan dari error.

### TASK-019 — Uji responsivitas dan aksesibilitas dasar
- **Prioritas:** P1
- **Status:** Todo
- **Deskripsi:** Pastikan dashboard dapat digunakan pada ukuran layar target.
- **Checklist:**
  - [ ] Uji desktop, tablet, dan mobile.
  - [ ] Uji navigasi keyboard dan focus state.
  - [ ] Periksa kontras teks dan label grafik.
- **Kriteria selesai:** Layout tidak rusak dan kontrol utama dapat digunakan dengan keyboard.

---

## 8. Testing dan Validasi

### TASK-020 — Uji autentikasi
- **Prioritas:** P0
- **Status:** Todo
- **Kriteria selesai:** Registrasi dan login berjalan sesuai rancangan; kredensial salah ditolak; dashboard terlindungi; logout mengakhiri sesi.

### TASK-021 — Uji akurasi tampilan data monitoring
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Cocokkan nilai dashboard dengan data sumber/backend.
- **Kriteria selesai:** Nilai, unit, timestamp, identitas VM, status Fail2Ban, dan status pengiriman Telegram sesuai sumber; data dummy tidak disajikan sebagai data live.

### TASK-022 — Uji pembaruan dan ketahanan dashboard
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Uji polling, kegagalan endpoint, dan pemulihan koneksi.
- **Kriteria selesai:** Pembaruan berjalan berkala tanpa reload; error satu endpoint tidak merusak seluruh halaman; request polling tidak menumpuk.

### TASK-023 — Uji integrasi end-to-end
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Jalankan skenario terkontrol dari sumber data hingga dashboard dan Telegram.
- **Checklist:**
  - [ ] Pastikan data monitoring tampil pada dashboard.
  - [ ] Pastikan kejadian deteksi masuk ke attack history.
  - [ ] Pastikan blocked IP berdasarkan konfirmasi Fail2Ban.
  - [ ] Pastikan alert Telegram dikirim sesuai aturan.
- **Kriteria selesai:** Alur end-to-end dibuktikan melalui data/log pengujian dan temuan dicatat.

---

## 9. Deployment dan Dokumentasi

### TASK-024 — Dokumentasikan konfigurasi dan cara menjalankan
- **Prioritas:** P1
- **Status:** Todo
- **Deskripsi:** Dokumentasikan cara menjalankan frontend/backend dan konfigurasi sumber monitoring.
- **Checklist:**
  - [ ] Dokumentasikan environment variables tanpa secret.
  - [ ] Dokumentasikan endpoint yang dibutuhkan.
  - [ ] Dokumentasikan cara menjalankan tes dasar.
- **Kriteria selesai:** Anggota tim dapat menjalankan proyek dari dokumentasi tanpa membocorkan token/password.

### TASK-025 — Validasi kesiapan MVP
- **Prioritas:** P0
- **Status:** Todo
- **Deskripsi:** Periksa seluruh acceptance criteria PRD sebelum demo.
- **Checklist:**
  - [ ] Verifikasi autentikasi.
  - [ ] Verifikasi enam komponen Overview.
  - [ ] Verifikasi pembaruan berkala 5 detik.
  - [ ] Verifikasi integrasi API dan Telegram.
  - [ ] Catat fitur yang belum tersedia atau masih menggunakan data dummy.
- **Kriteria selesai:** Setiap acceptance criteria memiliki hasil uji/status terdokumentasi dan batasan implementasi diketahui.

---

## Dependensi dan Catatan

- Integrasi API membutuhkan kontrak data dan endpoint dari tim backend.
- QoS membutuhkan konfigurasi iperf3 yang disepakati (client/server, TCP/UDP, arah, durasi/interval dan pemicu tes), unit, timestamp, serta metode terpisah untuk delay/latency.
- Resource monitoring membutuhkan endpoint Glances atau sumber setara yang dapat diakses dengan aman.
- Blocked IP membutuhkan status aktual dari Fail2Ban.
- Attack history dan Telegram alert membutuhkan data/log dari backend.
- Authentication membutuhkan mekanisme backend atau layanan autentikasi yang disepakati tim.

Dokumen ini merupakan daftar kerja dashboard berdasarkan PRD. Dokumen ini tidak mengasumsikan semua endpoint, format data, metode QoS, atau mekanisme backend sudah tersedia; seluruh dependensi perlu dikonfirmasi sebelum integrasi dinyatakan selesai.


## Konfigurasi Environment dan Penyimpanan API

Semua konfigurasi URL API/endpoint dan nilai konfigurasi terkait integrasi eksternal harus dikelola melalui file `.env`, bukan ditulis langsung (hardcode) di kode aplikasi. Gunakan nama variabel yang disepakati tim, misalnya `API_BASE_URL` sebagai contoh nama konfigurasi dasar; nama final mengikuti kontrak proyek.

Contoh struktur `.env` (gunakan nilai lokal/rahasia yang sesuai; jangan mengisi kredensial nyata ke dokumentasi atau repository):

```dotenv
API_BASE_URL=http://localhost:5000
# Contoh jika proyek membutuhkan endpoint/konfigurasi tambahan:
# AUTH_API_URL=
# QOS_API_URL=
# IPERF3_CLIENT_HOST=
# IPERF3_SERVER_HOST=
# IPERF3_TEST_PROTOCOL=udp
# IPERF3_TEST_DURATION_SECONDS=
# IPERF3_TEST_INTERVAL_SECONDS=
# TELEGRAM_API_URL=
# TELEGRAM_BOT_TOKEN=
```

Catatan keamanan:
- `.env` adalah file konfigurasi environment, bukan tempat menyimpan seluruh implementasi/source code API.
- Jika yang dimaksud “semua API disimpan di `.env`” adalah URL endpoint dan konfigurasi API, simpan nilai konfigurasi tersebut di `.env`; kode pemanggil API tetap berada di file service/backend yang sesuai.
- Jangan commit `.env` yang berisi token, password, atau secret ke Git. Tambahkan `.env` ke `.gitignore`.
- Sediakan `.env.example` berisi nama variabel dan placeholder tanpa nilai rahasia agar anggota tim mengetahui konfigurasi yang diperlukan.
- Pada frontend browser, jangan memasukkan secret seperti `TELEGRAM_BOT_TOKEN` ke environment variable yang akan dibundel/ditampilkan ke client. Token Telegram harus tetap di backend/server. Frontend hanya menggunakan konfigurasi publik yang memang aman untuk diketahui browser.
- Jika frontend dan backend berjalan sebagai aplikasi terpisah, tentukan `.env` masing-masing sesuai mekanisme framework/build tool; variabel rahasia hanya dibaca di backend.



## Ketentuan Visualisasi dan Statistik Monitoring

| Komponen | Metrik | Statistik |
|---|---|---|
| QoS | Delay, Jitter, Packet Loss, Throughput | Min, Max, Avg (Mean) |
| System Resource | CPU Usage, Memory Usage | Min, Max, Mean |

Untuk kedua komponen, statistik harus dihitung dari sampel/periode data yang konsisten. Tampilkan satuan, rentang waktu, timestamp, dan sumber data yang relevan; untuk resource, sertakan identitas VM. Gunakan pengukuran aktual, bukan data dummy yang terlihat seperti data live. Refresh UI setiap 5 detik tidak menjamin sumber menghasilkan sampel baru pada interval tersebut. Periode statistik harus disepakati dengan tim. Threshold/batas baik-buruk QoS ditunda dan tidak termasuk task saat ini.


## Arsitektur Implementasi yang Disepakati

- Laptop monitoring menjalankan backend Flask dan frontend web. Pengguna dapat membuka dashboard yang sama dari browser HP selama perangkat dapat menjangkau laptop/server dashboard melalui jaringan yang dikonfigurasi.
- Backend Flask mengambil data dari API yang sudah tersedia pada server LightGBM, Random Forest, dan Fail2Ban, serta mengambil metrik CPU/memori dari Glances pada setiap server yang dipantau. Endpoint dan skema respons harus mengikuti API aktual, bukan dibuat berdasarkan asumsi.
- Network traffic/flow diukur pada laptop monitoring. Pengujian QoS memakai iperf3 sesuai topologi client-server yang disepakati; konfigurasi tes tidak boleh diasumsikan. Metode/sumber delay harus ditentukan terpisah sebelum metrik delay ditampilkan.
- Backend menormalisasi data sumber menjadi JSON untuk frontend. Frontend tidak perlu mengakses API tiap server secara langsung jika arsitektur menetapkan akses melalui Flask.
- SQLite hanya menyimpan data akun untuk Register/Login, misalnya username unik, password hash, dan waktu pembuatan akun. Jangan gunakan SQLite akun sebagai penyimpanan telemetry, QoS, attack history, status blokir, atau riwayat Telegram kecuali keputusan arsitektur diubah secara eksplisit.
- Simpan URL API dan secret pada konfigurasi backend seperti `.env`; jangan pernah mengekspos token Telegram di HTML/JavaScript atau browser.
