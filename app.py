import streamlit as st
import pandas as pd
import numpy as np
import requests
import datetime
import plotly.graph_objects as go
from ta.trend import ADXIndicator, MACD
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator

# ---------------------------- BEÁLLÍTÁSOK ----------------------------
API_KEY = "bb8600ae3e1b41acac22ce8558f5e2e1"
SYMBOLS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY"
]
INTERVALS = {"5 perc": "5min", "15 perc": "15min"}

TP_PCT = 0.008  # Take Profit 0.8%
SL_PCT = 0.005  # Stop Loss 0.5%
ADX_THRESHOLD = 20  # ADX threshold

# ---------------------------- ADATBETÖLTÉS ----------------------------
@st.cache_data(ttl=300)
def load_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize=100"
    response = requests.get(url)
    data = response.json()
    if "values" not in data:
        raise ValueError(f"Hiba az adatok betöltésekor: {data.get('message', 'Ismeretlen hiba')}")
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col])
    return df.reset_index(drop=True)

# ---------------------------- TECHNIKAI INDIKÁTOROK ----------------------------
def compute_indicators(df):
    df["EMA8"] = df["close"].ewm(span=8, adjust=False).mean()
    df["EMA21"] = df["close"].ewm(span=21, adjust=False).mean()

    rsi_ind = RSIIndicator(close=df["close"], window=14)
    df["RSI"] = rsi_ind.rsi()

    macd_ind = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["MACD"] = macd_ind.macd()
    df["Signal"] = macd_ind.macd_signal()
    df["MACD_Hist"] = macd_ind.macd_diff()

    adx_ind = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["ADX"] = adx_ind.adx()

    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()
    df["BB_Mid"] = bb.bollinger_mavg()

    return df

# ---------------------------- SZIGNÁL GENERÁLÁS + TP/SL ÉRTÉKELÉS ----------------------------
def generate_signals(df):
    df["Buy"] = False
    df["Sell"] = False
    df["TP"] = np.nan
    df["SL"] = np.nan
    df["Eredmény"] = ""

    for i in range(len(df) - 15):
        # Kicsit lazább feltételek, hogy több jelzés legyen
        buy_cond = (
            (df.at[i, "EMA8"] >= df.at[i, "EMA21"]) and
            (df.at[i, "RSI"] < 75) and
            (df.at[i, "MACD_Hist"] > 0) and
            (df.at[i, "ADX"] > ADX_THRESHOLD) and
            (df.at[i, "close"] <= df.at[i, "BB_Low"] * 1.02)  # Kicsit megengedőbb alsó Bollinger körül
        )
        sell_cond = (
            (df.at[i, "EMA8"] <= df.at[i, "EMA21"]) and
            (df.at[i, "RSI"] > 25) and
            (df.at[i, "MACD_Hist"] < 0) and
            (df.at[i, "ADX"] > ADX_THRESHOLD) and
            (df.at[i, "close"] >= df.at[i, "BB_High"] * 0.98)  # Kicsit megengedőbb felső Bollinger körül
        )

        price = df.at[i, "close"]

        if buy_cond:
            df.at[i, "Buy"] = True
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl

            eredmeny = ""
            for j in range(1, 16):
                if i + j >= len(df):
                    break
                high = df.at[i + j, "high"]
                low = df.at[i + j, "low"]
                if high >= tp:
                    eredmeny = "TP"
                    break
                elif low <= sl:
                    eredmeny = "SL"
                    break
            df.at[i, "Eredmény"] = eredmeny if eredmeny else "Semmi"

        elif sell_cond:
            df.at[i, "Sell"] = True
            tp = price * (1 - TP_PCT)
            sl = price * (1 + SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl

            eredmeny = ""
            for j in range(1, 16):
                if i + j >= len(df):
                    break
                high = df.at[i + j, "high"]
                low = df.at[i + j, "low"]
                if low <= tp:
                    eredmeny = "TP"
                    break
                elif high >= sl:
                    eredmeny = "SL"
                    break
            df.at[i, "Eredmény"] = eredmeny if eredmeny else "Semmi"

    return df

# ---------------------------- GRAFIKON ----------------------------
def plot_chart(df, symbol):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df["time"],
        open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name="Ár"
    ))
    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA8"], mode="lines", name="EMA 8", line=dict(color="orange")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA21"], mode="lines", name="EMA 21", line=dict(color="purple")))

    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_High"], mode="lines", name="Bollinger Felső", line=dict(color="cyan", dash="dash")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Mid"], mode="lines", name="Bollinger Közép", line=dict(color="gray", dash="dot")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Low"], mode="lines", name="Bollinger Alsó", line=dict(color="cyan", dash="dash")))

    buy_signals = df[df["Buy"]]
    sell_signals = df[df["Sell"]]

    fig.add_trace(go.Scatter(x=buy_signals["time"], y=buy_signals["close"],
                             mode="markers", name="Vétel", marker=dict(color="green", size=12, symbol="arrow-up")))

    fig.add_trace(go.Scatter(x=sell_signals["time"], y=sell_signals["close"],
                             mode="markers", name="Eladás", marker=dict(color="red", size=12, symbol="arrow-down")))

    fig.update_layout(title=f"{symbol} árfolyam és jelek", xaxis_title="Idő", yaxis_title="Ár",
                      xaxis_rangeslider_visible=False, template="plotly_dark")
    return fig

# ---------------------------- STREAMLIT FELÜLET ----------------------------
def main():
    st.title("📈 Forex Scalping Stratégiád – Több jelzés, ADX20, TP/SL finomítva")

    col1, col2 = st.columns(2)
    with col1:
        selected_symbol = st.selectbox("Válaszd ki a devizapárt:", SYMBOLS)
    with col2:
        selected_interval = st.selectbox("Válaszd ki az időkeretet:", list(INTERVALS.keys()))

    try:
        df = load_data(selected_symbol, INTERVALS[selected_interval])
        df = compute_indicators(df)
        df = generate_signals(df)

        st.plotly_chart(plot_chart(df, selected_symbol), use_container_width=True)

        st.subheader("📊 Legutóbbi szignálok TP/SL szintekkel")
        st.dataframe(df[["time", "close", "Buy", "Sell", "TP", "SL", "Eredmény"]].sort_values("time", ascending=False).head(30))

        st.subheader("📈 Szignálok statisztika az utolsó 100 jelzésből")
        signals = df[(df["Buy"] | df["Sell"])].sort_values("time", ascending=False).head(100)
        tp_ratio = (signals["Eredmény"] == "TP").mean() * 100
        sl_ratio = (signals["Eredmény"] == "SL").mean() * 100
        st.metric("✅ TP arány", f"{tp_ratio:.2f}%")
        st.metric("❌ SL arány", f"{sl_ratio:.2f}%")

    except Exception as e:
        st.error(f"Hiba történt: {str(e)}")

if __name__ == "__main__":
    main()
