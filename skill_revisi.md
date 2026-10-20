# skill.md — Panduan Implementasi Dashboard Monitoring SSH Brute Force

## 1. Tujuan Dokumen

Dokumen ini menjadi panduan teknis untuk mengimplementasikan frontend dashboard dan integrasi notifikasi Telegram pada proyek PBL deteksi SSH Brute Force. Gunakan bersama `task.md`, `desain.md`, dan PRD terbaru. Dashboard adalah web responsif yang sama untuk laptop/desktop, tablet, dan browser HP; aplikasi native Android/iOS tidak termasuk cakupan. Arsitektur yang disepakati menempatkan backend Flask di laptop monitoring. Jika terdapat perbedaan, konfirmasikan ke tim sebelum mengubah ruang lingkup.

Fokus implementasi:
- Login, register, dan logout.
- Dashboard Overview untuk pemantauan sistem.
- Integrasi data dari backend melalui API/JSON.
- Pembaruan tampilan berkala setiap 5 detik.
- Tampilan status dan riwayat notifikasi Telegram.

Dokumen ini bukan daftar tugas dan tidak menetapkan endpoint API, framework frontend, atau format payload yang belum disepakati tim.

## 2. Batasan Ruang Lingkup

Dashboard Overview hanya memuat komponen berikut:

1. Grafik traffic/flow jaringan.
2. Monitoring QoS: delay, jitter, packet loss, dan throughput.
3. Penggunaan CPU dan memori.
4. Daftar IP yang diblokir.
5. Riwayat serangan.
6. Status dan riwayat notifikasi Telegram.

Login, register, dan logout tetap termasuk ruang lingkup aplikasi.

Jangan menambahkan evaluasi model LightGBM vs Random Forest atau perbandingan ML vs Fail2Ban ke Dashboard Overview. Status IP yang diblokir harus berasal dari data Fail2Ban yang terkonfirmasi; prediksi model saja tidak membuktikan bahwa IP sudah diblokir.

## 3. Prinsip Implementasi

- **Ikuti kontrak API tim.** Sepakati endpoint, metode HTTP, autentikasi, skema JSON, satuan, timestamp, dan format error dengan pengembang backend. Jangan mengarang endpoint atau nama field untuk dianggap final.
- **Pisahkan UI dari data.** Komponen tampilan menerima data terstruktur; fungsi API menangani request, autentikasi, validasi dasar, dan error.
- **Tampilkan keadaan dengan jujur.** Bedakan data terbaru, data lama, data kosong, dan kegagalan mengambil data.
- **Jangan menganggap mock sebagai fitur selesai.** Data dummy boleh dipakai saat pengembangan, tetapi harus diberi label dan tidak dihitung sebagai integrasi live.
- **Jangan mengasumsikan sumber data.** Tiap panel perlu memiliki sumber, waktu pengambilan, satuan, dan aturan pembaruan yang jelas.
- **Jaga rahasia.** Token Telegram dan kredensial sensitif hanya berada di backend atau konfigurasi rahasia server.

## 4. Teknologi dan Batas Tanggung Jawab

Gunakan teknologi yang sudah disepakati dalam proyek. Berdasarkan rancangan saat ini, teknologi yang relevan meliputi:

- **HTML/CSS/JavaScript:** struktur, gaya, dan interaksi frontend jika menggunakan pendekatan web standar.
- **Chart.js:** grafik traffic/flow dan visualisasi QoS atau metrik historis bila sesuai.
- **Flask:** backend/API Python yang berjalan di laptop monitoring.
- **Requests HTTP dan JSON:** backend Flask mengambil data dari API yang sudah tersedia di server LightGBM, Random Forest, dan Fail2Ban, serta dari Glances pada setiap server. Frontend mengambil data normalisasi dari backend Flask.
- **Pengukuran jaringan/QoS:** dilakukan di laptop monitoring, bukan diasumsikan berasal dari API ketiga server. Metode, arah, interface, dan periode observasi harus dikonfirmasi dengan tim.
- **SQLite:** hanya untuk data akun Register/Login (username unik, password hash, dan metadata akun); bukan untuk menyimpan telemetry atau riwayat monitoring.
- **Glances:** sumber metrik CPU dan memori pada VM yang dipantau, diakses melalui mekanisme yang disepakati dengan backend.
- **iperf3:** alat uji jaringan aktif untuk mengukur throughput; pada mode UDP, hasilnya juga dapat mencakup jitter dan packet loss. Backend mengorkestrasi/mengambil hasil pengujian sesuai konfigurasi yang disepakati, bukan menganggap iperf3 sebagai telemetry pasif.
- **Telegram Bot API:** pengiriman notifikasi melalui backend, bukan langsung dari browser.

