# Edge Discovery Pipeline — Spesifikasi Project Lengkap

## Prinsip Utama
1. **MQL5 adalah source of truth.** Semua indicator value dihitung dan dihasilkan oleh MQL5, bukan direplikasi di Python. Python murni konsumen data.
2. **Tidak ada lookahead.** Setiap kondisi hanya boleh memakai informasi yang benar-benar sudah "diketahui" pada bar itu (`known_at_bar`), termasuk indicator yang punya shift visual atau butuh konfirmasi.
3. **Tidak ada fixed lookahead.** Python menghitung probabilitas arah market di SEMUA horizon (1..max_horizon), lalu menemukan sendiri horizon mana yang punya edge signifikan.
4. **Overfitting dicegah lewat proses, bukan sumber data.** Multiple-testing correction, walk-forward validation, dan holdout wajib di semua tahap eksplorasi.
5. **Kondisi harus sederhana & boolean-mappable.** Supaya 1:1 diterjemahkan ke `if()` MQL5, tidak ada black-box ML.

---

## Daftar Indicator — Tier 1 (Scope Awal, Aman Dipakai)

| Indicator | MQL5 Function | Kategori | Parameter Varian yang Disarankan |
|---|---|---|---|
| Moving Average | `iMA` | Immediate | period: 5,10,20,50,100,200; mode: SMA,EMA,SMMA,LWMA |
| Double EMA | `iDEMA` | Immediate | period: 10,20,50 |
| Triple EMA | `iTEMA` | Immediate | period: 10,20,50 |
| Fractal Adaptive MA | `iFrAMA` | Immediate | period: 14,20 |
| Adaptive MA (Kaufman) | `iAMA` | Immediate | period: 10; fast:2; slow:30 |
| Variable Index Dynamic Avg | `iVIDyA` | Immediate | period: 9,12 |
| Parabolic SAR | `iSAR` | Sequential-dependent | step:0.02; max:0.2 (+ varian step 0.01/0.03) |
| RSI | `iRSI` | Immediate | period: 7,14,21 |
| Stochastic Oscillator | `iStochastic` | Immediate | %K:5,%D:3,slowing:3 (+ varian 14/3/3) |
| CCI | `iCCI` | Immediate | period: 14,20 |
| Williams %R | `iWPR` | Immediate | period: 14 |
| Momentum | `iMomentum` | Immediate | period: 10,14 |
| MACD | `iMACD` | Immediate | 12/26/9 (standar) |
| MACD Histogram (OsMA) | `iOsMA` | Immediate | 12/26/9 |
| DeMarker | `iDeMarker` | Immediate | period: 14 |
| Relative Vigor Index | `iRVI` | Immediate | period: 10 |
| TriX | `iTriX` | Immediate | period: 14 |
| Accelerator Oscillator | `iAC` | Immediate | (tanpa parameter) |
| Awesome Oscillator | `iAO` | Immediate | (tanpa parameter) |
| Bears Power | `iBearsPower` | Immediate | period: 13 |
| Bulls Power | `iBullsPower` | Immediate | period: 13 |
| ATR | `iATR` | Immediate | period: 14,20 |
| Bollinger Bands | `iBands` | Immediate | period:20, dev:2.0 (+varian dev 1.5/2.5) |
| Standard Deviation | `iStdDev` | Immediate | period: 20 |
| Envelopes | `iEnvelopes` | Immediate | period:20, deviation:0.1% |
| ADX | `iADX` | Immediate | period: 14 |
| ADX Wilder | `iADXWilder` | Immediate | period: 14 |
| On Balance Volume | `iOBV` | Immediate (volume) | (tanpa parameter) |
| Accumulation/Distribution | `iAD` | Immediate (volume) | (tanpa parameter) |
| Money Flow Index | `iMFI` | Immediate (volume) | period: 14 |
| Force Index | `iForce` | Immediate (volume) | period: 13 |
| Chaikin Oscillator | `iChaikin` | Immediate (volume) | fast:3, slow:10 |
| Volumes (tick volume) | `iVolumes` | Immediate (volume) | (tanpa parameter) |

**Total Tier 1: 32 indicator** (termasuk varian parameter, jadi ratusan kolom fitur).

## Daftar Indicator — Tier 2 (Ditunda, Butuh Treatment Khusus)

