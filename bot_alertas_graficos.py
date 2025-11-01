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
ALERTA_MARGEN = 0.003  # 0.3%

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
        df = pd.DataFrame(data["result"][key])
        # Ajuste dinámico de columnas
        expected_cols = ["time", "open", "high", "low", "close", "v", "v2", "v3"]
        if df.shape[1] < len(expected_cols):
            df.columns = expected_cols[:df.shape[1]]
        else:
            df.columns = expected_cols
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        print(f"⚠️ Kraken falló para {par}: {e}")
        return None

def obtener_datos_coinbase(par, intervalo):
    """Fallback a Coinbase (simplificado, último precio)"""
    symbol = par.replace("/", "-")
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={intervalo*60}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        df = pd.DataFrame(data, columns=["time", "low", "high", "open", "close", "volume"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        print(f"⚠️ Coinbase falló para {par}: {e}")
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
        fuente = "Kraken"
        if df is None or df.empty:
            df = obtener_datos_coinbase(par, minutos)
            fuente = "Coinbase"
        if df is None or df.empty:
            print(f"❌ No hay datos para {par}")
            continue

        print(f"📊 Datos de {par} obtenidos desde {fuente}")
        soporte, resistencia = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]

        distancia_sup = abs(precio_actual - resistencia) / resistencia
        distancia_inf = abs(precio_actual - soporte) / soporte

        if distancia_sup <= ALERTA_MARGEN:
            enviar_telegram(
                f"🚀 <b>{par}</b> tocando resistencia ({tf}): "
                f"<b>{resistencia:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
            )
        if distancia_inf <= ALERTA_MARGEN:
            enviar_telegram(
                f"⚡ <b>{par}</b> tocando soporte ({tf}): "
                f"<b>{soporte:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
            )

# === LOOP PRINCIPAL ===
if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")

    while True:
        try:
            hora_actual = datetime.now(timezone.utc).strftime("%H:%M")
            if hora_actual == "00:00":
                enviar_telegram(
                    f"⚙️ El bot se ha reiniciado y está operativo ✅\n⏰ Hora de reinicio: "
                    f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                )

            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)  # pequeño delay entre monedas

            print(f"💓 Bot activo y ejecutándose... {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
            time.sleep(300)  # espera 5 minutos antes del próximo ciclo

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)