Jangan menambahkan framework baru hanya karena panduan ini menyebutkannya. Pastikan versi, dependensi, dan cara menjalankan aplikasi konsisten dengan repository dan keputusan tim.

## 5. Struktur Frontend yang Disarankan

Sesuaikan struktur berikut dengan struktur repository yang sudah ada. Ini contoh pengelompokan tanggung jawab, bukan kewajiban nama file.

```text
frontend/
├── pages/          # Login, Register, Dashboard
├── components/     # Kartu metrik, tabel, grafik, status
├── services/       # Client API dan fungsi autentikasi
├── charts/         # Konfigurasi grafik
├── styles/         # Token desain, layout, komponen
└── utils/          # Format angka, waktu, validasi data
```

Prinsip:
- Satu komponen memiliki tanggung jawab yang jelas.
- Hindari menaruh seluruh request API, rendering grafik, dan logika autentikasi dalam satu file besar.
- Gunakan satu fungsi bersama untuk menangani format waktu, angka, satuan, dan pesan error.
- Simpan konfigurasi URL backend di konfigurasi environment yang sesuai; jangan menyebarkan URL API ke banyak file.

## 6. Kontrak Data API

Sebelum integrasi, sepakati hal berikut dengan tim backend untuk setiap endpoint:

- Tujuan endpoint dan metode HTTP.
- Bentuk respons sukses dan respons error.
- Skema field serta tipe datanya.
- Satuan metrik, misalnya ms untuk delay/jitter, persen untuk packet loss, dan satuan throughput yang disepakati.
- Timestamp dan zona waktu.
- Sumber data dan identitas VM/host.
- Arti status, termasuk status pemblokiran Fail2Ban dan status pengiriman Telegram.
- Metode autentikasi serta perilaku ketika sesi kedaluwarsa.
- Batas frekuensi request dan kemungkinan pagination untuk riwayat.

Contoh payload berikut **hanya ilustrasi format**, bukan kontrak API final:

```json
{
  "timestamp": "2026-10-19T10:15:00Z",
  "source": "nama-sumber-yang-disepakati",
  "data": []
}
```

Jangan menampilkan nilai yang tidak tersedia seolah-olah bernilai nol. Nol adalah nilai pengukuran; `null` atau data yang tidak ada berarti nilai belum tersedia. Validasi tipe dan struktur respons sebelum menggunakannya di grafik atau tabel.

## 7. Pengambilan Data dan Refresh 5 Detik

Interval 5 detik adalah **interval pembaruan UI/request polling**, bukan jaminan bahwa sumber metrik mengukur atau menghasilkan data baru setiap 5 detik.

Pedoman:
- Gunakan satu mekanisme polling terpusat untuk data dashboard bila memungkinkan.
- Hindari request yang saling tumpang tindih. Jangan memulai siklus baru jika siklus sebelumnya belum selesai, atau gunakan mekanisme setara yang mencegah overlap.
- Hentikan timer dan batalkan request yang masih berjalan saat pengguna meninggalkan halaman atau komponen dilepas.
- Tangani timeout, HTTP error, respons JSON tidak valid, dan koneksi backend yang terputus.
- Jangan menghapus data valid terakhir secara diam-diam saat request gagal. Pertahankan data terakhir dan beri indikator bahwa data sudah usang, beserta waktu pembaruan terakhir.
- Berikan indikator loading saat pengambilan pertama, empty state jika belum ada data, dan error state jika pengambilan gagal.
- Pertimbangkan polling terpisah untuk riwayat yang jarang berubah jika disepakati tim; jangan membebani backend dengan request yang tidak perlu.
- Jangan membuat grafik berkedip atau merender ulang seluruh halaman pada setiap polling. Perbarui data grafik/tabel secara terarah.

