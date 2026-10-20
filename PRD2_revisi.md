# Product Requirements Document (PRD)
## Dashboard Monitoring Deteksi SSH Brute Force

---

## 1. Product Overview

Dashboard Monitoring Deteksi SSH Brute Force merupakan dashboard web untuk memantau kondisi jaringan dan sistem secara terpusat selama pengujian SSH Brute Force. Halaman Dashboard Overview menampilkan grafik network traffic/flow, metrik Quality of Service (QoS), penggunaan CPU dan memori, daftar IP yang diblokir, attack history, serta informasi notifikasi alert Telegram.

Dashboard dapat diakses melalui browser pada laptop/desktop maupun perangkat mobile dengan tata letak responsif. Dashboard menerima data melalui backend Flask dari API server LightGBM, Random Forest, dan Fail2Ban yang dapat diakses dari laptop monitoring. Data CPU dan memori diperoleh dari Glances yang berjalan pada setiap server yang dipantau. Pengukuran QoS menggunakan iperf3 dengan proses pengujian yang dikendalikan/dijalankan dari laptop monitoring sesuai topologi client-server yang disepakati. Pengukuran network traffic/flow tetap dilakukan pada laptop monitoring dengan metode yang ditentukan tim. Backend menormalisasi data dari sumber-sumber tersebut ke format JSON untuk frontend. Antarmuka diperbarui setiap 5 detik tanpa memuat ulang seluruh halaman. Interval ini adalah interval pembaruan UI dan tidak berarti semua sumber menghasilkan sampel baru setiap 5 detik. Sistem juga terintegrasi dengan Telegram untuk mengirimkan notifikasi ketika serangan SSH Brute Force terdeteksi.

Sistem menyediakan Register, Login, dan Logout. Pengguna harus berhasil login sebelum dapat mengakses dashboard.

---

## 2. Problem Statement

Data trafik jaringan, hasil pengukuran QoS, penggunaan resource VM, informasi IP yang diblokir, dan riwayat serangan dapat berasal dari sumber atau VM yang berbeda. Jika informasi tersebut hanya tersedia melalui terminal atau log masing-masing VM, pemantauan kondisi selama pengujian menjadi kurang praktis.

Dashboard diperlukan untuk memusatkan grafik network traffic/flow, metrik QoS (delay, jitter, packet loss, dan throughput), penggunaan CPU dan memori, daftar IP yang diblokir, serta attack history dalam satu halaman Overview. Integrasi Telegram membantu administrator menerima peringatan tanpa harus selalu membuka dashboard. Autentikasi diperlukan untuk membatasi akses dashboard kepada pengguna yang berhasil login.

---

## 3. Product Goals

- Menampilkan grafik network traffic/flow yang diperbarui secara berkala selama pengujian.
- Memantau metrik QoS berdasarkan pengukuran pada laptop monitoring: delay/latency, jitter, packet loss, dan throughput.
- Memantau penggunaan CPU dan memori melalui Glances pada setiap server yang dipantau.
- Menampilkan daftar IP yang benar-benar diblokir oleh Fail2Ban.
- Menampilkan attack history yang memuat waktu kejadian, source IP, dan informasi deteksi yang tersedia.
- Menampilkan status atau riwayat notifikasi alert Telegram jika datanya disediakan backend.
- Memperbarui data monitoring setiap 5 detik tanpa reload halaman.
- Mengirimkan notifikasi alert melalui Telegram ketika serangan SSH Brute Force terdeteksi.
- Menyediakan Register, Login, dan Logout untuk mengelola akses ke dashboard.

---

## 4. Success Metrics