| Indicator | Alasan Ditunda |
|---|---|
| `iIchimoku` | Shift visual 26 bar (Senkou), butuh realignment eksplisit |
| `iAlligator` | Shift visual 3/5/8 bar |
| `iGator` | Turunan Alligator, warisi masalah sama |
| `iFractals` | Butuh 2-bar confirmation delay |
| `iBWMFI` | Butuh interpretasi 4-kondisi kualitatif tambahan |

Revisit Tier 2 hanya setelah Tier 1 menghasilkan kandidat edge yang solid dan tervalidasi.

---

## FASE 0 — MQL5 Data Exporter (Ground Truth Generator)

**Tujuan:** satu script MQL5 (bukan EA trading) yang jalan di Strategy Tester, loop seluruh histori, hitung semua indicator Tier 1, dan tulis ke CSV.

### Spesifikasi Teknis
- **Testing model:** "Open prices only" — cukup untuk ambil value indicator per-bar, jauh lebih cepat dari "Every tick".
- **Batching indicator handle:** pecah jadi grup (misal: grup Trend/MA, grup Oscillator, grup Volatility, grup Volume) untuk hindari exceed limit handle MT5. Panggil `IndicatorRelease()` setelah tiap grup selesai dipakai sebelum lanjut ke grup berikutnya.
- **Evaluasi selalu di bar closed** — pakai index bar `[1]` terhadap bar berjalan, bukan `[0]`.
- **Streaming write** — tulis CSV baris per baris (append), jangan kumpulkan array besar di memori EA dulu.
- **Jalankan per symbol + per timeframe** — hasil disimpan permanen, tidak diulang tiap sesi riset.

### Skema Kolom CSV
```
time, open, high, low, close, tick_volume,
ma_20_sma, ma_50_sma, ma_20_ema, ..., 
rsi_14, rsi_7, ...
stoch_k_5_3_3, stoch_d_5_3_3, ...
atr_14, bb_upper_20_2, bb_lower_20_2, bb_mid_20_2, ...
adx_14, adx_wilder_14, ...
obv, ad, mfi_14, force_13, chaikin_3_10, volume, ...
sar_002_02, ...
```
Semua kolom immediate/sequential-dependent bisa ditulis apa adanya (`known_at_bar = t`). Tidak ada kolom Tier 2 di fase ini.

### Sanity Check
Setelah export, cek jumlah baris = jumlah bar historis (tidak ada bar hilang), cek tidak ada NaN berlebihan di awal data (warm-up period indicator wajar NaN di beberapa bar pertama, itu normal).

---

## FASE 1 — Python: Ingestion & Layer 1 Cache (Indicator Value Layer)

**Tujuan RAM optimization di titik ini:**
- Load CSV sekali, convert semua kolom numerik ke `float32` (bukan `float64` default pandas) — hemat ~50% RAM.
- Kolom `time` disimpan sebagai `int64` (unix timestamp) atau `datetime64[ns]` yang di-set sebagai index, bukan string.
- Simpan hasil sebagai **Parquet** dengan kompresi (`snappy` atau `zstd`), partitioned per symbol+timeframe — bukan CSV untuk dipakai ulang, karena parquet jauh lebih cepat dibaca dan lebih kecil di disk.
- **Ini dihitung/dikonversi sekali.** Semua fase berikutnya hanya membaca dari parquet ini, tidak mengulang parsing CSV.

```
storage/
  EURUSD_H1.parquet
  EURUSD_M15.parquet
  GBPUSD_H1.parquet
```

---

## FASE 2 — Tagging Known-At (Delay Layer)

Untuk seluruh Tier 1, hampir semua `known_at_bar = t` (langsung dipakai). Kolom `sar_*` tetap `known_at_bar = t` karena walau sequential-dependent, valuenya tetap murni dari data hingga bar `t`.

Simpan mapping ini sebagai file konfigurasi kecil (dict/YAML), bukan hardcode di logika — supaya kalau nanti Tier 2 ditambahkan, tinggal update mapping ini tanpa ubah kode inti:

```yaml
known_at_delay:
  default: 0
  # contoh kalau nanti ada Tier 2:
  # fractal_up: 2
  # fractal_down: 2
```

---

## FASE 3 — Condition Layer (Generate Kandidat Kondisi)

