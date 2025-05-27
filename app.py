import streamlit as st
import pandas as pd
import requests 
import ta
import plotly.graph_objects as go

API_KEY = st.secrets["TWELVE_DATA_API_KEY"] if "TWELVE_DATA_API_KEY" in st.secrets else "IDE_ÍRD_BE_A_TWELVE_DATA_API_KULCSODAT"

FOREX_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD"
]

@st.cache_data(ttl=300)
def load_forex_data(symbol="EUR/USD"):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&apikey={API_KEY}&format=JSON&outputsize=100"
    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        st.error(f"Nem sikerült lekérni az adatokat a(z) {symbol} párhoz. Ellenőrizd az API kulcsot vagy a szimbólumot.")
        return None
    
    df = pd.DataFrame(data["values"])
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

def analyze_and_plot(df, symbol):
    # Számolja az indikátorokat
    df['EMA8'] = ta.trend.ema_indicator(df['close'], window=8)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    df['MACD_hist'] = macd.macd_diff()

    # Jelzések
    df['signal'] = 0
    long_condition = (df['EMA8'] > df['EMA21']) & (df['EMA8'].shift(1) <= df['EMA21'].shift(1))
    long_rsi_condition = df['RSI'] < 70
    long_macd_condition = df['MACD_hist'] > 0

    short_condition = (df['EMA8'] < df['EMA21']) & (df['EMA8'].shift(1) >= df['EMA21'].shift(1))
    short_rsi_condition = df['RSI'] > 30
    short_macd_condition = df['MACD_hist'] < 0

    df.loc[long_condition & long_rsi_condition & long_macd_condition, 'signal'] = 1
    df.loc[short_condition & short_rsi_condition & short_macd_condition, 'signal'] = -1

    # Mutatjuk az adatokat
    st.subheader(f"Adatok és jelzések: {symbol}")
    st.dataframe(df.tail(15))

    # Chart
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

    selected_pairs = st.multiselect(
        "Válassz forex pár(oka)t a következők közül:", 
        FOREX_PAIRS, 
        default=["EUR/USD"]
    )

    if not selected_pairs:
        st.warning("Legalább egy forex párat válassz ki.")
        return

    for symbol in selected_pairs:
        df = load_forex_data(symbol)
        if df is None or df.empty:
            st.warning(f"Nincs adat a {symbol} párhoz.")
            continue
        analyze_and_plot(df, symbol)

    st.info("Az adatok 5 percenként frissülnek az API korlátok miatt.")

if __name__ == "__main__":
    main() 