## 8. Panduan untuk Setiap Panel Dashboard

### 8.1 Grafik traffic/flow jaringan
- Gunakan waktu pada sumbu X dan metrik yang disepakati pada sumbu Y.
- Beri label sumbu, satuan, legenda, dan rentang waktu.
- Tampilkan keadaan tanpa data dan kesalahan pengambilan data.
- Pastikan timestamp berurutan dan tangani data hilang tanpa mengarang titik data.
- Jelaskan sumber traffic/flow yang digunakan berdasarkan kontrak backend.

### 8.2 QoS: delay, jitter, packet loss, throughput
- Tampilkan metrik yang didukung oleh hasil pengukuran aktual sebagai nilai yang mudah dibaca dan, jika diperlukan, grafik historis.
- Gunakan iperf3 untuk pengujian throughput; pada UDP, gunakan hasilnya untuk jitter dan packet loss bila tersedia. Jangan mengasumsikan hasil UDP tersedia jika pengujian berjalan pada TCP.
- iperf3 tidak otomatis menggantikan pengukuran delay/latency. Tentukan metode/sumber delay terpisah dan jelaskan metode serta timestamp-nya; jika belum ada, tampilkan “Belum tersedia”.
- Dokumentasikan host client/server, protokol, arah, durasi/interval pengujian, dan waktu hasil. Jalankan tes sesuai jadwal/trigger yang disepakati, bukan otomatis setiap 5 detik hanya karena UI melakukan polling.
- Cantumkan satuan secara eksplisit dan konsisten.
- Tampilkan timestamp pengukuran dan sumbernya.
- Jangan membandingkan nilai yang memakai metode pengukuran atau interval berbeda tanpa penjelasan.
- Jika suatu metrik belum diimplementasikan di backend, tampilkan “Belum tersedia” alih-alih angka contoh yang tampak nyata.


#### Ketentuan visualisasi dan statistik QoS
Untuk setiap metrik QoS—delay/latency, jitter, packet loss, dan throughput—sajikan visualisasi dan ringkasan statistik yang mudah dipahami. Statistik mencakup **Min**, **Max**, dan **Avg (Mean)**.

- Pilih bentuk visualisasi yang sesuai dengan kebutuhan monitoring dan data yang tersedia; tata letak visual tidak ditetapkan secara kaku.
- Min adalah nilai minimum, Max nilai maksimum, dan Avg (Mean) rata-rata aritmetika sampel pada periode yang sama dengan grafik.
- Visualisasi dan statistik yang ditampilkan harus mengacu pada rentang data/periode yang konsisten.
- Cantumkan satuan, rentang waktu, timestamp, dan sumber data yang relevan.
- Gunakan hasil pengukuran aktual; jangan menampilkan data dummy seolah-olah data live.
- Interval pembaruan UI adalah 5 detik, tetapi tidak menjamin sumber pengukuran menghasilkan sampel baru setiap 5 detik.
- Periode perhitungan statistik harus disepakati secara eksplisit dengan tim; jangan mengasumsikannya.
- Threshold/batas baik-buruk ditunda dan tidak termasuk implementasi saat ini.

### 8.3 CPU dan memori (System Resource Monitoring)
- Gunakan Glances yang berjalan pada setiap server yang dipantau sebagai sumber metrik, sesuai konfigurasi dan akses yang ditetapkan tim. Backend Flask di laptop monitoring mengambil data melalui akses yang disepakati.
- Ambil data melalui backend/API yang disepakati; hindari browser mengakses layanan monitoring VM secara langsung jika arsitektur tim menetapkan akses melalui backend.
- Pantau **CPU Usage (%)** dan **Memory Usage (%)** untuk setiap VM yang dipantau.
- Sajikan visualisasi yang sesuai untuk CPU dan memori, disertai ringkasan statistik **Min**, **Max**, dan **Mean**.
- Visualisasi dan statistik harus memakai sampel serta periode waktu yang sama. Min adalah nilai minimum, Max nilai maksimum, dan Mean rata-rata aritmetika sampel pada periode tersebut.
- Cantumkan satuan, rentang waktu, identitas VM/host, timestamp, dan sumber data yang relevan.
- Gunakan data pemantauan aktual; jangan menampilkan data dummy seolah-olah data live.
- Interval pembaruan UI adalah 5 detik, tetapi tidak menjamin sumber monitoring menghasilkan sampel baru setiap 5 detik. Periode statistik harus disepakati dengan tim.
- Bedakan nilai yang tidak tersedia dari penggunaan 0%. Jika beberapa VM dipantau, beri label jelas agar metrik tidak tertukar.

