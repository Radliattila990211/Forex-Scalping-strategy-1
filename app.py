import streamlit as st
import pandas as pd
import requests
import ta
import plotly.graph_objects as go
import urllib.parse

API_KEY = st.secrets["TWELVE_DATA_API_KEY"] if "TWELVE_DATA_API_KEY" in st.secrets else ""

# Forex párok a Twelve Data API dokumentáció szerint perjellel
FOREX_PAIRS_API = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD"]
# Felhasználónak megjelenő formátum (ez most megegyezik az API-val)
FOREX_PAIRS_DISPLAY = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD"]

@st.cache_data(ttl=300)
def load_forex_data(symbol="EUR/USD"):
    symbol_encoded = urllib.parse.quote(symbol)  # Pl. "USD/JPY" -> "USD%2FJPY"
    url = f"https://api.twelvedata.com/time_series?symbol={symbol_encoded}&interval=5min&apikey={API_KEY}&format=JSON&outputsize=100"
    response = requests.get(url)

    if response.status_code != 200:
        st.error(f"Hálózati hiba történt: {response.status_code}")
        return None

    data = response.json()

    if "values" not in data:
        msg = data.get("message", "Ismeretlen hiba az API válaszában.")
        st.error(f"Nem sikerült adatot lekérni a {symbol} párhoz. Hiba: {msg}")
        return None

    df = pd.DataFrame(data["values"])

    expected_cols = {"datetime", "open", "high", "low", "close", "volume"}
    if not expected_cols.issubset(df.columns):
        st.error(f"Hiányzó adat oszlopok az API válaszában: {expected_cols - set(df.columns)}")
        return None

    df = df.rename(columns={
        "datetime": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume"
    })
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def analyze_and_plot(df, symbol_display):
    df['EMA8'] = ta.trend.ema_indicator(df['close'], window=8)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    df['MACD_hist'] = macd.macd_diff()

    df['signal'] = 0
    long_condition = (df['EMA8'] > df['EMA21']) & (df['EMA8'].shift(1) <= df['EMA21'].shift(1))
    long_rsi_condition = df['RSI'] < 70
    long_macd_condition = df['MACD_hist'] > 0

    short_condition = (df['EMA8'] < df['EMA21']) & (df['EMA8'].shift(1) >= df['EMA21'].shift(1))
    short_rsi_condition = df['RSI'] > 30
    short_macd_condition = df['MACD_hist'] < 0

    df.loc[long_condition & long_rsi_condition & long_macd_condition, 'signal'] = 1
    df.loc[short_condition & short_rsi_condition & short_macd_condition, 'signal'] = -1

    st.subheader(f"Adatok és jelzések: {symbol_display}")
    st.dataframe(df.tail(15))

    fig = go.Figure(data=[go.Candlestick(
        x=df['date'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Gyertyák'
    )])

    fig.add_trace(go.Scatter(x=df['date'], y=df['EMA8'], mode='lines', name='EMA8', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=df['date'], y=df['EMA21'], mode='lines', name='EMA21', line=dict(color='orange')))

    buys = df[df['signal'] == 1]
    sells = df[df['signal'] == -1]

    fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers',
                             marker=dict(symbol='triangle-up', size=15, color='green'), name='Vételi jelzés'))
    fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers',
                             marker=dict(symbol='triangle-down', size=15, color='red'), name='Eladási jelzés'))

    fig.update_layout(xaxis_rangeslider_visible=False, template='plotly_dark', height=600)

    st.plotly_chart(fig, use_container_width=True)

def main():
    st.title("Élő Forex Skalpolási Stratégia (5 perc)")

    selected_display = st.multiselect(
        "Válassz forex pár(oka)t a következők közül:",
        FOREX_PAIRS_DISPLAY,
        default=["EUR/USD"]
    )

    if not selected_display:
        st.warning("Legalább egy forex párat válassz ki.")
        return

    for symbol_display in selected_display:
        symbol_api = FOREX_PAIRS_API[FOREX_PAIRS_DISPLAY.index(symbol_display)]
        df = load_forex_data(symbol_api)
        if df is None or df.empty:
            st.warning(f"Nincs elérhető adat a {symbol_display} párhoz.")
            continue
        analyze_and_plot(df, symbol_display)

    st.info("Az adatok 5 percenként frissülnek az API korlátok miatt.")

if __name__ == "__main__":
    main()