1. **Kondisi atomik**: perbandingan sederhana per indicator, misal `rsi_14 < 30`, `close < bb_lower_20_2`, `ma_20_ema > ma_50_ema` (crossover state).
2. **Kondisi kombinasi**: AND antar 2-3 kondisi atomik dari indicator berbeda (hindari kombinasi dari indicator yang sangat korelatif, misal RSI_7 AND RSI_14, karena itu bukan diversifikasi sinyal asli).
3. **RAM optimization:** kondisi disimpan sebagai **boolean mask** (`numpy bool_` array, 1 byte per elemen) atau **bit-packed** (`numpy.packbits`, 1 bit per elemen) kalau jumlah kondisi kandidat sangat besar. Tidak disimpan sebagai kolom permanen di parquet — dihitung on-the-fly dari Layer 1 saat dibutuhkan, karena murah untuk dihitung ulang (elementwise comparison).
4. Kondisi diproses per-batch (misal per grup indicator), bukan generate semua ribuan kombinasi sekaligus dalam satu list di memori.

---

## FASE 4 — Frequency Pre-Filter (Murah, Sebelum Proses Berat)

Untuk tiap kondisi kandidat, hitung:
- `n_occurrence` = total kejadian kondisi True.
- `freq_per_year` = occurrence dibagi rentang tahun data.

Filter:
```python
MIN_OCCURRENCE = 200        # sesuaikan dgn panjang data
MIN_FREQ_PER_YEAR = 30      # minimal signal ~30x/tahun biar actionable
```

Kondisi yang tidak lolos dibuang di sini — **sebelum** masuk ke forward probability profiling yang jauh lebih mahal secara komputasi. Ini titik penghematan RAM & waktu terbesar dalam keseluruhan pipeline.

---

## FASE 5 — Forward Probability Profiling (Inti Riset)

### Konsep RAM Control
Struktur paling besar dalam seluruh pipeline adalah **forward return matrix**: `n_bars × max_horizon`. Ini dihitung **sekali** untuk seluruh dataset (bukan per kondisi), lalu dipakai ulang oleh semua kondisi.

```python
MAX_HORIZON = 100   # hard ceiling, sesuaikan RAM tersedia

# forward_direction[i, h] = True jika close[i+h] > close[i]
# dtype bool -> 1 byte, untuk 500,000 bar x 100 horizon = 50 MB saja
```

Estimasi RAM: `n_bars × max_horizon × 1 byte` (dtype bool). Untuk data H1 10 tahun (~87,600 bar) dengan `max_horizon=100`: ±8.7 MB. Sangat terkendali. Kalau mau multi-timeframe/multi-symbol sekaligus, proses **satu file per waktu**, flush hasil ke disk, baru lanjut file berikutnya — jangan load semua symbol ke RAM bersamaan.

### Entry Point yang Benar (Anti-Lookahead)
Entry dianggap terjadi di **open bar berikutnya** setelah kondisi sah (bar `t+1` open), bukan di close bar sinyal (bar `t`). Forward return dihitung dari titik entry ini, bukan dari `close[t]`.

### Perhitungan per Kondisi
Untuk tiap kondisi yang lolos Fase 4:
```python
idx_true = np.where(condition_mask)[0]
idx_true = idx_true[idx_true < n - MAX_HORIZON]  # buang yg mepet ujung data

for h in range(1, MAX_HORIZON + 1):
    entry_price = open_[idx_true + 1]          # open bar berikutnya
    future_price = close[idx_true + 1 + h]
    is_bull = future_price > entry_price
    prob = is_bull.mean()
    n = len(idx_true)
    ci_low, ci_high = wilson_ci(is_bull.sum(), n)
```
Output disimpan sebagai satu baris ringkas per (kondisi, horizon) — bukan array mentah disimpan permanen. Setelah probabilitas dihitung, array intermediate bisa langsung dibuang (`del`, garbage collect) sebelum lanjut kondisi berikutnya.

---

## FASE 6 — Uji Statistik & Koreksi Multiple-Testing

1. **Baseline**: hitung `P(bull)` unconditional di tiap horizon yang sama (dari seluruh dataset, tanpa kondisi) sebagai pembanding.
2. **Z-test proporsi** tiap horizon vs baseline.
3. **Koreksi Benjamini-Hochberg (FDR)** — karena satu kondisi diuji di banyak horizon sekaligus (hingga 100 uji), dan banyak kondisi diuji sekaligus (bisa ratusan kandidat). Koreksi harus diterapkan di **kedua level** ini, bukan cuma satu.
4. Simpan hanya horizon yang lolos `p_adj < alpha` sebagai kandidat signifikan.

