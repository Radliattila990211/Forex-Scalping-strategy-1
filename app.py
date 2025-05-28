import streamlit as st
import pandas as pd
import numpy as np
import requests
from ta.trend import ADXIndicator
import plotly.graph_objects as go

# ---------------------------- BEÁLLÍTÁSOK ----------------------------
API_KEY = "bb8600ae3e1b41acac22ce8558f5e2e1"
SYMBOLS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY"
]
INTERVALS = {"5 perc": "5min", "15 perc": "15min"}

# Telegram bot beállítások (ide tedd a sajátodat)
TELEGRAM_BOT_TOKEN = "IDE_ÍRD_A_BOT_TOKENED"
TELEGRAM_CHAT_ID = "IDE_ÍRD_A_CHAT_ID"

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

    return df

# ---------------------------- BOLLINGER BAND ----------------------------
def compute_bollinger(df, window=20, n_std=2):
    df["BB_Middle"] = df["close"].rolling(window).mean()
    df["BB_Std"] = df["close"].rolling(window).std()
    df["BB_Upper"] = df["BB_Middle"] + n_std * df["BB_Std"]
    df["BB_Lower"] = df["BB_Middle"] - n_std * df["BB_Std"]
    return df

# ---------------------------- TELEGRAM ÜZENET KÜLDÉS ----------------------------
def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload)
        return response.ok
    except Exception as e:
        print("Telegram üzenet küldési hiba:", e)
        return False

# ---------------------------- SZIGNÁL GENERÁLÁS + TP/SL ÉRTÉKELÉS ----------------------------
def generate_signals(df):
    TP_PCT = 0.008  # 0.8%
    SL_PCT = 0.005  # 0.5%
    LOOKAHEAD = 15  # gyertyaszám a TP/SL vizsgálathoz

    # Vételi jel: EMA8 > EMA21, RSI < 70, MACD_Hist pozitív, ADX > 20, close közel a BB alsó szalaghoz (pl. < BB_Lower + kis buffer)
    df["Buy"] = (
        (df["EMA8"] > df["EMA21"]) &
        (df["RSI"] < 70) &
        (df["MACD_Hist"] > 0) &
        (df["ADX"] > 20) &
        (df["close"] < df["BB_Lower"] * 1.02)
    )

    # Eladási jel: EMA8 < EMA21, RSI > 30, MACD_Hist negatív, ADX > 20, close közel a BB felső szalaghoz (pl. > BB_Upper - kis buffer)
    df["Sell"] = (
        (df["EMA8"] < df["EMA21"]) &
        (df["RSI"] > 30) &
        (df["MACD_Hist"] < 0) &
        (df["ADX"] > 20) &
        (df["close"] > df["BB_Upper"] * 0.98)
    )

    df["TP"] = np.nan
    df["SL"] = np.nan
    df["Eredmény"] = ""

    for i in range(len(df) - LOOKAHEAD):
        price = df.at[i, "close"]

        if df.at[i, "Buy"]:
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            df.at[i, "TP"] = tp
            df.at[i, "SL"] = sl
            for j in range(1, LOOKAHEAD + 1):
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
            for j in range(1, LOOKAHEAD + 1):
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

    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Upper"], mode="lines", name="BB Felső szalag", line=dict(color="cyan", dash='dash')))
    fig.add_trace(go.Scatter(x=df["time"], y=df["BB_Lower"], mode="lines", name="BB Alsó szalag", line=dict(color="cyan", dash='dash')))

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

    # Eltároljuk az előző jelzést session state-ben, hogy tudjuk, mik
