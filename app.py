import streamlit as st
import pandas as pd
import numpy as np
import requests
import datetime
import plotly.graph_objects as go
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

# ---------------------------- BEÁLLÍTÁSOK ----------------------------
API_KEY = "bb8600ae3e1b41acac22ce8558f5e2e1"
SYMBOLS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY"
]
INTERVALS = {"5 perc": "5min", "15 perc": "15min"}

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
    df["EMA8"] = df["close"].ewm(span=8).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp1 - exp2
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["Signal"]

    adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["ADX"] = adx.adx()

    # Bollinger-szalag (20 periódus, 2 szórás)
    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_Middle"] = bb.bollinger_mavg()
    df["BB_Upper"] = bb.bollinger_hband()
    df["BB_Lower"] = bb.bollinger_lband()

    return df

# ---------------------------- SZIGNÁL GENERÁLÁS + TP/SL ÉRTÉKELÉS ----------------------------
def generate_signals(df):
    TP_PCT = 0.02  # 2%
    SL_PCT = 0.01  # 1%
    ADX_THRESHOLD = 20

    df["Buy"] = False
    df["Sell"] = False
    df["TP"] = np.nan
    df["SL"] = np.nan
    df["Eredmény"] = ""

    for i in range(len(df) - 5):
        price = df.at[i, "close"]

        # Feltételek vételre:
        buy_cond = (
            (df.at[i, "EMA8"] > df.at[i, "EMA21"]) and
            (df.at[i, "RSI"] < 80) and
            (df.at[i, "MACD_Hist"] > 0) and
            (df.at[i, "ADX"] > ADX_THRESHOLD) and
            (price <= df.at[i, "BB_Lower"] * 1.01)  # ár a Bollinger alsó szalag alatt vagy nagyon közel
        )
        # Feltételek eladásra:
        sell_cond = (
            (df.at[i, "EMA8"] < df.at[i, "EMA21"]) and
            (df.at[i, "RSI"] > 20) and
            (df.at[i, "MACD_Hist"] < 0) and
            (df.at[i, "ADX"] > ADX_THRESHOLD) and
            (price >= df.at[i, "BB_Upper"] * 0.99)  # ár a Bollinger felső szalag felett vagy nagyon közel
        )

        if buy_cond:
            df.at[i, "Buy"] = True
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl
            # Vizsgáljuk az ármozgást az elkövetkező 5 gyertyán belül
            for j in range(1, 6):
                high = df.at[i + j, "high"]
                low = df.at[i + j, "low"]
                if high >= tp:
                    df.at[i, "Eredmény"] = "TP"
                    break
                elif low <= sl:
                    df.at[i, "Eredmény"] = "SL"
                    break
            if df.at[i, "Eredmény"] == "":
                df.at[i, "Eredmény"] = "Semmi"

        elif sell_cond:
            df.at[i, "Sell"] = True
            tp = price * (1 - TP_PCT)
            sl = price * (1 + SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl
            for j in range(1, 6):
                high = df.at[i + j, "high"]
                low = df.at[i + j, "low"]
                if low <= tp:
                    df.at[i, "Eredmény"] = "TP"
                    break
                elif high >= sl:
                    df.at[i, "Eredmény"] = "SL"
                    break
            if df.at[i, "Eredmény"] == "":
                df.at[i, "Eredmény"] = "Semmi"

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

    # Bollinger-szalagok megjelenítése
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Upper"], mode="lines", name="BB Felső szalag", line=dict(color="blue", dash="dash")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Middle"], mode="lines", name="BB Közép szalag", line=dict(color="blue", dash="dot")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Lower"], mode="lines", name="BB Alsó szalag", line=dict(color="blue", dash="dash")))

    buy_signals = df[df["Buy"]]
    sell_signals = df[df["Sell"]]

    fig.add_trace(go.Scatter(x=buy_signals["time"], y=buy_signals["close"],
                             mode="markers", name="Vétel", marker=dict(color="green", size=10, symbol="arrow-up")))

    fig.add_trace(go.Scatter(x=sell_signals["time"], y=sell_signals["close"],
                             mode="markers", name="Eladás", marker=dict(color="red", size=10, symbol="arrow-down")))

    fig.update_layout(title=f"{symbol} árfolyam és jelek", xaxis_title="Idő", yaxis_title="Ár",
                      xaxis_rangeslider_visible=False, template="plotly_dark")
    return fig

# ---------------------------- STREAMLIT FELÜLET ----------------------------
def main():
    st.title("📈 Forex Scalping Stratégia – 5m / 15m")

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
        st.dataframe(df[["time", "close", "Buy", "Sell", "TP", "SL"]].sort_values("time", ascending=False).head(10))

        st.subheader("📈 Utolsó 100 szignál eredménye")
        signals = df[df["Buy"] | df["Sell"]].sort_values("time", ascending=False).head(100)
        st.dataframe(signals[["time", "close", "Buy", "Sell", "TP", "SL", "Eredmény"]])

        tp_ratio = (signals["Eredmény"] == "TP").mean() * 100
        sl_ratio = (signals["Eredmény"] == "SL").mean() * 100
        st.metric("✅ TP arány", f"{tp_ratio:.2f}%")
        st.metric("❌ SL arány", f"{sl_ratio:.2f}%")

    except Exception as e:
        st.error(f"Hiba történt: {str(e)}")

if __name__ == "__main__":
    main()