- Grafik network traffic/flow dapat diperbarui selama pengujian berlangsung.
- Nilai delay, jitter, packet loss, throughput, CPU usage, dan memory usage dapat diperbarui serta ditampilkan dengan satuan yang sesuai.
- Dashboard menerima dan memproses data JSON dari sumber monitoring melalui backend/API.
- Daftar IP yang diblokir hanya menampilkan status yang didukung data aktual Fail2Ban.
- Attack history menampilkan waktu, source IP, dan informasi deteksi yang tersedia.
- Dashboard dapat menampilkan status atau riwayat alert Telegram jika disediakan backend.
- Dashboard memperbarui data setiap 5 detik tanpa memuat ulang halaman.
- Notifikasi Telegram berhasil dikirim ketika serangan SSH Brute Force terdeteksi.
- Pengguna dapat melakukan registrasi, login, dan logout; pengguna yang belum login tidak dapat mengakses dashboard.

---

## 5. Target User

### Project Researcher / Administrator

Tanggung jawab:
- Memantau kondisi jaringan dan aktivitas serangan.
- Melihat metrik QoS dan penggunaan resource VM.
- Memeriksa IP yang diblokir dan riwayat serangan.
- Menerima alert serangan melalui Telegram.
- Melakukan pengujian dan mengamati perubahan kondisi sistem.
- Mengakses dashboard melalui akun yang terdaftar.

---

## 6. User Problems

1. Sulit memantau kondisi jaringan dan serangan dengan cepat jika hanya menggunakan terminal atau log.
2. Data trafik, QoS, resource, dan Fail2Ban berasal dari sumber/VM yang berbeda.
3. Informasi IP yang diblokir belum terpusat.
4. Perubahan kondisi jaringan selama pengujian sulit diamati tanpa visualisasi berkala.
5. Administrator tidak selalu berada di halaman dashboard sehingga membutuhkan mekanisme alert melalui Telegram.
6. Dashboard monitoring memerlukan autentikasi agar tidak dapat diakses oleh pengguna yang belum login.

---

## 7. Core Features

### 7.1 User Authentication

Sistem menyediakan fitur **Register**, **Login**, dan **Logout** sebelum pengguna dapat mengakses Dashboard Monitoring.

- **Register:** pengguna dapat membuat akun baru dengan informasi yang diperlukan untuk mengakses sistem.
- **Login:** pengguna dapat masuk menggunakan akun yang telah terdaftar. Dashboard hanya dapat diakses oleh pengguna yang berhasil melakukan autentikasi.
- **Logout:** pengguna dapat mengakhiri sesi dan kembali ke halaman autentikasi.
- **Access Control:** pengguna yang belum login tidak dapat mengakses halaman dashboard secara langsung.

### 7.2 Dashboard Overview

Halaman Overview berfokus pada pemantauan kondisi jaringan, resource sistem, dan aktivitas serangan secara real-time. Overview memuat enam komponen utama:

1. **Network Traffic / Flow Graph:** grafik trafik atau flow jaringan dari waktu ke waktu berdasarkan pengukuran pada laptop monitoring. Pemisahan trafik normal dan serangan hanya ditampilkan apabila data klasifikasi tersedia.
2. **QoS Monitoring:** nilai delay/latency (ms), jitter (ms), packet loss (%), dan throughput (misalnya Mbps), berdasarkan pengukuran pada laptop monitoring selama pengujian.
3. **System Resource Monitoring:** CPU usage (%) dan memory usage (%) untuk setiap server yang dipantau, diperoleh melalui Glances yang berjalan pada server tersebut.
4. **Blocked IP List:** daftar IP yang terkonfirmasi diblokir oleh Fail2Ban, dengan waktu dan status pemblokiran jika tersedia.
5. **Attack History:** riwayat serangan yang mencakup waktu kejadian, source IP, jenis serangan, dan hasil deteksi jika tersedia.
6. **Telegram Alert:** informasi status integrasi atau riwayat notifikasi Telegram jika data tersebut disediakan backend. Pengiriman alert dilakukan melalui backend ketika kondisi deteksi memenuhi aturan yang ditetapkan.