---

## FASE 7 — Robustness & Validation

| Uji | Tujuan |
|---|---|
| **Walk-forward** (rolling window train/test) | Cek edge stabil dari waktu ke waktu, bukan cuma di satu window |
| **Regime breakdown** (trending/ranging/high-vol/low-vol) | Cek edge tidak cuma jalan di 1 jenis kondisi market |
| **Parameter sensitivity** (geser threshold/period ±10-20%) | Kalau edge hilang drastis, tanda overfit ke angka spesifik |
| **Cost model** (spread + slippage realistis) | Cek expectancy tetap positif net biaya |
| **Final holdout** (data belum pernah disentuh sepanjang Fase 3-7) | Konfirmasi akhir, sekali pakai saja |

---

## FASE 8 — Edge Report (Output Akhir, Format Terstruktur)

Format YAML/JSON per kandidat edge yang lolos semua fase:

```yaml
edge_id: rsi14_below30_bb_lower_v1
hypothesis: "RSI(14)<30 AND Close<BB_lower(20,2) cenderung reversal bullish"
entry_condition:
  - indicator: rsi_14
    operator: "<"
    value: 30
  - indicator: bb_lower_20_2
    operator: "close_below"
frequency:
  n_occurrence: 2150
  freq_per_year: 65.3
optimal_horizon: 4
statistics:
  horizon_4:
    prob_bull: 0.596
    ci_95: [0.575, 0.617]
    baseline_prob: 0.503
    p_adj: 0.0008
robustness:
  walk_forward_stability: "consistent 4/5 window"
  regime_breakdown:
    trending: {prob_bull: 0.61, n: 1100}
    ranging: {prob_bull: 0.58, n: 1050}
  parameter_sensitivity: "stable pada period 12-16"
  cost_adjusted_expectancy_R: 0.28
validated_period: "2015-01 to 2023-12"
holdout_result:
  prob_bull: 0.583
  n: 210
mql5_mapping:
  entry: "rsi[1] < 30 && close[1] < bb_lower[1]"
  exit_type: fixed_bar
  exit_bars: 4
  magic_number: null   # diisi manual saat generate EA
```

---

## FASE 9 — MQL5 Code Generation

1. Parser baca `edge_report.yaml` → isi template `.mq5` sesuai pola existing (virtual SL/TP, magic number independen, CSV logging).
2. Exit logic default: fixed bar count dari `optimal_horizon`, bisa dikombinasi dengan TP/SL virtual dari distribusi return di horizon tersebut.
3. **Sanity check wajib**: jalankan EA hasil generate di Strategy Tester pada periode sama, bandingkan jumlah trade & win rate kasar dengan angka di edge report. Kalau meleset jauh → ada bug konversi.

---

## Struktur Folder Final

```
edge_research/
├── mql5_exporter/
│   └── DataExporter.mq5          # Fase 0
├── data/
│   ├── raw_csv/                  # output exporter
│   └── storage/                  # Fase 1: parquet, float32
├── config/
│   └── known_at_delay.yaml       # Fase 2
├── conditions/
│   ├── condition_library.py      # Fase 3
│   └── frequency_filter.py       # Fase 4
├── forward_profile/
│   ├── engine.py                 # Fase 5
│   └── significance.py           # Fase 6
├── validation/
│   ├── walk_forward.py
│   ├── regime_stress_test.py
│   ├── parameter_sensitivity.py
│   └── cost_model.py             # Fase 7
├── reporting/
│   ├── edge_report_schema.py
│   └── report_generator.py       # Fase 8
└── mql5_codegen/
    ├── templates/
    └── generator.py              # Fase 9
```

---

## Ringkasan RAM Budget

| Layer | Struktur | Ukuran (perkiraan, 10 tahun data H1) |
|---|---|---|
| Layer 1 — Indicator cache | parquet, float32, semua kolom | Puluhan-ratusan MB di disk, dibaca sebagian saat dibutuhkan |
| Layer 2 — Condition mask | bool array per kondisi, on-the-fly | ~87 KB per kondisi (87,600 bar × 1 byte) |
| Layer 3 — Forward return matrix | bool, dihitung sekali dipakai ulang | ~8.7 MB (`n_bars × max_horizon`) |

Titik kontrol RAM paling penting: **`MAX_HORIZON`** (hard ceiling Layer 3) dan **proses batch per symbol/timeframe** (tidak load semua sekaligus ke memori).