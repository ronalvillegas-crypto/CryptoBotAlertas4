import os
import time
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime, timezone

# === CONFIGURACIÓN PRINCIPAL ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"
]

TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}
ALERTA_MARGEN = 0.02  # 2%

# === FUNCIONES ===
def enviar_telegram(mensaje):
    """Envía un mensaje al canal de Telegram configurado"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Error enviando mensaje a Telegram: {e}")

def obtener_datos_kraken(par, intervalo):
    """Obtiene datos OHLC desde Kraken"""
    base, quote = par.split('/')
    url = f"https://api.kraken.com/0/public/OHLC?pair={base}{quote}&interval={intervalo}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        key = list(data["result"].keys())[0]
        df = pd.DataFrame(data["result"][key], columns=["time", "open", "high", "low", "close", "v", "v2", "v3"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        print(f"❌ Error obteniendo datos de {par}: {e}")
        return None

def calcular_niveles(df):
    """Calcula soporte y resistencia simples"""
    maximo = df["high"].max()
    minimo = df["low"].min()
    return minimo, maximo

def analizar_moneda(par):
    """Analiza una moneda en todos los timeframes"""
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        df = obtener_datos_kraken(par, minutos)
        if df is None or df.empty:
            continue

        soporte, resistencia = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]

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

# === LOOP PRINCIPAL ===
if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")

    while True:
        try:
            hora_actual = datetime.now(timezone.utc).strftime("%H:%M")
            if hora_actual == "00:00":
                enviar_telegram("⚙️ El bot se ha reiniciado y está operativo nuevamente ✅\n⏰ Hora de reinicio: "
                                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)


