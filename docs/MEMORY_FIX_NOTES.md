# Memory / freeze fix notes (M1 walk-forward)

## Cara menjalankan (perintah sama, dua opsi baru)

    python scripts/run_walkforward_pipeline.py data/raw_csv/XAUUSD_M1_export_20100101.csv \
      --symbol XAUUSD --timeframe M1 --config-dir config/WALKFORWARD/XAUUSD/M1 \
      --output-dir output_walkforward --max-rss-gb 40 --min-free-gb 3

- `--min-free-gb` (default 2.0): berhenti bersih (exit code 3) kalau RAM sistem yang tersedia
  turun di bawah nilai ini, SEBELUM PC mulai swap/freeze.
- `--max-rss-gb` (default off): berhenti bersih kalau proses ini melewati batas itu.
- Log `[MEM] ...` di awal/akhir tiap window: kalau `rss` di "window end" naik terus dari window ke
  window, itu kebocoran antar-window; kalau stabil, footprint per-window memang besar.

## Yang diperbaiki

1. loader.py - puncak RAM saat load ~3.2x ukuran tabel akhir (terukur) -> ~1.4x.
   File dibaca per-chunk dan langsung float32 (dulu: seluruh file float64 + loop
   `df[col] = astype(float32)` + `df.isna()` full-size + `to_parquet` menyalin lagi).
2. loader.py - fallback QUOTE_NONE versi sebelumnya membuat kolom yang kena tanda kutip jadi
   `object` (jutaan string Python), bukan NaN seperti yang dijanjikan. Sekarang `"` dibuang per sel
   dan kolom tetap float32.
3. loader.py - scan byte cepat: kalau file mengandung `"`, parser C default (yang butuh 43 menit
   dan ~16GB lalu gagal di log kamu) dilewati.
4. loader.py - timestamp duplikat: dulu SELURUH index diganti `date_range(freq="D")` (menghancurkan
   semua timestamp, dan untuk jutaan baris melewati batas tanggal). Sekarang baris duplikat dibuang
   (yang terakhir dipertahankan).
5. run_pipeline.py - semua mask kandidat (1 MB/kandidat di M1) ditahan 7 container sampai akhir
   fungsi, termasuk yang gagal signifikansi. Sekarang dilepas sebelum Phase 7; mask edge yang
   tidak lolos gate dibuang setelah Phase 7e.
6. run_walkforward_pipeline.py - `release_memory()` (gc + malloc_trim) tiap window supaya RSS tidak
   naik terus karena fragmentasi heap.
7. trade_simulator.py - `scan_holding_horizons` menjalankan loop Python murni (dengan objek
   Timestamp per trigger) 720 x n_trigger per kondisi. Sekarang vektorisasi; hasil identik
   bit-per-bit dengan loop lama (test_vectorized_r_multiples.py).
8. condition_library.py - korelasi kolom (dropna+corr atas ~1 jt baris) dihitung ulang untuk
   setiap kombinasi; sekarang di-cache per pasangan kolom.

## Verifikasi
- 99 test lolos (termasuk smoke test end-to-end run_pipeline_core pada data sintetis).
- Regresi: `STRATEGY_GATE_RESULTS.csv` kode lama vs baru pada data sintetis yang sama
  (spread ATR + session multiplier aktif) identik seluruh kolomnya.
- Belum diuji pada CSV M1 asli kamu (tidak dijalankan di sini).