### 8.4 Daftar IP yang diblokir
- Gunakan data status blokir yang dikonfirmasi dari Fail2Ban atau sumber backend yang setara dan disepakati.
- Tampilkan IP, waktu/status blokir, sumber atau jail jika tersedia, serta status terkini sesuai kontrak data.
- Bedakan daftar blokir aktif dari riwayat blokir.
- Jangan mengubah status menjadi “blocked” hanya berdasarkan prediksi LightGBM atau Random Forest.

### 8.5 Riwayat serangan
- Tampilkan informasi yang benar-benar tersedia, seperti waktu kejadian, IP sumber, target, dan status deteksi jika disediakan backend.
- Gunakan timestamp asli dari sumber data.
- Tetapkan format tanggal/waktu yang konsisten dan tampilkan zona waktu bila relevan.
- Sediakan empty state dan, bila data cukup besar, pagination atau pemuatan bertahap sesuai dukungan API.
- Jangan menggabungkan deteksi model dan blokir Fail2Ban menjadi satu status tanpa aturan yang jelas.

### 8.6 Status dan riwayat notifikasi Telegram
- Tampilkan status pengiriman berdasarkan respons atau log backend, bukan berdasarkan asumsi bahwa request sudah berhasil.
- Bedakan status seperti terkirim, gagal, menunggu, atau status lain yang benar-benar disediakan backend.
- Jika memungkinkan, tampilkan waktu, jenis peristiwa, dan ringkasan hasil pengiriman.
- Jangan menampilkan token bot, secret, atau kredensial di UI, log frontend, repository, atau payload yang dikirim ke browser.
- Kegagalan Telegram harus ditampilkan sebagai kegagalan notifikasi, bukan mengubah status serangan atau blokir.

## 9. Autentikasi dan Keamanan

- Ikuti mekanisme autentikasi yang disepakati backend; jangan membuat skema token sendiri tanpa persetujuan.
- Validasi input form di sisi frontend untuk pengalaman pengguna, tetapi lakukan validasi keamanan utama di backend.
- Tampilkan pesan error yang membantu tanpa membocorkan detail internal server.
- Pastikan halaman dashboard menangani sesi yang tidak valid atau kedaluwarsa dengan benar.
- Jangan menyimpan password dalam plaintext atau memasukkan rahasia ke kode frontend.
- Hindari mencatat password, token sesi, token Telegram, atau data sensitif ke console.
- Untuk deployment, gunakan HTTPS dan konfigurasi cookie/session yang aman sesuai arsitektur.
- Jangan menganggap menyembunyikan tombol atau halaman sebagai pengganti otorisasi di backend.

## 10. Integrasi Telegram

Frontend hanya perlu menampilkan status dan riwayat notifikasi serta, jika diperlukan oleh rancangan, memanggil endpoint backend yang disetujui. Pengiriman pesan ke Telegram dilakukan oleh backend.

Alur umum:
1. Backend menerima atau mendeteksi peristiwa yang memenuhi aturan notifikasi.
2. Backend mengirim pesan melalui Telegram Bot API menggunakan token dari konfigurasi rahasia server.
3. Backend mencatat hasil pengiriman.
4. Frontend mengambil status/riwayat dari API dan menampilkannya dengan timestamp.
5. Jika pengiriman gagal, UI menampilkan status gagal dan tidak mengklaim pesan terkirim.

Aturan tambahan:
- Jangan menaruh token Telegram di JavaScript, HTML, file konfigurasi publik, atau repository.
- Hindari pengiriman notifikasi berulang untuk satu peristiwa kecuali aturan tim memang mengizinkannya.
- Aturan deduplikasi, retry, dan batas frekuensi harus ditentukan pada backend.
- Jangan mengirim data sensitif yang tidak diperlukan ke isi pesan Telegram.