Dashboard menggunakan pembaruan berkala setiap 5 detik. Nilai metrik harus berasal dari pengukuran aktual; antarmuka tidak boleh menampilkan data contoh seolah-olah data live. Status prediksi serangan dan status pemblokiran harus dibedakan: prediksi serangan tidak otomatis berarti IP telah diblokir.

### 7.3 Network Traffic / Flow Monitoring

Menampilkan grafik trafik atau flow jaringan dari waktu ke waktu berdasarkan pengukuran pada laptop monitoring yang diproses oleh backend. Grafik diperbarui pada antarmuka setiap 5 detik. Label, unit, dan pemisahan kategori harus mengikuti data yang benar-benar tersedia; jangan menganggap pemisahan trafik normal dan serangan tersedia jika sumber data tidak menyediakannya.

### 7.4 Real-Time QoS Monitoring

Menampilkan metrik QoS yang diperbarui selama pengujian berlangsung:
- Delay (ms)
- Jitter (ms)
- Packet Loss (%)
- Throughput (misalnya Mbps)

iperf3 digunakan sebagai alat uji jaringan aktif. Konfigurasi pengujian harus mencatat host client/server, alamat/target, protokol (TCP atau UDP), arah pengujian, durasi/interval, dan timestamp. Throughput dapat diambil dari hasil iperf3; jitter dan packet loss terutama tersedia pada pengujian UDP. iperf3 tidak dengan sendirinya menyediakan metrik delay/latency umum yang setara dengan semua metode pengukuran latency, sehingga metode/sumber delay harus ditentukan dan didokumentasikan terpisah sebelum nilai tersebut ditampilkan. Backend menyajikan hanya metrik yang benar-benar tersedia dari hasil pengujian, dengan unit, waktu, status, dan konfigurasi/sumber relevan. Frekuensi eksekusi pengujian iperf3 harus disepakati tim dan tidak otomatis mengikuti refresh UI 5 detik.


**Ketentuan visualisasi QoS:** Untuk setiap metrik (delay/latency, jitter, packet loss, dan throughput), tampilkan grafik time series di sebelah kiri dan tabel statistik di sebelah kanan dengan kolom Min, Max, dan Avg (Mean). Grafik menunjukkan perubahan nilai dari waktu ke waktu, sedangkan tabel merangkum nilai minimum, maksimum, dan rata-rata aritmetika dari sampel pada periode yang sama dengan grafik. Tampilkan satuan, rentang waktu, serta timestamp dan sumber data yang relevan. Nilai harus berasal dari hasil pengukuran aktual. Interval pembaruan UI tetap setiap 5 detik sesuai rancangan, tetapi hal ini tidak menjamin sumber pengukuran menghasilkan sampel baru setiap 5 detik.

### 7.5 System Resource Monitoring

Menampilkan penggunaan sumber daya sistem pada VM yang dipantau selama pengujian berlangsung, meliputi:
- CPU Usage (%)
- Memory Usage (%)

**Ketentuan visualisasi System Resource Monitoring:** Untuk setiap metrik (CPU Usage dan Memory Usage), tampilkan grafik time series di sebelah kiri dan tabel statistik di sebelah kanan dengan kolom Min, Max, dan Mean. Grafik menunjukkan perubahan penggunaan CPU dan memori dari waktu ke waktu, sedangkan tabel merangkum nilai minimum, maksimum, dan rata-rata aritmetika dari sampel pada periode yang sama dengan grafik.

Tampilkan satuan, rentang waktu, identitas VM yang dipantau, serta timestamp dan sumber data yang relevan. Nilai penggunaan CPU dan memori harus berasal dari hasil pemantauan aktual melalui Glances yang berjalan pada setiap server yang dipantau. Interval pembaruan UI tetap setiap 5 detik sesuai rancangan, tetapi hal ini tidak menjamin sumber monitoring menghasilkan sampel baru setiap 5 detik.

### 7.6 Blocked IP List

