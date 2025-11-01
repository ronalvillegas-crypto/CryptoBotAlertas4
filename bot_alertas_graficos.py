import os
import requests
import pandas as pd
import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import telegram
from telegram.error import TimedOut

# ==============================
# ⚙️ CONFIGURACIÓN GENERAL
# ==============================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telegram.Bot(token=TOKEN)

PARES = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"]
INTERVALO = 15  # minutos entre actualizaciones
TOLERANCIA = 0.01  # 1%
MOVIMIENTO_MINIMO = 0.01  # 1%

# ==============================
# 🧩 FUNCIONES DE DATOS
# ==============================

def obtener_datos(par):
    """Obtiene datos desde Kraken con fallback a Coinbase o KuCoin."""
    base, quote = par.split("/")
    dfs = []

    # Kraken
    try:
        url = f"https://api.kraken.com/0/public/OHLC?pair={base}{quote}&interval={INTERVALO}"
        r = requests.get(url, timeout=10)
        data = r.json()["result"]
        key = list(data.keys())[0]
        df = pd.DataFrame(data[key], columns=["time", "open", "high", "low", "close", "v", "v2"])
        df["close"] = df["close"].astype(float)
        dfs.append(df)
        print(f"📊 Datos de {par} obtenidos desde Kraken")
    except Exception as e:
        print(f"⚠️ Kraken falló para {par}: {e}")

    # Coinbase (fallback)
    if not dfs:
        try:
            url = f"https://api.exchange.coinbase.com/products/{base}-{quote}/candles?granularity={INTERVALO*60}"
            r = requests.get(url, timeout=10)
            df = pd.DataFrame(r.json(), columns=["time", "low", "high", "open", "close", "volume"])
            df["close"] = df["close"].astype(float)
            dfs.append(df)
            print(f"📊 Datos de {par} obtenidos desde Coinbase")
        except Exception as e:
            print(f"⚠️ Coinbase falló para {par}: {e}")

    # KuCoin (fallback final)
    if not dfs:
        try:
            url = f"https://api.kucoin.com/api/v1/market/candles?type={INTERVALO}min&symbol={base}-{quote}"
            r = requests.get(url, timeout=10)
            df = pd.DataFrame(r.json()["data"], columns=["time", "open", "close", "high", "low", "volume", "turnover"])
            df["close"] = df["close"].astype(float)
            dfs.append(df)
            print(f"📊 Datos de {par} obtenidos desde KuCoin")
        except Exception as e:
            print(f"⚠️ KuCoin falló para {par}: {e}")

    if not dfs:
        return None
    return dfs[0]


# ==============================
# 📊 ANÁLISIS TÉCNICO SIMPLE
# ==============================
def calcular_soportes_resistencias(df):
    precios = df["close"].tail(100).values
    soporte = np.min(precios)
    resistencia = np.max(precios)
    return soporte, resistencia


# ==============================
# 🚨 DETECCIÓN DE ALERTAS
# ==============================
def verificar_alertas(par, df):
    precio_actual = df["close"].iloc[-1]
    soporte, resistencia = calcular_soportes_resistencias(df)

    alerta = None
    motivo = ""

    # Cercanía a soporte o resistencia
    if abs(precio_actual - soporte) / soporte <= TOLERANCIA:
        alerta = "🟢 Cerca del soporte"
        motivo = f"Precio actual {precio_actual:.2f} está a {100*TOLERANCIA:.1f}% del soporte ({soporte:.2f})"
    elif abs(precio_actual - resistencia) / resistencia <= TOLERANCIA:
        alerta = "🔴 Cerca de la resistencia"
        motivo = f"Precio actual {precio_actual:.2f} está a {100*TOLERANCIA:.1f}% de la resistencia ({resistencia:.2f})"

    # Movimiento brusco en los últimos 15 minutos
    if len(df) >= 2:
        cambio = (precio_actual - df["close"].iloc[-2]) / df["close"].iloc[-2]
        if abs(cambio) >= MOVIMIENTO_MINIMO:
            tendencia = "⬆️ Subida fuerte" if cambio > 0 else "⬇️ Caída fuerte"
            alerta = tendencia
            motivo = f"Movimiento de {cambio*100:.2f}% en los últimos 15 minutos"

    return alerta, motivo, precio_actual, soporte, resistencia


# ==============================
# 💬 ENVÍO DE MENSAJE TELEGRAM
# ==============================
def enviar_alerta(par, alerta, motivo, precio, soporte, resistencia):
    mensaje = (
        f"🚨 *Alerta en {par}*\n"
        f"{alerta}\n"
        f"💰 Precio: `{precio:.2f}`\n"
        f"📉 Soporte: `{soporte:.2f}`\n"
        f"📈 Resistencia: `{resistencia:.2f}`\n"
        f"🕒 {motivo}\n"
    )
    try:
        bot.send_message(chat_id=CHAT_ID, text=mensaje, parse_mode="Markdown")
    except TimedOut:
        time.sleep(5)
        bot.send_message(chat_id=CHAT_ID, text=mensaje, parse_mode="Markdown")


# ==============================
# 🔁 LOOP PRINCIPAL
# ==============================
def main():
    while True:
        for par in PARES:
            print(f"🔄 Analizando {par} ...")
            df = obtener_datos(par)
            if df is None:
                continue
            alerta, motivo, precio, soporte, resistencia = verificar_alertas(par, df)
            if alerta:
                enviar_alerta(par, alerta, motivo, precio, soporte, resistencia)
        print(f"💓 Bot activo y ejecutándose... {datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S')} UTC")
        time.sleep(INTERVALO * 60)


if __name__ == "__main__":
    main()


