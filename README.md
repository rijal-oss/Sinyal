# 📈 IDX Bagger Hunter (Sinyal)

Aplikasi web untuk memindai saham IDX yang berpotensi **half bagger (+50%)** atau **bagger (+100%)** dengan gaya **swing trading**, memakai 3 sinyal berurutan.

Data harian diambil dari Yahoo Finance (kode saham berakhiran `.JK`). Dibangun dengan Python dan Streamlit.

> ⚠️ **Disclaimer:** Hanya untuk edukasi dan riset, bukan rekomendasi jual/beli. Hasil scan adalah kandidat, bukan jaminan. Keputusan investasi sepenuhnya tanggung jawab pengguna.

## 3 Sinyal Persiapan Buy

1. **Setup Base** – tren sehat (di atas SMA50 yang naik), konsolidasi rapat, volatilitas menyempit (Bollinger squeeze), harga dekat resistance, dan belum naik terlalu jauh dari low 52 minggu.
2. **Akumulasi** – volume hari naik lebih besar daripada hari turun, OBV di atas rata-ratanya, dan nilai transaksi cukup likuid.
3. **Trigger Breakout** – harga menembus resistance base dengan volume besar, candle ditutup kuat, relative strength lebih baik dari IHSG, RSI sehat, dan tidak mengejar harga terlalu jauh.

**Status hasil scan:**

| Status | Arti |
|---|---|
| BUY (3 sinyal) | Sinyal 3 muncul saat sinyal 1 & 2 masih aktif |
| SIAP - tunggu breakout | Sinyal 1 & 2 aktif, harga tinggal menunggu tembus resistance |
| Watchlist (S1+S2) | Setup dan akumulasi aktif, harga masih agak jauh dari resistance |
| Pantau | Baru satu sinyal aktif |

## Fitur

- Pindai puluhan hingga ratusan saham sekaligus
- Daftar saham bisa diketik manual atau diunggah (`.csv` dengan kolom `Kode`, atau `.txt`)
- Semua parameter sinyal bisa diubah dari sidebar
- Tabel hasil dengan trigger, stop saran, target T1, R:R, dan nilai transaksi
- Grafik candlestick dengan SMA50, SMA200, resistance dan support base
- Unduh hasil dalam bentuk CSV
- Data di-cache 1 jam agar scan ulang lebih cepat

## Struktur File

| File | Fungsi |
|---|---|
| `app.py` | Tampilan web (Streamlit) |
| `scanner.py` | Logika perhitungan 3 sinyal |
| `requirements.txt` | Daftar pustaka Python yang dibutuhkan |

## Menjalankan di Komputer

```bash
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi terbuka di `http://localhost:8501`.

## Deploy Gratis (Streamlit Community Cloud)

1. Buka [share.streamlit.io](https://share.streamlit.io) dan masuk dengan GitHub.
2. Pilih **Create app**, lalu pilih repositori ini.
3. Isi **Branch** `main` dan **Main file path** `app.py`.
4. Tekan **Deploy**.

## Catatan

- Data Yahoo Finance untuk saham IDX kadang terlambat atau kurang lengkap, terutama saham kecil. Cek ulang di aplikasi sekuritas sebelum bertindak.
- Yahoo dapat membatasi permintaan. Jika data gagal diambil, tunggu beberapa menit dan kecilkan ukuran batch di sidebar.
- Untuk memindai seluruh emiten, unggah daftar kode saham dari situs BEI.
- Tetap cek fundamental, UMA, dan suspensi sebelum membeli.
