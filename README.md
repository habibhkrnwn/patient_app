# Patients App (FastAPI + PostgreSQL + Tailwind)

Implementasi tes kandidat:

- Level 1: CRUD pasien (FastAPI, PostgreSQL, HTML, Tailwind via CDN)
- Level 2: Login sederhana (JWT cookie), tabel users
- Level 3: Role-based access (admin: view-only, dokter: CRUD)
- Level 4: Dashboard + Laporan (ringkasan total, tabel, filter)
- Level 5: Import JSON + Export Excel

## Cara Menjalankan (Dev Cepat)

> Secara default memakai SQLite agar langsung jalan. Untuk PostgreSQL, set `DATABASE_URL`.

```bash
cd patient_app
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Buka: http://127.0.0.1:8000/login

Akun demo:
- admin / admin123 (admin → hanya lihat)
- dokter / dokter123 (dokter → boleh tambah/edit/hapus)

## Pakai PostgreSQL (Sesuai Requirement)

Buat database, lalu export env:

**Windows (PowerShell):**
```powershell
$env:DATABASE_URL="postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/hospital_db"
$env:SECRET_KEY="ganti_dengan_kunci_rahasia"
uvicorn app.main:app --reload
```

**Linux/macOS:**
```bash
export DATABASE_URL="postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/hospital_db"
export SECRET_KEY="ganti_dengan_kunci_rahasia"
uvicorn app.main:app --reload
```

## Endpoint Utama

- `GET /login` – form login
- `POST /login` – submit kredensial, set cookie JWT
- `GET /logout` – hapus cookie
- `GET /dashboard` – halaman ringkasan + filter
- `GET /export.xlsx` – unduh Excel sesuai filter
- `POST /import` – import pasien (JSON list)
- `GET /patients` – daftar pasien
- `GET /patients/new` – form tambah (role: dokter)
- `POST /patients/new` – simpan pasien baru (role: dokter)
- `GET /patients/{id}/edit` – form edit (role: dokter)
- `POST /patients/{id}/edit` – update (role: dokter)
- `POST /patients/{id}/delete` – hapus (role: dokter)

## Catatan
- Untuk integrasi Auth0 beneran, gantikan mekanisme JWT lokal dengan verifikasi token Auth0 (Authlib) pada dependency `get_current_user`.
- Tailwind pakai CDN agar setup cepat sesuai kebutuhan tes.
