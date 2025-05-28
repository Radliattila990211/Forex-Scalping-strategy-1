import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import talib

st.set_page_config(page_title="Forex Scalping Strategy", layout="wide")

def get_data(symbol, period="7d", interval="5m"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        return df
    df.reset_index(inplace=True)
    df.rename(columns={"Datetime": "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    return df

def add_indicators(df):
    df["EMA8"] = talib.EMA(df["Close"], timeperiod=8)
    df["EMA21"] = talib.EMA(df["Close"], timeperiod=21)
    df["RSI"] = talib.RSI(df["Close"], timeperiod=14)
    macd, macd_signal, macd_hist = talib.MACD(df["Close"], fastperiod=12, slowperiod=26, signalperiod=9)
    df["MACD"] = macd
    df["MACD_Signal"] = macd_signal
    df["MACD_Hist"] = macd_hist
    upper, middle, lower = talib.BBANDS(df["Close"], timeperiod=20)
    df["BB_upper"] = upper
    df["BB_middle"] = middle
    df["BB_lower"] = lower
    df["ADX"] = talib.ADX(df["High"], df["Low"], df["Close"], timeperiod=14)
    df.dropna(inplace=True)
    return df

def generate_signals(df):
    TP_PCT = 0.015  # 1.5%
    SL_PCT = 0.015  # 1.5%
    ADX_THRESHOLD = 20  # lazább küszöb

    df["Buy"] = False
    df["Sell"] = False
    df["TP"] = np.nan
    df["SL"] = np.nan
    df["Eredmény"] = ""

    for i in range(len(df) - 6):  # 5 gyertya TP/SL vizsgálat
        price = df.at[df.index[i], "Close"]

        buy_cond = (
            (df.at[df.index[i], "EMA8"] > df.at[df.index[i], "EMA21"]) and
            (df.at[df.index[i], "RSI"] < 70) and
            (df.at[df.index[i], "MACD_Hist"] > 0) and
            (df.at[df.index[i], "ADX"] > ADX_THRESHOLD)
        )
        sell_cond = (
            (df.at[df.index[i], "EMA8"] < df.at[df.index[i], "EMA21"]) and
            (df.at[df.index[i], "RSI"] > 30) and
            (df.at[df.index[i], "MACD_Hist"] < 0) and
            (df.at[df.index[i], "ADX"] > ADX_THRESHOLD)
        )

        if buy_cond:
            df.at[df.index[i], "Buy"] = True
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            df.at[df.index[i], "TP"] = tp
            df.at[df.index[i], "SL"] = sl
            eredmeny = ""
            for j in range(1, 6):
                if i + j >= len(df):
                    break
                high = df.at[df.index[i + j], "High"]
                low = df.at[df.index[i + j], "Low"]
                if high >= tp:
                    eredmeny = "TP"
                    break
                elif low <= sl:
                    eredmeny = "SL"
                    break
            df.at[df.index[i], "Eredmény"] = eredmeny if eredmeny else "Semmi"

        elif sell_cond:
            df.at[df.index[i], "Sell"] = True
            tp = price * (1 - TP_PCT)
            sl = price * (1 + SL_PCT)
            df.at[df.index[i], "TP"] = tp
            df.at[df.index[i], "SL"] = sl
            eredmeny = ""
            for j in range(1, 6):
                if i + j >= len(df):
                    break
                high = df.at[df.index[i + j], "High"]
                low = df.at[df.index[i + j], "Low"]
                if low <= tp:
                    eredmeny = "TP"
                    break
                elif high >= sl:
                    eredmeny = "SL"
                    break
            df.at[df.index[i], "Eredmény"] = eredmeny if eredmeny else "Semmi"

    return df

def main():
    st.title("Forex Scalping Strategy")

    pairs = [
        "AUDCAD=X", "EURUSD=X", "USDJPY=X", "GBPUSD=X",
        "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X",
        "GBPJPY=X", "EURJPY=X", "EURGBP=X"
    ]

    selected_pair = st.selectbox("Válassz devizapárt:", pairs, index=1)

    with st.spinner("Adatok lekérése és feldolgozása..."):
        df = get_data(selected_pair, period="7d", interval="5m")
        if df.empty:
            st.error("Nem sikerült adatot lekérni a kiválasztott párra.")
            return
        df = add_indicators(df)
        df = generate_signals(df)

    st.subheader(f"Jelzések és adatok: {selected_pair}")

    # Jelzések összesítése
    buy_signals = df[df["Buy"] == True]
    sell_signals = df[df["Sell"] == True]

    st.write(f"Vételi jelek száma: {len(buy_signals)}")
    st.write(f"Eladási jelek száma: {len(sell_signals)}")

    # Jelzések részletezése táblázatban
    signals_df = df[(df["Buy"] == True) | (df["Sell"] == True)][
        ["Close", "EMA8", "EMA21", "RSI", "MACD_Hist", "ADX", "Buy", "Sell", "TP", "SL", "Eredmény"]
    ].copy()
    signals_df.index = signals_df.index.astype(str)
    st.dataframe(signals_df.style.highlight_max(axis=0))

    # Grafikon mutatása
    import plotly.graph_objects as go

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candlesticks"
    ))

    fig.add_trace(go.Scatter(x=df.index, y=df["EMA8"], line=dict(color="blue", width=1), name="EMA8"))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA21"], line=dict(color="orange", width=1), name="EMA21"))
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_upper"], line=dict(color="grey", width=1, dash="dot"), name="BB Upper"))
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_middle"], line=dict(color="grey", width=1), name="BB Middle"))
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_lower"], line=dict(color="grey", width=1, dash="dot"), name="BB Lower"))

    buys = df[df["Buy"] == True]
    sells = df[df["Sell"] == True]

    fig.add_trace(go.Scatter(
        x=buys.index, y=buys["Close"],
        mode="markers", marker=dict(symbol="triangle-up", color="green", size=10),
        name="Buy Signals"
    ))
    fig.add_trace(go.Scatter(
        x=sells.index, y=sells["Close"],
        mode="markers", marker=dict(symbol="triangle-down", color="red", size=10),
        name="Sell Signals"
    ))

    st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