## 11. Desain, Aksesibilitas, dan Responsivitas

- Dashboard harus dapat dibuka dari browser HP sebagai web responsif yang sama; tidak perlu membuat aplikasi native Android/iOS.
- Pada layar HP, susun panel secara vertikal bila perlu, pertahankan keterbacaan grafik dan metrik, dan sediakan scroll horizontal yang disengaja untuk tabel lebar.
- Pastikan keenam komponen Overview tetap dapat diakses pada layar kecil: traffic/flow, QoS, CPU/memori, blocked IP, attack history, dan Telegram alert.
- Jadikan `desain.md` sebagai acuan visual utama dan konfirmasikan jika file tersebut berubah.
- Gunakan token warna, ukuran teks, spacing, radius, dan bayangan secara konsisten.
- Prioritaskan keterbacaan metrik dan status; warna tidak boleh menjadi satu-satunya penanda status.
- Pastikan label form, fokus keyboard, kontras teks, dan pesan validasi dapat digunakan dengan aksesibilitas dasar.
- Tabel panjang harus tetap dapat digunakan pada layar kecil; gunakan layout responsif atau scroll horizontal yang disengaja.
- Grafik perlu memiliki judul/label dan ringkasan tekstual jika memungkinkan.
- Sediakan tampilan konsisten untuk loading, data kosong, data usang, dan error.
- Uji layout desktop dan mobile sesuai kebutuhan demo proyek.

## 12. Penanganan Error dan Observabilitas

Tangani setidaknya:
- Backend tidak dapat dijangkau.
- Request timeout atau dibatasi.
- HTTP 4xx/5xx.
- Respons JSON tidak valid atau field wajib hilang.
- Sesi berakhir.
- Sumber metrik tidak tersedia.
- Riwayat kosong.
- Pengiriman Telegram gagal.

Pesan untuk pengguna harus singkat dan dapat ditindaklanjuti. Detail teknis dapat dicatat di log yang sesuai, tetapi jangan mencatat rahasia. Jika UI menampilkan data terakhir yang berhasil diambil, sertakan waktu pengambilan dan indikator bahwa data belum diperbarui.

## 13. Pengujian Minimum

Lakukan pengujian sesuai task di `task.md` dan cakupan tim:

- Register, login, logout, serta akses halaman ketika sesi tidak valid.
- Respons API sukses, kosong, gagal, lambat, dan memiliki format tidak valid.
- Polling berjalan sesuai interval yang ditetapkan, tidak overlap, dan berhenti saat halaman ditinggalkan.
- Data grafik menggunakan timestamp dan satuan yang benar.
- Nilai `null`/tidak tersedia tidak ditampilkan sebagai nol.
- CPU dan memori diberi label berdasarkan VM/host yang tepat.
- Daftar IP hanya menandai blokir jika sumber data mengonfirmasi.
- Riwayat Telegram menunjukkan hasil dari backend dan tidak membocorkan token.
- Tampilan loading, empty, stale, error, dan responsivitas.
- Pengujian end-to-end menggunakan backend/data uji yang disepakati.

Gunakan data dummy hanya untuk pengujian lokal dan beri label jelas. Catat kasus yang belum dapat diuji karena endpoint atau sumber data belum tersedia.

## 14. Kriteria Kualitas Implementasi

Implementasi dapat dianggap siap ditinjau jika:
- Setiap panel sesuai ruang lingkup dan desain yang disetujui.
- Integrasi memakai kontrak API yang disepakati.
- Timestamp, sumber, satuan, dan status ditampilkan dengan benar.
- Polling 5 detik tidak menyebabkan request menumpuk atau UI berkedip.
- Error dan data usang ditangani secara eksplisit.
- Status blokir berasal dari sumber terkonfirmasi.
- Token Telegram dan kredensial tidak terekspos.
- Login/register/logout berfungsi sesuai mekanisme backend.
- Pengujian yang relevan dijalankan dan keterbatasan yang tersisa didokumentasikan.

## 15. Hal yang Harus Dikonfirmasi dengan Tim

Jangan menebak hal-hal berikut. Sepakati sebelum integrasi final:

