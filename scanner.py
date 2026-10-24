"""Logika scanner IDX Bagger Hunter (port dari Pine Script).

3 sinyal:
  S1 Setup Base   : tren sehat, base rapat, squeeze, dekat resistance, belum terlalu lari
  S2 Akumulasi    : volume naik > turun, OBV di atas rata-rata, likuid
  S3 Trigger      : breakout resistance base + volume + RS vs IHSG + candle kuat
"""
import re

import numpy as np
import pandas as pd

DEFAULT_PARAMS = dict(
    base_len=60,
    max_depth=35.0,
    near_pct=10.0,
    sqz_rank=35,
    max_run=100.0,
    need_sma200=False,
    mem_bars=10,
    ud_min=1.2,
    min_val_m=1000.0,
    vol_mult=1.5,
    rsi_lo=55,
    rsi_hi=78,
    chase_pct=7.0,
    sl_mult=2.5,
)


# ───────── Fraksi harga BEI ─────────
def tick_size(p: float) -> float:
    if p < 200:
        return 1.0
    if p < 500:
        return 2.0
    if p < 2000:
        return 5.0
    if p < 5000:
        return 10.0
    return 25.0


def round_tick(p: float) -> float:
    ts = tick_size(p)
    return float(np.floor(p / ts + 0.5) * ts)


# ───────── Parsing ticker ─────────
def parse_tickers(text: str) -> list[str]:
    tokens = re.split(r"[\s,;]+", text.upper())
    out, seen = [], set()
    for t in tokens:
        t = t.strip()
        if not t or t.startswith("^"):
            continue
        if "." not in t:
            t = t + ".JK"
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ───────── Util indikator ─────────
def _recent(s: pd.Series, n: int) -> pd.Series:
    """True jika s bernilai True dalam n bar terakhir (termasuk bar ini)."""
    return s.astype(float).rolling(n + 1, min_periods=1).max() > 0


def _percent_rank(x: np.ndarray) -> float:
    prev, cur = x[:-1], x[-1]
    if np.isnan(cur) or np.isnan(prev).any():
        return np.nan
    return float((prev <= cur).sum()) / len(prev) * 100.0


