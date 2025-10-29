import os
import asyncio
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from ta.momentum import RSIIndicator
from telegram import Bot

# --- Variables de entorno ---
API_TOKEN = os.getenv("7901741145:AAFPr0wLmKVDkHV30_clU9eGcX8doi8mjQQ")
CHAT_ID = int(os.getenv("1347933429"))

if not API_TOKEN or not CHAT_ID:
    raise ValueError("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en variables de entorno.")

bot = Bot(token=API_TOKEN)

# --- Funciones ---
def obtener_datos(crypto, timeframe="15m", limit=200):
    try:
        binance = ccxt.binance()
        ohlc = binance.fetch_ohlcv(crypto, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlc, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as e:
        print(f"❌ Error al obtener datos de {crypto}: {e}")
        return pd.DataFrame()

def calcular_indicadores(df):
    if df.empty:
        return df, None, None
    df['MA50'] = df['close'].rolling(50).mean()
    df['MA200'] = df['close'].rolling(200).mean()
    rsi_indicator = RSIIndicator(df['close'], window=14)
    df['RSI'] = rsi_indicator.rsi()
    soporte = df['low'].min() if not df.empty else None
    resistencia = df['high'].max() if not df.empty else None
    return df, soporte, resistencia

def generar_grafico(df, crypto, soporte, resistencia, puntos=50):
    if df.empty:
        return None, None
    df = df.tail(puntos)
    
    estilo = mpf.make_mpf_style(
        base_mpf_style='yahoo', 
        marketcolors=mpf.make_marketcolors(up='green', down='red'),
        rc={'font.size':8}
    )
    
    archivo = f"{crypto.replace('/', '')}_grafico.png"
    
    addplots = []
    if df['MA50'].notna().any():
        addplots.append(mpf.make_addplot(df['MA50'], color='skyblue'))
    if df['MA200'].notna().any():
        addplots.append(mpf.make_addplot(df['MA200'], color='orange'))
    
    mpf.plot(df, type='candle', addplot=addplots, style=estilo,
             title=f"{crypto} - Últimos {puntos} puntos", ylabel='Precio',
             savefig=archivo, tight_layout=True)
    
    archivo_rsi = f"{crypto.replace('/', '')}_rsi.png"
    plt.figure(figsize=(6,3))
    plt.plot(df.index, df['RSI'], label='RSI', color='purple', linewidth=1.5)
    plt.axhline(70, color='red', linestyle='--', alpha=0.5)
    plt.axhline(30, color='green', linestyle='--', alpha=0.5)
    plt.title(f"{crypto} - RSI")
    plt.ylabel('RSI')
    plt.xticks(rotation=15)
    plt.legend()
    plt.tight_layout()
    plt.savefig(archivo_rsi)
    plt.close()
    
    return archivo, archivo_rsi

async def enviar_alerta(crypto, df, ultimo, soporte, resistencia, rsi):
    if df.empty or soporte is None or resistencia is None:
        return
    
    margen = 0.025  # 2.5%
    if abs(ultimo - soporte)/soporte < margen or abs(ultimo - resistencia)/resistencia < margen:
        archivo, archivo_rsi = generar_grafico(df, crypto, soporte, resistencia)
        texto = (f"📊 {crypto}\nPrecio: {ultimo:.2f}\nRSI: {rsi:.2f}\n"
                 f"Soporte: {soporte:.2f}\nResistencia: {resistencia:.2f}")
        try:
            async with bot:
                if archivo:
                    await bot.send_photo(chat_id=CHAT_ID, photo=open(archivo, 'rb'), caption=texto)
                if archivo_rsi:
                    await bot.send_photo(chat_id=CHAT_ID, photo=open(archivo_rsi, 'rb'), caption=f"{crypto} - RSI")
        except Exception as e:
            print(f"❌ Error al enviar alerta de {crypto}: {e}")

async def revisar_cryptos():
    # 10 principales criptos por capitalización
    cryptos = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", 
               "ADA/USDT", "SOL/USDT", "DOGE/USDT", "DOT/USDT", 
               "LTC/USDT", "LINK/USDT"]
    for crypto in cryptos:
        try:
            df = obtener_datos(crypto)
            df, soporte, resistencia = calcular_indicadores(df)
            if df.empty:
                continue
            ultimo = float(df['close'].iloc[-1])
            rsi_ultimo = float(df['RSI'].iloc[-1])
            await enviar_alerta(crypto, df, ultimo, soporte, resistencia, rsi_ultimo)
        except Exception as e:
            print(f"❌ Error con {crypto}: {e}")

async def main():
    async with bot:
        await bot.send_message(chat_id=CHAT_ID, text="✅ Bot avanzado con gráficos limpios iniciado.")
        while True:
            await revisar_cryptos()
            await asyncio.sleep(900)  # cada 15 minutos

if __name__ == "__main__":
    asyncio.run(main())