- Framework dan versi frontend.
- Struktur repository dan perintah menjalankan aplikasi.
- URL, endpoint, metode HTTP, serta skema JSON final.
- Mekanisme autentikasi, sesi, dan otorisasi.
- VM/host mana yang dipantau dan bagaimana identitasnya direpresentasikan.
- Metode pengukuran, satuan, sumber, dan timestamp QoS.
- Cara backend mengambil data Glances.
- Format riwayat serangan dan sumber status Fail2Ban.
- Format status/log notifikasi Telegram.
- Aturan deduplikasi, retry, dan batas frekuensi Telegram.
- Apakah polling semua panel memakai interval yang sama atau berbeda.

Jika keputusan tersebut belum tersedia, buat komponen dengan batas data yang jelas dan dokumentasikan dependensinya. Jangan menyamarkan asumsi sebagai keputusan tim.


## Konfigurasi Environment dan Penyimpanan API

Semua konfigurasi URL API/endpoint dan nilai konfigurasi terkait integrasi eksternal harus dikelola melalui file `.env`, bukan ditulis langsung (hardcode) di kode aplikasi. Gunakan nama variabel yang disepakati tim, misalnya `API_BASE_URL` sebagai contoh nama konfigurasi dasar; nama final mengikuti kontrak proyek.

Contoh struktur `.env` (gunakan nilai lokal/rahasia yang sesuai; jangan mengisi kredensial nyata ke dokumentasi atau repository):

```dotenv
API_BASE_URL=http://localhost:5000
# Contoh jika proyek membutuhkan endpoint/konfigurasi tambahan:
# AUTH_API_URL=
# QOS_API_URL=
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


## Ringkasan Ketentuan Statistik Monitoring

| Komponen | Metrik | Statistik |
|---|---|---|
| QoS | Delay, Jitter, Packet Loss, Throughput | Min, Max, Avg (Mean) |

Sumber/metode QoS: iperf3 untuk throughput; pada UDP, jitter dan packet loss jika tersedia. Delay/latency memerlukan metode/sumber yang ditentukan terpisah. Jangan tampilkan metrik yang tidak dihasilkan pengukuran sebagai angka live.
| System Resource | CPU Usage, Memory Usage | Min, Max, Mean |

Untuk kedua komponen, visualisasi dan statistik harus menggunakan periode/sampel yang sama. Tampilkan satuan, rentang waktu, timestamp, dan sumber data yang relevan; untuk resource, sertakan identitas VM yang dipantau. Semua nilai harus berasal dari pengukuran aktual. Refresh UI 5 detik bukan jaminan frekuensi sampling sumber. Periode statistik perlu disepakati dengan tim. Threshold QoS tidak termasuk implementasi saat ini.


## 14. Arsitektur Sumber Data yang Disepakati

- Backend Flask berjalan pada laptop monitoring dan menjadi perantara antara frontend dengan sumber data.
- API LightGBM, Random Forest, dan Fail2Ban sudah tersedia dan dapat diakses dari laptop monitoring. Integrasi harus mengikuti endpoint, autentikasi, metode HTTP, dan skema JSON aktual; jangan mengarang kontrak API.
- Glances berjalan pada setiap server yang dipantau dan menjadi sumber CPU/memori.
- Network traffic/flow diukur pada laptop monitoring. Pengujian QoS menggunakan iperf3 dengan laptop monitoring sebagai pengendali/client atau endpoint sesuai topologi yang disepakati; jangan menyatakan bahwa metrik ini berasal dari API LightGBM/RF/Fail2Ban. Konfirmasikan host client/server, protokol TCP/UDP, arah, durasi/interval, jadwal tes, dan metode pengukuran delay dengan tim.
- Backend menormalisasi sumber-sumber tersebut ke JSON untuk frontend. Interval refresh UI 5 detik adalah interval polling/tampilan, bukan jaminan semua sumber menghasilkan sampel baru setiap 5 detik.
- SQLite hanya untuk data akun. Password harus disimpan sebagai hash, bukan plaintext. Jangan menyimpan data telemetry, QoS, attack history, blocked IP, atau riwayat Telegram di SQLite akun berdasarkan rancangan saat ini.
- Token Telegram dan secret lainnya hanya berada di backend/configuration environment. Jangan kirim ke browser, HTML, JavaScript, atau repository.