def compute(df: pd.DataFrame, ihsg: pd.Series | None, P: dict) -> pd.DataFrame:
    """Hitung semua indikator & sinyal per bar. df: kolom Open/High/Low/Close/Volume."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c

    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    prev = c.shift()
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()

    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100 - 100 / (1 + gain / loss)

    base_high = h.rolling(P["base_len"]).max().shift(1)
    base_low = l.rolling(P["base_len"]).min().shift(1)
    low52 = l.rolling(252).min()

    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    bbw = 4 * sd / mid
    bbw_rank = bbw.rolling(121).apply(_percent_rank, raw=True)

    vol_ma = v.rolling(20).mean()
    vol_ratio = (v / vol_ma).where(vol_ma > 0, 0.0)
    val_avg_m = (c * v).rolling(20).mean() / 1_000_000

    if ihsg is not None and len(ihsg) > 0:
        ih = ihsg.reindex(c.index).ffill()
        rs = c / ih
        rs_ema = rs.ewm(span=50, adjust=False).mean()
        rs_ok = (rs > rs_ema) & (rs > rs.shift(20))
    else:
        rs_ok = pd.Series(True, index=c.index)

    # ── Sinyal 1
    base_depth = (base_high - base_low) / base_high * 100
    trend_ok = (c > sma50) & (sma50 > sma50.shift(10))
    if P["need_sma200"]:
        trend_ok &= c > sma200
    depth_ok = base_depth <= P["max_depth"]
    squeeze_ok = bbw_rank <= P["sqz_rank"]
    near_high = c >= base_high * (1 - P["near_pct"] / 100)
    run_pct = (c / low52 - 1) * 100
    not_ext = run_pct <= P["max_run"]
    s1 = trend_ok & depth_ok & squeeze_ok & near_high & not_ext

    # ── Sinyal 2
    up_vol = v.where(c > prev, 0.0).rolling(20).sum()
    down_vol = v.where(c < prev, 0.0).rolling(20).sum()
    ud = (up_vol / down_vol).where(down_vol > 0, 10.0)
    obv = (np.sign(d).fillna(0.0) * v).cumsum()
    obv_ema = obv.ewm(span=20, adjust=False).mean()
    liq_ok = val_avg_m >= P["min_val_m"]
    s2 = (ud >= P["ud_min"]) & (obv > obv_ema) & (obv_ema > obv_ema.shift(5)) & liq_ok

    # ── Sinyal 3
    rng = (h - l).where(h > l)
    strong_close = ((c - l) / rng >= 0.6).fillna(False)
    not_chasing = c <= base_high * (1 + P["chase_pct"] / 100)
    brk = (c > base_high) & (prev <= base_high.shift())
    s3 = (
        brk
        & (vol_ratio >= P["vol_mult"])
        & strong_close
        & rs_ok
        & (rsi >= P["rsi_lo"])
        & (rsi <= P["rsi_hi"])
        & not_chasing
    )

    s1r = _recent(s1, P["mem_bars"])
    s2r = _recent(s2, P["mem_bars"])
    s3r = _recent(s3, 2)
    buy = s3 & s1r & s2r
    pre_buy = s1r & s2r & ~s3 & (c >= base_high * 0.95) & (c <= base_high)

    f["sma50"], f["sma200"] = sma50, sma200
    f["base_high"], f["base_low"] = base_high, base_low
    f["atr"], f["rsi"] = atr, rsi
    f["base_depth"], f["run_pct"], f["bbw_rank"] = base_depth, run_pct, bbw_rank
    f["ud"], f["vol_ratio"], f["val_avg_m"] = ud, vol_ratio, val_avg_m
    f["rs_ok"] = rs_ok
    f["s1"], f["s2"], f["s3"] = s1, s2, s3
    f["s1r"], f["s2r"], f["s3r"] = s1r, s2r, s3r
    f["buy"], f["pre_buy"] = buy, pre_buy
    f["score"] = s1r.astype(int) + s2r.astype(int) + s3r.astype(int)
    return f


def summarize(ticker: str, f: pd.DataFrame, P: dict) -> dict | None:
    """Ringkas bar terakhir menjadi satu baris hasil scan."""
    r = f.iloc[-1]
    if pd.isna(r["base_high"]) or pd.isna(r["atr"]):
        return None

    close = float(r["close"])
    bh, bl = float(r["base_high"]), float(r["base_low"])
    sl = round_tick(min(max(bl, close - P["sl_mult"] * float(r["atr"])), close - tick_size(close)))
    t1 = round_tick(bh + (bh - bl))
    rr = (t1 - close) / (close - sl) if close > sl else 0.0

    if r["buy"]:
        status = "BUY (3 sinyal)"
    elif r["pre_buy"]:
        status = "SIAP - tunggu breakout"
    elif r["s1r"] and r["s2r"]:
        status = "Watchlist (S1+S2)"
    elif r["s3r"] and not (r["s1r"] and r["s2r"]):
        status = "Breakout tanpa setup"
    elif r["s1r"] or r["s2r"]:
        status = "Pantau"
    else:
        status = "-"

    return {
        "Kode": ticker.replace(".JK", ""),
        "Status": status,
        "Skor": int(r["score"]),
        "S1": "✔" if r["s1r"] else "✘",
        "S2": "✔" if r["s2r"] else "✘",
        "S3": "✔" if r["s3r"] else "✘",
        "Harga": round(close),
        "Trigger (resist.)": round_tick(bh),
        "Jarak ke trigger %": round((bh / close - 1) * 100, 1),
        "Base depth %": round(float(r["base_depth"]), 1),
        "Vol naik/turun": round(float(r["ud"]), 2),
        "Vol x": round(float(r["vol_ratio"]), 2),
        "RSI": round(float(r["rsi"]), 1),
        "RS vs IHSG": "Kuat" if r["rs_ok"] else "Lemah",
        "Naik dari low 52w %": round(float(r["run_pct"]), 0),
        "Stop saran": sl,
        "Target T1": t1,
        "Potensi T1 %": round((t1 / close - 1) * 100, 1),
        "R:R": round(rr, 1),
        "Nilai trx (jt Rp)": round(float(r["val_avg_m"]), 0),
    }
