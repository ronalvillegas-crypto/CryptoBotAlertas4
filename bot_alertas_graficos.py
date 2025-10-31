import os
import time
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime

# === CONFIGURACIÓN PRINCIPAL ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Pares principales a monitorear
PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
         "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"]

# Timeframes a analizar
TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}

# Margen para alertas (2%)
ALERTA_MARGEN = 0.02

# === FUNCIONES AUXILIARES ===

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos_kraken(par):
    base, quote = par.split('/')
    symbol = base + quote
    url = f"https://api.kraken.com/0/public/OHLC?pair={base}{quote}&interval=60"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        key = list(data["result"].keys())[0]
        df = pd.DataFrame(data["result"][key],
                          columns=["time", "open", "high", "low", "close", "v", "v2", "v3"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        print(f"Error obteniendo datos de {par} desde Kraken: {e}")
        return None

def calcular_niveles(df):
    maximo = df["high"].max()
    minimo = df["low"].min()
    rango = maximo - minimo
    resistencia = maximo
    soporte = minimo
    return soporte, resistencia, rango

def analizar_moneda(par):
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        try:
            df = obtener_datos_kraken(par)
            if df is None or len(df) == 0:
                continue

            soporte, resistencia, rango = calcular_niveles(df)
            precio_actual = df["close"].iloc[-1]

            # Chequear toque de niveles
            distancia_sup = abs(precio_actual - resistencia) / resistencia
            distancia_inf = abs(precio_actual - soporte) / soporte

            if distancia_sup <= ALERTA_MARGEN:
                enviar_telegram(
                    f"🚀 <b>{par}</b> está tocando resistencia ({tf}): "
                    f"<b>{resistencia:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
                )

            if distancia_inf <= ALERTA_MARGEN:
                enviar_telegram(
                    f"⚡ <b>{par}</b> está tocando soporte ({tf}): "
                    f"<b>{soporte:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
                )

        except Exception as e:
            print(f"❌ Error analizando {par} en {tf}: {e}")
            traceback.print_exc()
            continue

# === LOOP PRINCIPAL ===

if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")

    while True:
        try:
            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)  # pequeño delay entre monedas

            print(f"💓 Bot activo y ejecutándose... {datetime.now().strftime('%H:%M:%S')}")
            time.sleep(300)  # Espera 5 minutos antes del próximo ciclo

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)





