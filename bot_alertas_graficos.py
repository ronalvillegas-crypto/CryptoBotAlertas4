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

# Criptomonedas principales
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
    """Envía mensaje a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"⚠️ Error al enviar mensaje Telegram: {e}")


def obtener_datos_kraken(par, intervalo):
    """Obtiene datos OHLC desde Kraken."""
    try:
        symbol = par.replace("/", "")
        url = f"https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={INTERVALOS[intervalo]}"
        r = requests.get(url, timeout=10).json()
        result_key = list(r["result"].keys())[0]
        data = pd.DataFrame(r["result"][result_key], columns=["time","open","high","low","close","v","v2"])
        data["close"] = data["close"].astype(float)
        data["high"] = data["high"].astype(float)
        data["low"] = data["low"].astype(float)
        return data
    except Exception:
        return None


def calcular_niveles(df):
    """Calcula niveles de soporte y resistencia."""
    maximo = df["high"].max()
    minimo = df["low"].min()
    return round(minimo, 2), round(maximo, 2)


def analizar_precio(par):
    """Analiza el precio actual contra soportes y resistencias."""
    for intervalo in INTERVALOS.keys():
        df = obtener_datos_kraken(par, intervalo)
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


def iniciar_bot_alertas():
    """Bucle principal del bot."""
    enviar_telegram("🤖 Bot de alertas iniciado correctamente en Render ✅")
    while True:
        print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')} | Escaneando mercados...")
        for par in PAIRS:
            analizar_precio(par)
            time.sleep(2)  # pausa corta entre pares
        print("💓 Ciclo completado, esperando 15 minutos...")
        time.sleep(900)  # espera 15 minutos antes de volver a analizar


# ==============================
# EJECUCIÓN
# ==============================
if __name__ == "__main__":
    iniciar_bot_alertas()



