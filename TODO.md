# 📋 TODO — Sales AI Assistant (AI-Powered Sales Assistant for WhatsApp Business)

**PRD:** v1.0 (2026-08-05) · **Status:** Iterasi v3 · **Update:** 2026-08-12 (v0.4.2)

## ✅ SUDAH DILAKUKAN

### Frontend (Prototype) — `/home/adminicc/workspace/sales-ai-assistant/index.html`
- [x] Prototype 1 file HTML self-contained (dark-first + light mode, palet ICC #1A56DB/#F97316/Inter)
- [x] **Dashboard**: 5 stat cards (Chat Masuk, Hot/Warm/Cold Lead, Avg Response) + Lead Distribution + Chat Activity 7 hari + Top Products + Response Time Trend
- [x] **Dashboard date range filter** (Hari ini / 7 hari / 30 hari) — semua angka & chart ikut berubah
- [x] **Dashboard auto-refresh** 30 detik (simulasi)
- [x] **Inbox**: 3 panel (list chat / chat detail / AI Analysis)
  - [x] List chat: badge Hot/Warm/Cold + unread, search nama/nomor, filter kategori
  - [x] Chat detail: bubble percakapan + komposer manual + tombol Kirim
  - [x] AI Analysis: score ring, 6 komponen berbobot, labels, Suggested Reply (confidence + sources + Regenerate/Copy/Kirim + feedback 👍👎)
- [x] **Knowledge Base**: 6 kartu kategori, tabel dokumen (edit/hapus), statistik
- [x] **KB upload file** (dropzone PDF/DOCX/TXT/MD/CSV + simulasi chunking)
- [x] **KB version history** (list versi + restore)
- [x] **Notifikasi chat baru** (simulasi 45 detik, bisa toggle)
- [x] **WebSocket real-time** ke backend (chat masuk langsung muncul, fallback ke simulasi jika backend mati, auto-reconnect 5 dtk)
- [x] Responsive (drawer sidebar < 900px), theme toggle persist localStorage
- [x] Verifikasi: 0 JS error, QA visual Playwright bersih, E2E PASS
- [x] **Integrasi real (v0.4.1)**: Dashboard & KB tidak lagi simulasi
  - [x] `GET /api/v1/stats` (chat_count, hot/warm/cold + %, distribution, activity 7 hari, top_products) — dibaca dashboard
  - [x] Dashboard: stat cards, Lead Distribution bar, Chat Activity, Top Products, Response Trend di-render dari API (auto-refresh 30 dtk)
  - [x] Status pills topbar diisi dari `/health` (Groq/Fonnte/WebSocket)
  - [x] KB list/filter kategori/statistik dari `GET /api/v1/knowledge` (kategori disatukan: BNSP/Kemnaker RI/Reguler/Umum)
  - [x] Edit dokumen via `PUT /api/v1/knowledge/{id}` (re-chunk otomatis), hapus via `DELETE`, detail via `GET .../doc/{id}`
  - [x] Fix: `upload_knowledge` pakai `Form(...)` agar category/name terbaca (sebelumnya selalu default Umum)
  - [x] Fix: `process_incoming` simpan category/score/badge ke store in-memory (sebelumnya mutasi dict salinan)
- [x] **Inbox persisten + Login UI + Loading/Error/A11y (v0.4.2)**
  - [x] `send_message` kini simpan pesan keluar (in-memory + Supabase `chats` + update last_message customer)
  - [x] Endpoint `GET /api/v1/customers/{phone}/messages` — riwayat chat per customer (Supabase fallback in-memory)
  - [x] Inbox load riwayat chat saat chat dibuka (`loadMessages`), pesan keluar muncul lagi setelah refresh
  - [x] Login UI: modal username/password → `/api/v1/auth/login` → token disimpan di localStorage; logout; otomatis muncul jika `auth_enabled` dan belum ada token; ganti `prompt()` pada 401
  - [x] Loading/error state: spinner pada dashboard/KB, error + tombol "Coba lagi", toast error inbox
  - [x] A11y: `role="dialog"`/`aria-modal`/aria-label pada modal & tombol icon, `aria-live` pada toast, focus otomatis saat modal buka, Escape menutup modal, `:focus-visible`

### Backend (FastAPI) — `/home/adminicc/workspace/sales-ai-backend/`
- [x] `main.py` — 6 endpoint + WebSocket
  - [x] `GET /health` — status + groq_ready
  - [x] `POST /webhook/fonte` — terima chat masuk + verifikasi token webhook + scoring otomatis
  - [x] `POST /api/v1/assessment/analyze` — lead scoring 6 komponen (format PRD 5.1.4)
  - [x] `POST /api/v1/reply/generate` — suggested reply + confidence + sources (format PRD 5.2.4)
  - [x] `POST /api/v1/messages/send` — kirim balasan via Fonte API
  - [x] `GET /api/v1/customers` — list customer
  - [x] `WS /ws` — broadcast chat_incoming ke frontend (ConnectionManager)
- [x] `profile_name` support (nama WA asli tampil di inbox)
- [x] CORS enabled (dev), .env.example + requirements.txt
- [x] **Keamanan v0.4**: webhook token (`WEBHOOK_SECRET`, header `x-webhook-token` / query `?token=`), auth JWT + API token di semua `/api/v1/*`, CORS restricted (`CORS_ORIGINS`), rate limiting in-memory, parse payload aman, XSS escaping di frontend, `AI_LOGS` di-cap
- [x] Terverifikasi live: semua endpoint 200, WebSocket E2E PASS (webhook → scoring → broadcast → muncul di Inbox <1 dtk)

### Proses
- [x] Email review v1, v2, v3 → dwifajar15@gmail.com
- [x] Backup v1: `index-v1-backup.html`

## ⏳ BELUM DILAKUKAN (butuh akses/keputusan Anda)

### WA Asli — Fonnte ✅ JALAN
- [x] **Fonnte token** terpasang & valid (device 6285328883511, quota 1000)
- [x] **Kirim WA asli** via `/api/v1/messages/send` → api.fonnte.com ✅ (tes ke 0821-3322-3330 sukses)
- [x] **Webhook URL** di dashboard Fonnte (Device → Edit) → `https://amcicccrm.my.id/salesai/webhook/fonnte`
- [x] **Auto Read ON** (device-status webhook aktif)
- [x] **WA masuk → app** ✅ E2E: pesan asli dari 0821-3322-3330 (Mas Fajar) → webhook → Groq score 69 Warm → broadcast → Inbox
- [x] **Parser format asli Fonnte** (`sender`/`message`/`name` + skip device-status `stateid`)
- [x] **Balas dari app → WA** (tombol Kirim → backend → Fonnte; fallback simulasi jika offline)

### AI Asli — Groq
- [x] **GROQ_API_KEY terpasang** di `.env` — `groq_ready: true`
- [x] **GroqClient asli** (bukan stub): assessment + reply via `llama-3.3-70b-versatile` JSON mode
  - [x] Assessment: 0.4s, lead 84 Hot, label AI asli (PRD 6.3.1)
  - [x] Reply: 0.7s, suggested_reply + confidence + sources + fallback (PRD 6.3.2)
  - [x] Fallback rule-based otomatis jika Groq error
- [ ] RAG penuh: query knowledge base (chunks) sebagai konteks reply (saat ini context manual/kosong)

### Database & Persistensi
- [x] `/api/v1/customers` kini baca gabungan in-memory + Supabase (customer lama muncul lagi setelah restart) — v0.4
  - [x] Auth JWT + API token di semua `/api/v1/*` (login `/api/v1/auth/login`, `ADMIN_USER`/`ADMIN_PASSWORD`/`API_TOKEN`) — PRD 9.2
  - [x] **Multi-User (v0.5):** store SQLite (`data/app.db`) — tabel `users`/`customers`/`chats`/`knowledge_base`/`products`, semua data di-scope per `owner_id`
  - [x] **Login page** full-screen + profil (`/api/v1/me`, PUT ganti password/token Fonnte/Groq)
  - [x] **RBAC Admin (super-admin) vs User:** admin lihat & kelola SEMUA data user (`?owner=all` / `?owner=<uid>`) + CRUD user (`/api/v1/admin/users`); user hanya data sendiri
  - [x] **Per-user WhatsApp:** tiap user punya Fonnte token/nomor sendiri; webhook `?uid=<id>` memetakan pesan masuk ke owner; pengiriman pakai token owner
  - [x] **Frontend beda Admin/User:** nav Users + scope selector hanya untuk admin; user punya halaman Profil untuk set token sendiri; login menutupi app sampai sesi valid
  - [ ] PostgreSQL + PgVector (ganti mock `CUSTOMERS`/`LEAD_SCORES`/`AI_LOGS`)
- [ ] Simpan messages, lead_scores, ai_reply_logs (schema PRD 6.2)
- [ ] RBAC penuh (Admin/Sales Manager/Sales) — PRD 9.2

### Deployment
- [ ] Deploy backend ke VPS 31.97.109.249 (systemd/Docker)
- [ ] Ubah `ws://localhost:8000/ws` di frontend → `wss://<domain>/ws`
- [ ] Serve frontend di domain publik (atau pindah ke Next.js sesuai PRD 8.2)
- [ ] Domain + HTTPS (TLS 1.2+) + reverse proxy (nginx sudah ada di VPS)
- [ ] Set `WEBHOOK_SECRET` & tambahkan `?token=...` pada URL webhook di dashboard Fonnte
- [ ] Set `JWT_SECRET_KEY` + `ADMIN_PASSWORD` (atau `API_TOKEN`) sebelum go-live

### QA & Penutup
- [ ] UAT lengkap dengan sales/manager (persona PRD 4)
- [ ] Retry/backoff Groq (PRD 6.5) — rate limiting in-memory sudah ada
- [ ] Notifikasi chat baru (Web Push / Telegram) saat sales offline

## 🔜 FUTURE (Out of Scope MVP — PRD 3.2)
- [ ] Auto-reply penuh, integrasi CRM lain, mobile app, multichannel (Telegram/LINE/Email), advanced analytics, sentiment real-time
