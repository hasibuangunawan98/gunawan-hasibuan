# Polymarket BTC Microtrend Bot

Bot untuk memindai pasar Polymarket terkait Bitcoin dengan data **real-time** dari Binance.

---

## 🚀 Fitur Utama

- **Data Real-Time**: Order book dan trades dari Binance WebSocket
- **Sinyal Mikrotrend**: Analisis 5m dan 15m untuk BTC
- **Dashboard Interaktif**: Tampilan modern dengan Chart.js
- **Black-Swan Filter**: Filter risiko untuk menghindari volatilitas ekstrem
- **Paper-Trading Ready**: Siap untuk simulasi trading

---

## 📦 Instalasi

### 1. Install Python

Pastikan Python 3.8+ sudah terinstall. Download dari [python.org](https://www.python.org/downloads/).

### 2. Install Dependencies

```bash
python -m pip install websocket-client
```

---

## 🎯 Cara Menjalankan

### **Opsi 1: Menggunakan Script Batch (Windows)**

1. **Jalankan Bot Lengkap** (WebSocket + Signal Bot):
   ```
   Klik dua kali: run-bot.bat
   ```

2. **Refresh Dashboard Saja**:
   ```
   Klik dua kali: refresh-dashboard.bat
   ```

### **Opsi 2: Menggunakan Terminal**

1. **Terminal 1** - Jalankan WebSocket Bridge:
   ```bash
   python scripts/btc_ws_bridge.py
   ```

2. **Terminal 2** - Jalankan Signal Bot:
   ```bash
   python scripts/btc_bot.py scan-btc
   ```

   Atau untuk mode otomatis dengan dashboard:
   ```bash
   python scripts/btc_bot.py auto-btc
   ```

3. **Buka Dashboard**:
   - Buka file `data/dashboard.html` di browser
   - Dashboard akan auto-refresh setiap 10 detik

---

## 📊 Struktur Data

| File | Deskripsi |
|------|-----------|
| `data/live-feed.json` | State real-time lengkap (harga, order book, trades) |
| `data/order_book.json` | Snapshot order book untuk dashboard |
| `data/trades.jsonl` | Log historis trades (format JSONL) |
| `data/dashboard.html` | Dashboard interaktif |
| `data/summary.json` | Ringkasan analisis sinyal |
| `data/signals.jsonl` | Log historis sinyal |

---

## 🖥️ Tampilan Dashboard

Dashboard menampilkan:

1. **Order Book Real-Time**: 10 level bid/ask teratas
2. **Grafik Harga BTC**: Chart interaktif dengan Chart.js
3. **Recent Trades**: 10 trades terakhir
4. **Sinyal Mikrotrend**: Daftar sinyal dengan bias, confidence, dan action
5. **Risk Metrics**: Market regime, black-swan filter, valid markets

---

## ⚙️ Konfigurasi

### Mengubah Interval Refresh

Edit di `assets/dashboard.html`:
```javascript
// Auto-refresh setiap 10 detik
setInterval(() => {
  window.location.reload();
}, 10000);  // Ganti angka ini (dalam milidetik)
```

### Mengubah Depth Order Book

Edit di `scripts/btc_ws_bridge.py`:
```python
DEPTH_LEVELS = 15  // Ganti angka ini untuk jumlah level
```

---

## 🛠️ Troubleshooting

### Error: "Missing dependency: websocket-client"
```bash
python -m pip install websocket-client
```

### Dashboard Tidak Menampilkan Data Real-Time
1. Pastikan `btc_ws_bridge.py` sedang berjalan
2. Periksa file `data/order_book.json` dan `data/trades.jsonl` ada
3. Refresh halaman dashboard (F5)

### WebSocket Tidak Terhubung
- Periksa koneksi internet
- Pastikan firewall tidak memblokir koneksi WebSocket
- Coba restart `btc_ws_bridge.py`

---

## 📝 Mode Bot

### `scan-btc`
- Scan pasar Polymarket untuk BTC
- Hasilkan sinyal tanpa menjalankan dashboard

### `auto-btc`
- Scan pasar + generate dashboard
- Mode lengkap untuk trading

---

## 🔒 Keamanan

- **Jangan bagikan** file `TOOLS.md` yang berisi token GitHub
- **Simpan dengan aman** Personal Access Token (PAT)
- Bot ini hanya untuk **tujuan edukasi** dan **paper-trading**

---

## 📄 Lisensi

Lihat file `LICENSE` di root repository.

---

## 🤝 Kontribusi

Lihat `CONTRIBUTING.md` untuk panduan kontribusi.

---

**Happy Trading! 🚀**