Menampilkan daftar IP yang status pemblokirannya dikonfirmasi oleh Fail2Ban atau sumber pemblokiran yang digunakan. Informasi dapat mencakup alamat IP, waktu pemblokiran, status, dan sumber data jika tersedia. IP yang hanya terdeteksi sebagai sumber serangan tidak boleh otomatis ditampilkan sebagai IP terblokir.

### 7.7 Attack History

Menampilkan riwayat kejadian serangan yang tersedia dari sistem deteksi/log, meliputi:
- Waktu kejadian atau waktu deteksi
- Source IP
- Jenis serangan
- Hasil deteksi/prediksi jika tersedia
- Model yang menghasilkan prediksi jika tersedia
- Status pemblokiran jika tersedia

### 7.8 Telegram Alert Notification

Sistem mengirimkan notifikasi alert melalui Telegram ketika serangan SSH Brute Force terdeteksi dan kondisi pemicu yang ditetapkan terpenuhi. Notifikasi dapat memuat:
- Waktu deteksi
- Source IP
- Jenis serangan
- Hasil deteksi
- Status blocking jika tersedia

Contoh format notifikasi:

```text
🚨 SSH Brute Force Detected

IP: [source IP]
Attack: SSH Brute Force
Detection Time: [timestamp]
Blocking Status: [status jika tersedia]
```

Token bot dan credential Telegram harus disimpan di backend/konfigurasi aman dan tidak ditampilkan di frontend.

---

## 8. Information Architecture

Struktur akses sistem:

```text
Authentication
├── Register
└── Login
      ↓
Dashboard
└── Overview
    ├── Network Traffic / Flow
    ├── QoS Monitoring
    ├── System Resource Monitoring
    ├── Blocked IP List
    ├── Attack History
    └── Telegram Alert Status / History
```

Telegram berfungsi sebagai kanal notifikasi alert. Enam komponen di atas merupakan isi Dashboard Overview; evaluasi model dan perbandingan ML dengan Fail2Ban tidak menjadi komponen Overview pada versi PRD ini.

---

## 9. User Flow

### 9.1 Authentication

```text
Buka Website
      ↓
Login / Register
      ↓
Berhasil Login?
   ↙       ↘
 Tidak      Ya
  ↓          ↓
Login      Dashboard Overview
Kembali
```

Setelah berhasil login, pengguna dapat mengakses halaman Overview dan fitur monitoring.

### 9.2 Monitoring Dashboard

```text
Buka Dashboard Overview
      ↓
Request ke Backend/API
      ↓
Ambil Data Trafik, QoS, Resource, Fail2Ban, dan Attack History
      ↓
JSON Response
      ↓
Parsing dan Validasi Data
      ↓
Visualisasi pada Dashboard
      ↓
Update Traffic, QoS, Resource, Blocked IP, Attack History, dan Telegram Alert
      ↓
Tunggu 5 Detik
      ↓
Request Data Monitoring Kembali
```

Proses berjalan berulang selama monitoring aktif. Jika data tidak tersedia atau sudah kedaluwarsa, dashboard perlu menampilkan status yang sesuai, bukan menganggap data lama sebagai data terbaru.

### 9.3 Alur Alert Telegram

```text
Trafik / Aktivitas SSH
      ↓
Deteksi SSH Brute Force
      ↓
Evaluasi Kondisi Pemicu Alert
      ↓
Kirim Alert melalui Backend ke Telegram
      ↓
Simpan / Catat Event jika logging tersedia
      ↓
Tampilkan informasi terkait pada Dashboard
```

Pemblokiran IP merupakan proses terpisah dan hanya ditampilkan sebagai berhasil apabila statusnya dikonfirmasi oleh Fail2Ban atau sumber pemblokiran.

---

## 10. Functional Requirements

