import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from ta.trend import ADXIndicator

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

    # Bollinger szalagok (20 periódus, 2 szórás)
    df["bb_middle"] = df["close"].rolling(window=20).mean()
    df["bb_std"] = df["close"].rolling(window=20).std()
    df["bb_upper"] = df["bb_middle"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_middle"] - 2 * df["bb_std"]

    return df

# ---------------------------- SZIGNÁL GENERÁLÁS + TP/SL ÉRTÉKELÉS ----------------------------
def generate_signals(df):
    TP_PCT = 0.02  # 2%
    SL_PCT = 0.01  # 1%

    df["Buy"] = (
        (df["EMA8"] > df["EMA21"]) &
        (df["RSI"] < 70) &
        (df["MACD_Hist"] > 0) &
        (df["ADX"] > 25)
    )
    df["Sell"] = (
        (df["EMA8"] < df["EMA21"]) &
        (df["RSI"] > 30) &
        (df["MACD_Hist"] < 0) &
        (df["ADX"] > 25)
    )

    df["TP"] = np.nan
    df["SL"] = np.nan
    df["Eredmény"] = ""

    for i in range(len(df) - 5):
        price = df.at[i, "close"]

        if df.at[i, "Buy"]:
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl
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

        elif df.at[i, "Sell"]:
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

#
