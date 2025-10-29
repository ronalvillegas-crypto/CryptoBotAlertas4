import os
import asyncio
import threading
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from telegram import Bot
from flask import Flask

# --- Variables de entorno ---
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("TELEGRAM_CHAT_ID")

if CHAT_ID_ENV is None:
    raise ValueError("❌ La variable de entorno TELEGRAM_CHAT_ID no está configurada")
CHAT_ID = int(CHAT_ID_ENV)

if not API_TOKEN:
    raise ValueError("❌ Falta la variable de entorno TELEGRAM_TOKEN")

bot = Bot(token=API_TOKEN)
print("✅ Configuración correcta de variables de entorno.")
print("🔄 Usando API pública de Bybit (sin clave privada).")

# --- Funciones principales ---
def obtener_datos(crypto, timeframe="15m", limit=200):
    """Obtiene datos OHLC de Bybit usando API pública."""
    try:
        exchange = ccxt.bybit({'enableRateLimit': True})
        ohlc = exchange.fetch_ohlcv(crypto, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlc, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as e:
        print(f"❌ Error al obtener datos de {crypto}: {e}")
        return pd.DataFrame()

def calcular_indicadores(df):
    """Calcula indicadores técnicos avanzados."""
    if df.empty:
        return df, None, None

    df['EMA20'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['EMA50'] = EMAIndicator(df['close'], window=50).ema_indicator()
    df['RSI'] = RSIIndicator(df['close'], window=14).rsi()

    macd = MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()

    bb = BollingerBands(df['close'])
    df['BB_low'] = bb.bollinger_lband()
    df['BB_high'] = bb.bollinger_hband()

    soporte = df['low'].min()
    resistencia = df['high'].max()
    return df, soporte, resistencia

def generar_grafico(df, crypto, soporte, resistencia, puntos=50):
    """Genera gráficos de velas y RSI."""
    if df.empty:
        return None, None
    df = df.tail(puntos)

    estilo = mpf.make_mpf_style(
        base_mpf_style='yahoo',
        marketcolors=mpf.make_marketcolors(up='green', down='red'),
        rc={'font.size': 8}
    )

    archivo = f"{crypto.replace('/', '')}_grafico.png"
    archivo_rsi = f"{crypto.replace('/', '')}_rsi.png"

    addplots = [
        mpf.make_addplot(df['EMA20'], color='skyblue'),
        mpf.make_addplot(df['EMA50'], color='orange')
    ]

    mpf.plot(df, type='candle', addplot=addplots, style=estilo,
             title=f"{crypto} - Últimos {puntos} puntos", ylabel='Precio',
             savefig=archivo, tight_layout=True)

    plt.figure(figsize=(6, 3))
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

async def enviar_alerta(crypto, df, ultimo, soporte, resistencia):
    """Envía alerta a Telegram con niveles de confianza."""
    if df.empty or soporte is None or resistencia is None:
        return

    rsi = df['RSI'].iloc[-1]
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    macd_val = df['MACD'].iloc[-1]
    macd_signal = df['MACD_signal'].iloc[-1]
    bb_low = df['BB_low'].iloc[-1]
    bb_high = df['BB_high'].iloc[-1]

    # Contadores de condiciones
    condiciones_compra = sum([
        rsi < 35,
        ema20 > ema50,
        macd_val > macd_signal,
        ultimo <= bb_low
    ])
    condiciones_venta = sum([
        rsi > 65,
        ema20 < ema50,
        macd_val < macd_signal,
        ultimo >= bb_high
    ])

    tipo = None
    emoji = None
    nivel = None

    if condiciones_compra >= 3:
        tipo, emoji, nivel = "COMPRA FUERTE", "🟩", "✅ Confirmada"
    elif condiciones_compra == 2:
        tipo, emoji, nivel = "COMPRA DÉBIL", "🟨", "⚠️ Posible entrada"
    elif condiciones_venta >= 3:
        tipo, emoji, nivel = "VENTA FUERTE", "🟥", "🚨 Confirmada"
    elif condiciones_venta == 2:
        tipo, emoji, nivel = "VENTA DÉBIL", "🟧", "⚠️ Posible salida"

    if tipo:
        archivo, archivo_rsi = generar_grafico(df, crypto, soporte, resistencia)
        texto = (
            f"{emoji} *{tipo}* ({nivel})\n"
            f"📊 {crypto}\n"
            f"💰 Precio: {ultimo:.2f}\n"
            f"📉 RSI: {rsi:.2f}\n"
            f"📈 EMA20: {ema20:.2f} | EMA50: {ema50:.2f}\n"
            f"🔄 MACD: {macd_val:.4f} | Signal: {macd_signal:.4f}\n"
            f"💎 Soporte: {soporte:.2f}\n"
            f"📉 Resistencia: {resistencia:.2f}"
        )
        try:
            async with bot:
                if archivo:
                    await bot.send_photo(chat_id=CHAT_ID, photo=open(archivo, 'rb'), caption=texto, parse_mode="Markdown")
                if archivo_rsi:
                    await bot.send_photo(chat_id=CHAT_ID, photo=open(archivo_rsi, 'rb'), caption=f"{crypto} - RSI")
        except Exception as e:
            print(f"❌ Error al enviar alerta de {crypto}: {e}")

async def revisar_cryptos():
    """Revisa criptos y genera alertas."""
    cryptos = [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
        "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
        "LTC/USDT", "LINK/USDT"
    ]
    for crypto in cryptos:
        try:
            df = obtener_datos(crypto)
            df, soporte, resistencia = calcular_indicadores(df)
            if df.empty:
                continue
            ultimo = float(df['close'].iloc[-1])
            await enviar_alerta(crypto, df, ultimo, soporte, resistencia)
        except Exception as e:
            print(f"❌ Error con {crypto}: {e}")

async def heartbeat():
    """Mensaje periódico para mantener Render activo."""
    while True:
        print("💓 Bot activo y ejecutándose...")
        await asyncio.sleep(60)

async def main():
    """Bucle principal del bot."""
    async with bot:
        await bot.send_message(chat_id=CHAT_ID, text="✅ Bot avanzado con señales de triple y doble confirmación iniciado.")
        asyncio.create_task(heartbeat())
        while True:
            await revisar_cryptos()
            await asyncio.sleep(900)  # cada 15 min

# --- Servidor Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot de alertas cripto activo y funcionando."

def iniciar_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=iniciar_flask).start()
    asyncio.run(main())

