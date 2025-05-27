import streamlit as st
import pandas as pd
import ta
import plotly.graph_objects as go

st.set_page_config(page_title="Forex Skalpolási Stratégia 5 perc", layout="wide")

st.title("Forex Skalpolási Stratégia 5 perces időtávon\nRSI, EMA, MACD alapján")

st.markdown("""
Ez az alkalmazás egy egyszerű skalpolási stratégiát valósít meg 5 perces időtávon, ahol az EMA8 és EMA21 kereszteket,
az RSI-t és a MACD hisztogramot használjuk vételi és eladási jelzésekhez.

**Használat:**
- Töltsd fel az 5 perces gyertyaadatokat CSV-ben (oszlopok: `date, open, high, low, close, volume`)
- A program kiszámolja az indikátorokat, és megjeleníti a jelzéseket a charton.

**Jelzések:**
- 🟢 Zöld háromszög = vételi jelzés
- 🔴 Piros háromszög = eladási jelzés
""")

uploaded_file = st.file_uploader("CSV fájl feltöltése (date, open, high, low, close, volume)", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        st.error(f"A CSV fájlnak tartalmaznia kell az alábbi oszlopokat: {required_cols}")
    else:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        # Indikátorok számítása
        df['EMA8'] = ta.trend.ema_indicator(df['close'], window=8)
        df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['MACD_hist'] = macd.macd_diff()

        # Jelzés logika
        df['signal'] = 0
        long_condition = (df['EMA8'] > df['EMA21']) & (df['EMA8'].shift(1) <= df['EMA21'].shift(1))
        long_rsi_condition = df['RSI'] < 70
        long_macd_condition = df['MACD_hist'] > 0

        short_condition = (df['EMA8'] < df['EMA21']) & (df['EMA8'].shift(1) >= df['EMA21'].shift(1))
        short_rsi_condition = df['RSI'] > 30
        short_macd_condition = df['MACD_hist'] < 0

        df.loc[long_condition & long_rsi_condition & long_macd_condition, 'signal'] = 1
        df.loc[short_condition & short_rsi_condition & short_macd_condition, 'signal'] = -1

        st.subheader("Legutóbbi jelzések")
        st.dataframe(df[['date', 'close', 'EMA8', 'EMA21', 'RSI', 'MACD_hist', 'signal']].tail(15))

        # Chart kirajzolása Plotly-val
        fig = go.Figure(data=[go.Candlestick(
            x=df['date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Gyertyák'
        )])

        fig.add_trace(go.Scatter(x=df['date'], y=df['EMA8'], mode='lines', line=dict(color='blue', width=1), name='EMA8'))
        fig.add_trace(go.Scatter(x=df['date'], y=df['EMA21'], mode='lines', line=dict(color='orange', width=1), name='EMA21'))

        buys = df[df['signal'] == 1]
        sells = df[df['signal'] == -1]

        fig.add_trace(go.Scatter(
            x=buys['date'],
            y=buys['close'],
            mode='markers',
            marker=dict(symbol='triangle-up', size=15, color='green'),
            name='Vételi jelzés'
        ))

        fig.add_trace(go.Scatter(
            x=sells['date'],
            y=sells['close'],
            mode='markers',
            marker=dict(symbol='triangle-down', size=15, color='red'),
            name='Eladási jelzés'
        ))

        fig.update_layout(
            xaxis_rangeslider_visible=False,
            margin=dict(l=20, r=20, t=30, b=20),
            height=600,
            template='plotly_dark',
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Tölts fel egy CSV fájlt 5 perces gyertyákkal (oszlopok: date, open, high, low, close, volume).")