- Sistem menyediakan registrasi akun pengguna.
- Sistem menyediakan login dan validasi kredensial.
- Sistem menyediakan logout dan mengakhiri sesi pengguna.
- Pengguna yang belum login tidak dapat mengakses Dashboard Overview.
- Backend Flask dapat mengambil data melalui API dari server LightGBM, Random Forest, dan Fail2Ban yang dapat diakses dari laptop monitoring, serta mengambil metrik CPU dan memori melalui Glances pada setiap server yang dipantau.
- Backend mengukur/mengumpulkan data network traffic/flow dan QoS pada laptop monitoring; data tersebut tidak diasumsikan berasal dari API server ML atau Fail2Ban.
- Backend menormalisasi respons dari sumber berbeda ke format JSON yang konsisten sesuai kontrak API aktual.
- API menggunakan JSON sebagai format pertukaran data.
- Laptop monitoring menjalankan backend Flask dan frontend dashboard serta mengendalikan pengujian QoS iperf3 sesuai topologi client-server yang disepakati. Pengukuran network traffic/flow dilakukan pada laptop monitoring dengan metode yang ditetapkan tim.
- iperf3 harus dijalankan sebagai pengujian terkonfigurasi, bukan diperlakukan sebagai sumber data pasif yang selalu menghasilkan sampel baru. Hindari menjalankan tes berulang tanpa jeda yang disepakati karena dapat menambah beban jaringan dan memengaruhi hasil.
- API server LightGBM, Random Forest, dan Fail2Ban dapat diakses dari laptop monitoring; backend mengambil data dari ketiga API tersebut sesuai kontrak yang tersedia.
- Glances berjalan pada setiap server yang dipantau untuk menyediakan data CPU dan memori.
- Backend menormalisasi respons API ke format JSON yang konsisten dan mempertahankan timestamp, identitas sumber, satuan, serta status data jika tersedia.
- URL endpoint dan konfigurasi integrasi disimpan dalam environment backend; token Telegram tetap berada di backend dan tidak terekspos ke frontend.
- Dashboard dapat melakukan parsing dan validasi data JSON.
- Dashboard dapat menampilkan grafik network traffic/flow yang diperbarui setiap 5 detik.
- Dashboard dapat menampilkan nilai QoS real-time berupa delay, jitter, packet loss, dan throughput, beserta unit dan timestamp.
- Dashboard dapat menampilkan CPU usage dan memory usage untuk setiap VM yang dipantau.
- Dashboard dapat menampilkan daftar IP yang status blokirnya dikonfirmasi oleh Fail2Ban atau sumber pemblokiran yang digunakan.
- Dashboard dapat menampilkan attack history yang berisi waktu, source IP, jenis serangan, dan hasil deteksi jika tersedia.
- Dashboard dapat menampilkan status atau riwayat Telegram alert jika informasi tersebut disediakan backend.
- Dashboard dapat membedakan data aktual, data kedaluwarsa, dan data yang belum tersedia jika informasi pendukung tersedia.
- Dashboard menggunakan Chart.js untuk visualisasi grafik.
- Dashboard memperbarui komponen monitoring secara berkala tanpa reload seluruh halaman.
- Sistem mengirimkan alert ke Telegram ketika SSH Brute Force terdeteksi dan kondisi pemicu terpenuhi.
- Notifikasi Telegram memuat informasi dasar serangan dan status blocking jika tersedia.
- Pengiriman notifikasi tidak boleh mengekspos token Telegram atau mengganggu proses monitoring.

### 10.1 Database dan Persistensi Data

Sistem menggunakan SQLite melalui backend Flask hanya untuk menyimpan data akun pengguna yang diperlukan untuk Register, Login, dan pengelolaan akses dashboard.

Data akun yang disimpan dapat mencakup:
- ID pengguna sebagai primary key.
- Username dengan nilai unik.
- Password hash, bukan password plaintext.
- Created_at jika diperlukan.

