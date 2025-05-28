import streamlit as st
import pandas as pd
import numpy as np
import requests
import datetime
import plotly.graph_objects as go

# ---------------------------- BEÁLLÍTÁSOK ----------------------------
API_KEY = "bb8600ae3e1b41acac22ce8558f5e2e1"
SYMBOLS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY"
]
INTERVALS = {"5 perc": "5min", "15 perc": "15min"}

# TP és SL százalékban
TP_PCT = 0.008  # 0.8%
SL_PCT = 0.005  # 0.5%

# ---------------------------- ADATBETÖLTÉS ----------------------------
@st.cache_data(ttl=300)
def load_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize=200"
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
    # EMA 50 és 100
    df["EMA50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["EMA100"] = df["close"].ewm(span=100, adjust=False).mean()

    # Stochastic Oscillator (14, 3, 3)
    low14 = df["low"].rolling(window=14).min()
    high14 = df["high"].rolling(window=14).max()
    df["%K"] = 100 * (df["close"] - low14) / (high14 - low14)
    df["%D"] = df["%K"].rolling(window=3).mean()

    return df

# ---------------------------- SZIGNÁL GENERÁLÁS TP/SL-vel ----------------------------
def generate_signals(df):
    df["Buy"] = False
    df["Sell"] = False
    df["TP"] = np.nan
    df["SL"] = np.nan

    for i in range(1, len(df)):
        price = df.at[i, "close"]
        ema50 = df.at[i, "EMA50"]
        ema100 = df.at[i, "EMA100"]
        stochastic_k = df.at[i, "%K"]
        stochastic_d = df.at[i, "%D"]

        # Ár legyen az EMA-k +/- 0.2%-án belül
        ema_mid = (ema50 + ema100) / 2
        tol = ema_mid * 0.002  # 0.2% tűrés
        close_near_ema = (price >= (ema_mid - tol)) and (price <= (ema_mid + tol))

        # Long belépő feltételek
        if (ema50 > ema100) and close_near_ema:
            if stochastic_k > 20 and stochastic_d > 20 and stochastic_k > stochastic_d:
                df.at[i, "Buy"] = True
                df.at[i, "TP"] = price * (1 + TP_PCT)
                df.at[i, "SL"] = price * (1 - SL_PCT)

        # Short belépő feltételek
        elif (ema50 < ema100) and close_near_ema:
            if stochastic_k < 80 and stochastic_d < 80 and stochastic_k < stochastic_d:
                df.at[i, "Sell"] = True
                df.at[i, "TP"] = price * (1 - TP_PCT)
                df.at[i, "SL"] = price * (1 + SL_PCT)

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
    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA50"], mode="lines", name="EMA 50", line=dict(color="orange")))
    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA100"], mode="lines", name="EMA 100", line=dict(color="purple")))

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
    st.title("📈 Forex Scalping Stratégia – EMA & Stochastic + TP/SL")

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

        st.subheader("📊 Utolsó 20 szignál TP/SL szintekkel")
        szignalok = df[(df["Buy"]) | (df["Sell"])].sort_values("time", ascending=False).head(20)
        if szignalok.empty:
            st.write("Nincs jelenleg szignál.")
        else:
            # Oszlopok: idő, ár, Buy, Sell, TP, SL
            szignalok_display = szignalok[["time", "close", "Buy", "Sell", "TP", "SL"]].copy()
            szignalok_display["Buy"] = szignalok_display["Buy"].apply(lambda x: "Igen" if x else "")
            szignalok_display["Sell"] = szignalok_display["Sell"].apply(lambda x: "Igen" if x else "")
            szignalok_display["TP"] = szignalok_display["TP"].apply(lambda x: f"{x:.5f}")
            szignalok_display["SL"] = szignalok_display["SL"].apply(lambda x: f"{x:.5f}")
            st.dataframe(szingalok_display)

        st.write(f"Összes vételi jel: {df['Buy'].sum()}, összes eladási jel: {df['Sell'].sum()}")

    except Exception as e:
        st.error(f"Hiba történt: {str(e)}")

if __name__ == "__main__":
    main()
