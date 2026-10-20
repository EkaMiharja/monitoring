SSH Sentinel - QoS remote-agent integration patch

Isi:
- apply_patch.py: patch otomatis untuk proyek Dashboard yang struktur filenya cocok dengan cuplikan yang diberikan.
- remote_metrics.py: SQLite store bagi data QoS yang diterima dari VM agent.

Cara pakai di Windows:
1. Hentikan SSH Sentinel yang sedang berjalan.
2. Salin apply_patch.py dan remote_metrics.py ke root proyek:
   C:\Users\eka\PycharmProjects\Dashboard
   (remote_metrics.py boleh ikut disalin ke root untuk kebutuhan script; patch akan memasukkannya ke services\remote_metrics.py)
3. Buka PowerShell di root proyek, aktifkan venv seperti biasa, lalu jalankan:
   & .\.venv\Scripts\python.exe .\apply_patch.py
4. Patch membuat backup timestamped .qos-integration-backup-... sebelum mengubah file.
5. Buka .env secara lokal untuk mendapatkan REMOTE_METRICS_TOKEN dan salin nilainya ke agent.env di VM. Jangan kirim token ke chat atau commit ke Git.
6. Setelah endpoint dan agen siap, ubah DATA_MODE=live di .env, lalu mulai ulang SSH Sentinel.
7. Jalankan test proyek sebelum dipakai.

Payload JSON yang didukung (semua field metrik opsional, minimal satu angka diperlukan):
{
  "timestamp": "2026-10-20T05:00:00+00:00",
  "delay_ms": 12.5,
  "packet_loss_percent": 0,
  "throughput_mbps": 40.4,
  "jitter_ms": 3.215,
  "cpu_percent": 15.2,
  "memory_percent": 27.6
}

Endpoint: POST /api/metrics
Header: Authorization: Bearer <REMOTE_METRICS_TOKEN>
Content-Type: application/json

Catatan:
- Endpoint autentikasi khusus agen, tidak memakai session login atau CSRF. Bearer token wajib.
- DB disimpan persisten di instance/remote_metrics.db secara default.
- Patch tidak membuat endpoint /health.
- Patch otomatis memodifikasi config.py, api/routes.py, dan services/providers/live.py.
- Karena patch dibuat dari cuplikan kode yang Anda kirim, script memverifikasi anchor; jika struktur file berbeda, ia berhenti dengan pesan error alih-alih melakukan penggantian yang ambigu.