SQLite tidak digunakan untuk menyimpan network traffic/flow, QoS, CPU/memori, daftar blocked IP, attack history, atau status/riwayat Telegram. Data monitoring diperoleh dari API sumber terkait atau dari pengukuran lokal pada laptop monitoring. Persistensi data monitoring atau alert, jika diperlukan di kemudian hari, harus disepakati sebagai perubahan ruang lingkup terpisah.

Ketentuan database:
- Frontend mengambil data melalui backend/API dan tidak mengakses database secara langsung.
- Backend bertanggung jawab atas validasi serta operasi baca dan tulis data ke database.
- API menyediakan data kepada frontend dalam format JSON.
- Data historis harus memiliki timestamp yang sesuai.
- Password pengguna harus disimpan dalam bentuk hash yang aman, bukan plaintext.
- Kredensial database harus disimpan secara aman di konfigurasi backend dan tidak diekspos ke browser.
- SQLite digunakan hanya untuk akun pengguna; skema tabel final dapat ditetapkan tim sesuai kebutuhan autentikasi.
- Backend Flask bertanggung jawab atas operasi baca/tulis SQLite; frontend tidak mengakses database secara langsung.

Data monitoring terkini tidak harus disimpan secara permanen. Keputusan penyimpanan sampel historis ditentukan berdasarkan kebutuhan pengujian dan analisis.

Kriteria penerimaan:
- Backend dapat membuat akun dan memvalidasi login melalui SQLite dengan password yang tersimpan sebagai hash.
- Dashboard mengambil data melalui backend/API.
- Data yang tidak tersedia atau sudah kedaluwarsa tidak ditampilkan seolah-olah merupakan data terbaru.

---

## 11. Non-Functional Requirements

### Performance
- Data monitoring diperbarui setiap 5 detik sebagai interval polling yang ditetapkan.
- Grafik dan komponen dashboard diperbarui tanpa reload seluruh halaman.
- Request API dikelola agar tidak dilakukan secara berlebihan.
- Timestamp ditampilkan agar pengguna dapat mengetahui waktu pengukuran atau pembaruan data.
- Jika sumber data tidak dapat diakses, dashboard menampilkan status error/koneksi atau data tidak tersedia dengan jelas.

### Usability
- Dashboard menggunakan desain responsif agar dapat digunakan pada laptop/desktop, tablet, dan perangkat mobile melalui browser.
- Pada layar kecil, enam komponen Overview harus menyesuaikan ukuran dan susunan tata letak tanpa kehilangan informasi penting; tabel dan grafik harus tetap dapat dibaca atau digulir secara wajar.
- Informasi utama harus mudah dibaca.
- Metrik QoS menggunakan satuan yang sesuai dan konsisten.
- Status deteksi dan status blocking dapat dibedakan dengan jelas.
- Informasi Telegram alert dibuat ringkas dan mudah dipahami.
- Loading, empty, dan error states tersedia untuk komponen utama.

### Security
- Akses dashboard dibatasi melalui autentikasi pengguna.
- Kredensial pengguna dikelola dan disimpan secara aman sesuai implementasi backend.
- Endpoint monitoring hanya dapat diakses sesuai kebijakan akses sistem.
- Data monitoring yang ditampilkan tidak mengandung kredensial.
- Token atau credential Telegram tidak ditampilkan pada dashboard maupun kode frontend.
- Input pengguna divalidasi dan sesi ditangani dengan aman.

### Data Integrity
- Data monitoring harus berasal dari sumber yang sesuai.
- Timestamp dan unit data dipertahankan saat data ditampilkan.
- Prediksi serangan tidak boleh disamakan dengan status IP terblokir.
- Data contoh atau simulasi harus diberi label dan tidak boleh disajikan sebagai data aktual.

---

## 12. MVP Scope

### Termasuk

