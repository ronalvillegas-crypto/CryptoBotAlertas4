import os
import asyncio
import threading
import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
from telegram import Bot
from flask import Flask
from datetime import datetime

# === Configuración de entorno ===
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("TELEGRAM_CHAT_ID")

if CHAT_ID_ENV is None:
    raise ValueError("❌ La variable de entorno TELEGRAM_CHAT_ID no está configurada")
CHAT_ID = int(CHAT_ID_ENV)

if not API_TOKEN:
    raise ValueError("❌ Falta la variable de entorno TELEGRAM_TOKEN")

bot = Bot(token=API_TOKEN)
print("✅ Configuración correcta de variables de entorno.")
print("🔄 Usando API pública con fallback (Kraken → Coinbase → KuCoin).")

# === Función de datos con fallback ===
def obtener_datos(crypto, timeframe="1h", limit=200):
    exchanges = [
        ("Kraken", ccxt.kraken({'enableRateLimit': True})),
        ("Coinbase", ccxt.coinbaseexchange({'enableRateLimit': True})),
        ("KuCoin", ccxt.kucoin({'enableRateLimit': True}))
    ]
    for nombre, exchange in exchanges:
        try:
            print(f"🔄 Obteniendo {crypto} ({timeframe}) desde {nombre}...")
            ohlc = exchange.fetch_ohlcv(crypto, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlc, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            print(f"✅ Datos obtenidos desde {nombre}")
            return df
        except Exception as e:
            print(f"⚠️ Falló {nombre}: {e}")
    return pd.DataFrame()

# === Cálculo de indicadores ===
def calcular_indicadores(df):
    if df.empty:
        return df, None, None
    df["EMA20"] = EMAIndicator(df["close"], window=20).ema_indicator()
    df["EMA50"] = EMAIndicator(df["close"], window=50).ema_indicator()
    df["RSI"] = RSIIndicator(df["close"], window=14).rsi()
    macd = MACD(df["close"])
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    soporte = df["low"].min()
    resistencia = df["high"].max()
    return df, soporte, resistencia

# === Generar gráficos ===
def generar_grafico(df, crypto):
    df = df.tail(50)
    archivo = f"{crypto.replace('/', '')}_grafico.png"
    estilo = mpf.make_mpf_style(base_mpf_style='yahoo', rc={'font.size': 8})
    addplots = [
        mpf.make_addplot(df["EMA20"], color="blue"),
        mpf.make_addplot(df["EMA50"], color="orange")
    ]
    mpf.plot(df, type="candle", addplot=addplots, style=estilo,
             title=f"{crypto}", ylabel="Precio", savefig=archivo, tight_layout=True)
    return archivo

# === Envío de alertas ===
async def enviar_alerta(crypto, timeframe, df, ultimo, soporte, resistencia):
    margen = 0.02  # 2%
    rango_soporte = soporte * (1 + margen)
    rango_resistencia = resistencia * (1 - margen)

    tocar_soporte = ultimo <= rango_soporte
    tocar_resistencia = ultimo >= rango_resistencia

    if tocar_soporte or tocar_resistencia:
        tipo = "🟢 TOCÓ SOPORTE" if tocar_soporte else "🔴 TOCÓ RESISTENCIA"
        archivo = generar_grafico(df, crypto)
        texto = (
            f"{tipo}\n"
            f"⏱ {timeframe}\n"
            f"📊 {crypto}\n"
            f"💰 Precio: {ultimo:.2f}\n"
            f"💎 Soporte: {soporte:.2f}\n"
            f"📈 Resistencia: {resistencia:.2f}"
        )

        # Guardar registro CSV
        fecha = datetime.now().strftime("%Y-%m-%d")
        archivo_csv = f"alertas_{fecha}.csv"
        registro = pd.DataFrame([{
            "fecha": datetime.now(),
            "crypto": crypto,
            "timeframe": timeframe,
            "precio": ultimo,
            "soporte": soporte,
            "resistencia": resistencia,
            "tipo": tipo
        }])
        registro.to_csv(archivo_csv, mode='a', header=not os.path.exists(archivo_csv), index=False)

        try:
            async with bot:
                await bot.send_photo(chat_id=CHAT_ID, photo=open(archivo, 'rb'), caption=texto)
        except Exception as e:
            print(f"❌ Error al enviar alerta: {e}")

# === Ciclo principal ===
async def revisar_cryptos():
    cryptos = [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
        "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
        "LTC/USDT", "LINK/USDT"
    ]
    timeframes = ["1h", "4h", "1d"]

    for crypto in cryptos:
        for tf in timeframes:
            try:
                df = obtener_datos(crypto, timeframe=tf)
                df, soporte, resistencia = calcular_indicadores(df)
                if df.empty: 
                    continue
                ultimo = float(df["close"].iloc[-1])
                await enviar_alerta(crypto, tf, df, ultimo, soporte, resistencia)
            except Exception as e:
                print(f"❌ Error con {crypto} ({tf}): {e}")

# === Heartbeat ===
async def heartbeat():
    while True:
        print("💓 Bot activo...")
        await asyncio.sleep(60)

# === Main ===
async def main():
    async with bot:
        await bot.send_message(chat_id=CHAT_ID, text="✅ Bot de soportes/resistencias iniciado correctamente.")
        asyncio.create_task(heartbeat())
        while True:
            await revisar_cryptos()
            await asyncio.sleep(900)

# === Servidor Flask ===
app = Flask(__name__)
@app.route('/')
def home():
    return "🤖 Bot activo monitoreando soportes y resistencias (1h, 4h, 1d)."

def iniciar_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=iniciar_flask).start()
    asyncio.run(main())


