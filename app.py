import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from scanner import DEFAULT_PARAMS, compute, parse_tickers, summarize

st.set_page_config(page_title="IDX Bagger Hunter", page_icon="📈", layout="wide")

DEFAULT_TICKERS = """
BBCA BBRI BMRI BBNI BRIS ARTO BTPS BNGA TLKM EXCL ISAT TOWR TBIG MTEL
ASII AUTO UNVR ICBP INDF MYOR CPIN JPFA SIDO KLBF MIKA HEAL SILO
AMRT ACES MAPI ERAA LPPF ADRO PTBA ITMG HRUM MEDC PGAS AKRA ESSA
ANTM INCO MDKA TINS BRPT TPIA SMGR INTP JSMR PTPP WIKA
CTRA BSDE PWON SMRA ASRI GOTO BUKA EMTK SCMA
"""

# ───────── Data ─────────
def split_batch(data: pd.DataFrame, tickers: list[str]) -> dict:
    out = {}
    if data is None or data.empty:
        return out
    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(data.columns.get_level_values(0))
        for t in tickers:
            if t in level0:
                df = data[t].dropna(how="all")
                if not df.empty:
                    out[t] = df
    else:
        out[tickers[0]] = data.dropna(how="all")
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_batch(tickers: tuple, period: str) -> dict:
    data = yf.download(
        list(tickers), period=period, interval="1d",
        group_by="ticker", auto_adjust=True, threads=True, progress=False,
    )
    return split_batch(data, list(tickers))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ihsg(period: str):
    df = yf.download("^JKSE", period=period, interval="1d", auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def read_upload(file) -> str:
    raw = file.read().decode("utf-8", errors="ignore")
    if file.name.lower().endswith(".csv"):
        try:
            tbl = pd.read_csv(io.StringIO(raw))
            for col in tbl.columns:
                if str(col).strip().lower() in ("kode", "code", "ticker", "symbol"):
                    return " ".join(tbl[col].astype(str))
        except Exception:
            pass
    return raw


# ───────── Sidebar ─────────
st.sidebar.header("⚙️ Parameter")
P = dict(DEFAULT_PARAMS)
with st.sidebar.expander("Sinyal 1 - Setup Base", expanded=False):
    P["base_len"] = st.number_input("Panjang base (bar)", 20, 250, P["base_len"])
    P["max_depth"] = st.number_input("Maks kedalaman base %", 5.0, 80.0, P["max_depth"])
    P["near_pct"] = st.number_input("Maks jarak ke resistance %", 1.0, 30.0, P["near_pct"])
    P["sqz_rank"] = st.number_input("Squeeze: persentil BBW maks", 5, 100, P["sqz_rank"])
    P["max_run"] = st.number_input("Maks naik dari low 52w %", 10.0, 500.0, P["max_run"])
    P["need_sma200"] = st.checkbox("Wajib di atas SMA200", P["need_sma200"])
    P["mem_bars"] = st.number_input("Memori sinyal 1 & 2 (bar)", 1, 30, P["mem_bars"])
with st.sidebar.expander("Sinyal 2 - Akumulasi", expanded=False):
    P["ud_min"] = st.number_input("Rasio vol naik/turun min", 1.0, 3.0, P["ud_min"], step=0.1)
    P["min_val_m"] = st.number_input("Min nilai transaksi/hari (juta Rp)", 0.0, 100000.0, P["min_val_m"])
with st.sidebar.expander("Sinyal 3 - Trigger", expanded=False):
    P["vol_mult"] = st.number_input("Volume breakout min (x)", 1.0, 5.0, P["vol_mult"], step=0.1)
    P["rsi_lo"] = st.number_input("RSI minimum", 30, 80, P["rsi_lo"])
    P["rsi_hi"] = st.number_input("RSI maksimum", 50, 95, P["rsi_hi"])
    P["chase_pct"] = st.number_input("Maks di atas resistance %", 1.0, 20.0, P["chase_pct"])
with st.sidebar.expander("Risk", expanded=False):
    P["sl_mult"] = st.number_input("Stop awal (x ATR)", 0.5, 6.0, P["sl_mult"], step=0.5)

period = st.sidebar.selectbox("Rentang data", ["2y", "3y", "5y"], index=0)
batch_size = st.sidebar.slider("Ukuran batch unduh", 10, 60, 40)

# ───────── Halaman utama ─────────
st.title("📈 IDX Bagger Hunter")
st.caption(
    "Scanner swing untuk kandidat half bagger (+50%) / bagger (+100%) dengan 3 sinyal: "
    "Setup Base → Akumulasi → Trigger Breakout. Data harian Yahoo Finance (kode .JK). "
    "Bukan rekomendasi investasi."
)

col_a, col_b = st.columns([3, 2])
with col_a:
    txt = st.text_area("Daftar kode saham (pisahkan spasi/koma/baris)", DEFAULT_TICKERS.strip(), height=140)
with col_b:
    up = st.file_uploader("Atau unggah daftar saham (.csv kolom 'Kode' / .txt)", type=["csv", "txt"])
    min_score = st.slider("Tampilkan skor minimal", 0, 3, 1)
    only_status = st.multiselect(
        "Filter status",
        ["BUY (3 sinyal)", "SIAP - tunggu breakout", "Watchlist (S1+S2)", "Breakout tanpa setup", "Pantau"],
        default=[],
    )

if st.button("🔍 Scan sekarang", type="primary"):
    tickers = parse_tickers(read_upload(up) if up else txt)
    if not tickers:
        st.warning("Daftar saham kosong.")
        st.stop()

    ihsg = fetch_ihsg(period)
    if ihsg is None:
        st.warning("Data IHSG (^JKSE) gagal diambil — filter Relative Strength dinonaktifkan.")

    rows, frames, failed = [], {}, []
    bar = st.progress(0.0, text="Mengunduh data...")
    batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
    for i, b in enumerate(batches):
        try:
            data = fetch_batch(tuple(b), period)
        except Exception as e:  # noqa: BLE001
            data, _ = {}, e
        for t in b:
            df = data.get(t)
            if df is None or len(df) < 260:
                failed.append(t.replace(".JK", ""))
                continue
            try:
                f = compute(df, ihsg, P)
                row = summarize(t, f, P)
            except Exception:  # noqa: BLE001
                failed.append(t.replace(".JK", ""))
                continue
            if row:
                rows.append(row)
                frames[t.replace(".JK", "")] = (df, f)
        bar.progress((i + 1) / len(batches), text=f"Memproses batch {i + 1}/{len(batches)}")
    bar.empty()

    st.session_state["rows"] = rows
    st.session_state["frames"] = frames
    st.session_state["failed"] = failed

# ───────── Hasil ─────────
if "rows" in st.session_state:
    rows = st.session_state["rows"]
    res = pd.DataFrame(rows)
    if res.empty:
        st.info("Tidak ada data yang bisa dianalisis. Cek kode saham atau koneksi.")
    else:
        res = res[res["Skor"] >= min_score]
        if only_status:
            res = res[res["Status"].isin(only_status)]
        order = {"BUY (3 sinyal)": 0, "SIAP - tunggu breakout": 1, "Watchlist (S1+S2)": 2,
                 "Breakout tanpa setup": 3, "Pantau": 4, "-": 5}
        res = res.assign(_o=res["Status"].map(order)).sort_values(
            ["_o", "Skor", "Jarak ke trigger %"], ascending=[True, False, True]
        ).drop(columns="_o")

        m1, m2, m3 = st.columns(3)
        m1.metric("Saham dipindai", len(rows))
        m2.metric("BUY (3 sinyal)", int((pd.DataFrame(rows)["Status"] == "BUY (3 sinyal)").sum()))
        m3.metric("SIAP breakout", int((pd.DataFrame(rows)["Status"] == "SIAP - tunggu breakout").sum()))

        st.dataframe(res, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Unduh CSV", res.to_csv(index=False).encode("utf-8"), "hasil_scan_bagger.csv", "text/csv")

        if st.session_state.get("failed"):
            with st.expander(f"Data tidak tersedia / kurang dari 260 hari ({len(st.session_state['failed'])})"):
                st.write(", ".join(st.session_state["failed"]))

        # ───────── Chart ─────────
        st.subheader("Grafik")
        pick = st.selectbox("Pilih saham", list(res["Kode"]))
        if pick in st.session_state["frames"]:
            df, f = st.session_state["frames"][pick]
            n = 250
            d, ff = df.tail(n), f.tail(n)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="Harga"))
            fig.add_trace(go.Scatter(x=ff.index, y=ff["sma50"], name="SMA50", line=dict(width=1)))
            fig.add_trace(go.Scatter(x=ff.index, y=ff["sma200"], name="SMA200", line=dict(width=1.5)))
            fig.add_trace(go.Scatter(x=ff.index, y=ff["base_high"], name="Resistance base", line=dict(width=1.5, shape="hv")))
            fig.add_trace(go.Scatter(x=ff.index, y=ff["base_low"], name="Support base", line=dict(width=1, dash="dot", shape="hv")))
            sig = ff[ff["buy"]]
            if not sig.empty:
                fig.add_trace(go.Scatter(x=sig.index, y=d.loc[sig.index, "Low"] * 0.97, mode="markers+text",
                                         marker=dict(symbol="triangle-up", size=14), text=["BUY"] * len(sig), name="BUY"))
            fig.update_layout(height=560, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Klik **Scan sekarang** untuk memulai. Scan pertama butuh beberapa menit; hasil unduhan di-cache 1 jam.")