- Register, Login, dan Logout.
- Pembatasan akses Dashboard Overview berdasarkan autentikasi.
- Overview dashboard yang memuat enam komponen: network traffic/flow, QoS real-time, CPU/memory usage, blocked IP list, attack history, dan Telegram alert status/history.
- Monitoring QoS: delay, jitter, packet loss, dan throughput.
- Monitoring CPU usage dan memory usage secara real-time pada VM yang dipantau.
- Pembaruan data setiap 5 detik tanpa reload seluruh halaman.
- Daftar IP yang diblokir berdasarkan status aktual Fail2Ban atau sumber pemblokiran yang digunakan.
- Attack history dan informasi deteksi yang tersedia.
- Visualisasi menggunakan Chart.js.
- Backend/API dan pertukaran data JSON.
- Integrasi Telegram untuk notifikasi alert SSH Brute Force.
- Tampilan loading, empty, error, dan timestamp pembaruan yang sesuai.

### Tidak Termasuk dalam MVP

- Evaluasi model LightGBM dan Random Forest pada Dashboard Overview.
- Perbandingan ML dengan Fail2Ban pada Dashboard Overview.
- Aplikasi mobile native terpisah (dashboard diakses melalui browser responsif, bukan aplikasi Android/iOS khusus).
- Billing.
- Business integrations.
- Custom dashboard builder.
- AI insights dan predictive forecasting.
- WebSocket untuk pembaruan data.

---

## 13. Future Development

- WebSocket atau mekanisme push untuk pembaruan data tanpa polling.
- Visualisasi network traffic/flow yang lebih lanjut.
- Analisis dan pencarian data historis.
- Export data monitoring dan attack history.
- Filtering dan pengaturan alert yang lebih lanjut.
- Perluasan jumlah server yang dipantau di luar tiga server yang telah tersedia.
- Halaman terpisah untuk evaluasi model atau perbandingan sistem jika nantinya dibutuhkan kembali.

---

## 14. Acceptance Criteria

- Pengguna dapat melakukan registrasi akun.
- Pengguna dapat login menggunakan akun yang terdaftar.
- Pengguna yang belum login tidak dapat mengakses Dashboard Overview.
- Pengguna dapat logout dan sesi berakhir.
- Dashboard dapat dibuka melalui laptop/desktop maupun browser perangkat mobile setelah pengguna berhasil login.
- Tata letak dashboard menyesuaikan ukuran layar perangkat dan seluruh enam komponen Overview tetap dapat diakses.
- Dashboard menerima dan memproses JSON response dari backend/API.
- Backend dapat mengakses API server LightGBM, Random Forest, dan Fail2Ban dari laptop monitoring.
- CPU dan memori tiap server yang dipantau berasal dari Glances pada server tersebut.
- Network traffic/flow dan QoS diukur pada laptop monitoring berdasarkan metode yang disepakati tim.
- Grafik network traffic/flow menampilkan data aktual dan diperbarui selama pengujian.
- Delay, jitter, packet loss, throughput, CPU usage, dan memory usage ditampilkan dengan satuan yang sesuai serta timestamp pengukuran.
- Dashboard menampilkan sumber/VM yang sesuai untuk data resource apabila beberapa VM dipantau.
- Blocked IP List hanya menampilkan IP yang status pemblokirannya dikonfirmasi oleh Fail2Ban atau sumber pemblokiran.
- Attack history menampilkan waktu, source IP, jenis serangan, dan hasil deteksi jika tersedia.
- Dashboard menampilkan status atau riwayat Telegram alert jika data tersebut disediakan backend.
- Alert Telegram berhasil dikirim ketika serangan SSH Brute Force memenuhi kondisi pemicu.
- Alert Telegram memuat informasi serangan yang tersedia dan tidak mengekspos token bot.
- Dashboard memperbarui data setiap 5 detik tanpa reload seluruh halaman.
- Dashboard menampilkan status yang jelas ketika data kosong, sumber tidak dapat diakses, atau data kedaluwarsa.
- Dashboard Overview tidak menampilkan bagian evaluasi LightGBM vs Random Forest maupun perbandingan ML vs Fail2Ban.

