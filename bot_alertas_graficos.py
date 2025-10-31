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
    """Envía un mensaje al canal o chat de Telegram configurado."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos_kraken(par):
    """Obtiene velas OHLC desde Kraken."""
    base, quote = par.split('/')
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
    """Calcula soporte, resistencia y rango de precios."""
    maximo = df["high"].max()
    minimo = df["low"].min()
    rango = maximo - minimo
    return minimo, maximo, rango

def analizar_moneda(par):
    """Analiza una moneda en varios marcos temporales."""
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        try:
            df = obtener_datos_kraken(par)
            if df is None or len(df) == 0:
                continue

            soporte, resistencia, rango = calcular_niveles(df)
            precio_actual = df["close"].iloc[-1]

            # Distancias a niveles
            distancia_sup = abs(precio_actual - resistencia) / resistencia
            distancia_inf = abs(precio_actual - soporte) / soporte

            # Alertas
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

def generar_resumen_diario():
    """Envía un resumen de precios actual al chat de Telegram."""
    try:
        resumen = "📊 <b>Resumen Diario Cripto</b> 📊\n\n"
        for par in PAIRS:
            df = obtener_datos_kraken(par)
            if df is None or len(df) == 0:
                continue
            precio = df["close"].iloc[-1]
            cambio = ((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]) * 100
            resumen += f"{par}: <b>{precio:.2f}</b> USD ({cambio:+.2f}%)\n"

        enviar_telegram(resumen)
    except Exception as e:
        print(f"⚠️ Error generando resumen diario: {e}")

# === LOOP PRINCIPAL ===

if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")
    resumen_enviado_hoy = False

    while True:
        try:
            hora_actual = datetime.utcnow().strftime("%H:%M")  # Hora del servidor (UTC)
            hora_resumen = "10:30"  # Equivale a 6:30 AM hora local (UTC-4)

            # Enviar resumen diario
            if hora_actual == hora_resumen and not resumen_enviado_hoy:
                generar_resumen_diario()
                resumen_enviado_hoy = True
                print("📤 Resumen diario enviado correctamente.")

            # Reinicia bandera al cambiar de día
            if datetime.utcnow().strftime("%H:%M") == "00:00":
                resumen_enviado_hoy = False

            # Análisis de monedas
            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {datetime.utcnow().strftime('%H:%M:%S')} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)

