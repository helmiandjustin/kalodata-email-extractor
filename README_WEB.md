# Web UI ringan

Jalankan dari folder ini:

```powershell
python web_app.py
```

Buka `http://127.0.0.1:8010`, masukkan API key Chocodata harian, lalu paste username TikTok.
API key tidak disimpan ke file dan tidak dikirim ke browser selain saat submit ke server lokal.

## Deploy dari GitHub

Repository ini sudah memiliki `render.yaml`. Di Render pilih **New → Blueprint**, hubungkan repository GitHub ini, lalu deploy service `kalodata-email-finder`. Render akan mengisi `HOST`/`PORT` untuk web service secara otomatis.