---

## 15. Technology / Tools

| Kategori | Software / Tools | Fungsi |
|---|---|---|
| Backend | Flask | Server dan endpoint monitoring serta autentikasi sesuai implementasi |
| API Client | Requests | Mengambil data monitoring dari API di sisi backend |
| Data Format | JSON | Pertukaran data antara dashboard, backend, dan sumber monitoring |
| Frontend | HTML, CSS, JavaScript | Struktur dan tampilan dashboard |
| Visualisasi | Chart.js | Grafik network traffic/flow dan metrik QoS/resource |
| Resource Monitoring | Glances | Mengambil metrik CPU dan memori dari setiap server yang dipantau |
| QoS Testing | iperf3 | Pengujian throughput jaringan; pengujian UDP juga dapat menyediakan jitter dan packet loss |
| Model ML | LightGBM, Random Forest | Komponen sistem deteksi SSH Brute Force di backend/VM, bukan komponen evaluasi pada Overview |
| Blocking | Fail2Ban | Sumber status IP yang diblokir jika digunakan dalam implementasi |
| Database | SQLite | Menyimpan data akun pengguna untuk Register/Login saja |
| Notification | Telegram Bot API | Pengiriman alert serangan melalui backend |
| Virtualisasi | VirtualBox | Menjalankan lingkungan VM |


## Konfigurasi Environment dan Penyimpanan API

Semua konfigurasi URL API/endpoint dan nilai konfigurasi terkait integrasi eksternal harus dikelola melalui file `.env`, bukan ditulis langsung (hardcode) di kode aplikasi. Gunakan nama variabel yang disepakati, misalnya `API_BASE_URL` sebagai contoh nama konfigurasi dasar; nama final mengikuti kontrak proyek.

Contoh struktur `.env` (gunakan nilai lokal/rahasia yang sesuai; jangan mengisi kredensial nyata ke dokumentasi atau repository):

```dotenv
API_BASE_URL=http://localhost:5000
# Contoh endpoint API sumber data; sesuaikan dengan kontrak endpoint aktual:
# LIGHTGBM_API_URL=
# RANDOM_FOREST_API_URL=
# FAIL2BAN_API_URL=
# GLANCES_LIGHTGBM_URL=
# GLANCES_RANDOM_FOREST_URL=
# GLANCES_FAIL2BAN_URL=
# IPERF3_CLIENT_HOST=
# IPERF3_SERVER_HOST=
# IPERF3_TEST_PROTOCOL=udp
# IPERF3_TEST_DURATION_SECONDS=
# IPERF3_TEST_INTERVAL_SECONDS=
# TELEGRAM_BOT_TOKEN=
```

Catatan keamanan:
- `.env` adalah file konfigurasi environment, bukan tempat menyimpan seluruh implementasi/source code API.
- Jika yang dimaksud “semua API disimpan di `.env`” adalah URL endpoint dan konfigurasi API, simpan nilai konfigurasi tersebut di `.env`; kode pemanggil API tetap berada di file service/backend yang sesuai.
- Jangan commit `.env` yang berisi token, password, atau secret ke Git. Tambahkan `.env` ke `.gitignore`.
- Sediakan `.env.example` berisi nama variabel dan placeholder tanpa nilai rahasia agar anggota tim mengetahui konfigurasi yang diperlukan.
- Pada frontend browser, jangan memasukkan secret seperti `TELEGRAM_BOT_TOKEN` ke environment variable yang akan dibundel/ditampilkan ke client. Token Telegram harus tetap di backend/server. Frontend hanya menggunakan konfigurasi publik yang memang aman untuk diketahui browser.
- Jika frontend dan backend berjalan sebagai aplikasi terpisah, tentukan `.env` masing-masing sesuai mekanisme framework/build tool; variabel rahasia hanya dibaca di backend.