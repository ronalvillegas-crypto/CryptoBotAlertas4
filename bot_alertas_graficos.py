import os
import time
import requests
import pandas as pd
from datetime import datetime

# ==============================
# CONFIGURACIÓN INICIAL
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID or not TELEGRAM_TOKEN:
    raise ValueError("❌ Las variables de entorno TELEGRAM_TOKEN y TELEGRAM_CHAT_ID no están configuradas")

CRYPTOS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "DOT", "LTC", "LINK"]
PAIRS = [f"{crypto}/USDT" for crypto in CRYPTOS]

INTERVALOS = {
    "1h": 60,
    "4h": 240,
    "1d": 1440
}

# ==============================
# FUNCIONES AUXILIARES
# ==============================

def enviar_telegram(mensaje):
    """Envía un mensaje a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"⚠️ Error al enviar mensaje a Telegram: {e}")


# === OBTENCIÓN DE DATOS DESDE LOS EXCHANGES ===

def obtener_datos_kraken(par, intervalo):
    try:
        symbol = par.replace("/", "")
        url = f"https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={INTERVALOS[intervalo]}"
        r = requests.get(url, timeout=10).json()
        result_key = list(r["result"].keys())[0]
        data = pd.DataFrame(r["result"][result_key], columns=["time","open","high","low","close","v","v2"])
        data["close"] = data["close"].astype(float)
        data["high"] = data["high"].astype(float)
        data["low"] = data["low"].astype(float)
        print(f"✅ Datos obtenidos desde Kraken para {par} ({intervalo})")
        return data
    except Exception:
        return None


def obtener_datos_coinbase(par, intervalo):
    try:
        base, quote = par.split("/")
        symbol = f"{base}-{quote}"
        url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={INTERVALOS[intervalo]*60}"
        r = requests.get(url, timeout=10).json()
        df = pd.DataFrame(r, columns=["time", "low", "high", "open", "close", "volume"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        print(f"✅ Datos obtenidos desde Coinbase para {par} ({intervalo})")
        return df
    except Exception:
        return None


def obtener_datos_kucoin(par, intervalo):
    try:
        base, quote = par.split("/")
        symbol = f"{base}-{quote}"
        url = f"https://api.kucoin.com/api/v1/market/candles?type={intervalo}&symbol={symbol}"
        r = requests.get(url, timeout=10).json()
        df = pd.DataFrame(r["data"], columns=["time","open","close","high","low","volume","amount"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        print(f"✅ Datos obtenidos desde KuCoin para {par} ({intervalo})")
        return df
    except Exception:
        return None


def obtener_datos(par, intervalo):
    """Prueba Kraken → Coinbase → KuCoin"""
    data = obtener_datos_kraken(par, intervalo)
    if data is not None:
        return data
    data = obtener_datos_coinbase(par, intervalo)
    if data is not None:
        return data
    data = obtener_datos_kucoin(par, intervalo)
    if data is not None:
        return data
    print(f"❌ No se pudieron obtener datos para {par} ({intervalo})")
    return None


# === ANÁLISIS DE PRECIO ===

def calcular_niveles(df):
    maximo = df["high"].max()
    minimo = df["low"].min()
    return round(minimo, 2), round(maximo, 2)


def analizar_precio(par):
    """Analiza si el precio actual toca soporte o resistencia."""
    for intervalo in INTERVALOS.keys():
        df = obtener_datos(par, intervalo)
        if df is None or df.empty:
            continue

        soporte, resistencia = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]
        margen = 0.02  # 2%

        zona_soporte = soporte * (1 + margen)
        zona_resistencia = resistencia * (1 - margen)

        if precio_actual <= zona_soporte:
            enviar_telegram(f"🟢 <b>{par}</b> tocó el <b>soporte</b> ({intervalo}) en <b>{precio_actual:.2f}</b>.\n📉 Nivel: {soporte}")
        elif precio_actual >= zona_resistencia:
            enviar_telegram(f"🔴 <b>{par}</b> tocó la <b>resistencia</b> ({intervalo}) en <b>{precio_actual:.2f}</b>.\n📈 Nivel: {resistencia}")


# === BUCLE PRINCIPAL ===

def iniciar_bot_alertas():
    enviar_telegram("🤖 Bot de alertas iniciado en modo Background Worker ✅")
    while True:
        print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')} | Escaneando criptomonedas...")
        for par in PAIRS:
            analizar_precio(par)
            time.sleep(3)  # pausa entre criptos
        print("💤 Esperando 15 minutos para el siguiente escaneo...")
        time.sleep(900)  # 15 minutos


# ==============================
# EJECUCIÓN
# ==============================
if __name__ == "__main__":
    iniciar_bot_alertas()




