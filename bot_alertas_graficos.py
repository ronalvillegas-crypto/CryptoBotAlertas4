import os
import time
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime, timedelta, timezone

# === CONFIGURACIÓN PRINCIPAL ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Pares principales a monitorear
PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
         "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"]

# Timeframes a analizar
TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}

# Margen para alertas individuales (2%)
ALERTA_MARGEN = 0.02

# Margen para incluir en reporte diario (3%)
REPORTE_MARGEN = 0.03

# Hora local de reporte diario (6:30 AM Colombia/Venezuela)
REPORTE_HORA = "06:30"

# === FUNCIONES AUXILIARES ===

def enviar_telegram(mensaje):
    """Envía mensajes al canal de Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos_kraken(par):
    """Descarga velas desde Kraken."""
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
        print(f"Error obteniendo datos de {par}: {e}")
        return None

def calcular_niveles(df):
    """Obtiene soporte, resistencia y rango de precios."""
    maximo = df["high"].max()
    minimo = df["low"].min()
    rango = maximo - minimo
    return minimo, maximo, rango

def analizar_moneda(par):
    """Analiza un par en diferentes timeframes."""
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        try:
            df = obtener_datos_kraken(par)
            if df is None or len(df) == 0:
                continue

            soporte, resistencia, _ = calcular_niveles(df)
            precio_actual = df["close"].iloc[-1]

            distancia_sup = abs(precio_actual - resistencia) / resistencia
            distancia_inf = abs(precio_actual - soporte) / soporte

            if distancia_sup <= ALERTA_MARGEN:
                enviar_telegram(
                    f"🚀 <b>{par}</b> tocando <b>resistencia</b> ({tf}): "
                    f"<b>{resistencia:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
                )

            if distancia_inf <= ALERTA_MARGEN:
                enviar_telegram(
                    f"⚡ <b>{par}</b> tocando <b>soporte</b> ({tf}): "
                    f"<b>{soporte:.2f}</b>\n💰 Precio actual: {precio_actual:.2f}"
                )

        except Exception as e:
            print(f"❌ Error analizando {par}: {e}")
            traceback.print_exc()

def generar_reporte_diario():
    """Genera un reporte resumen con monedas cercanas a soporte o resistencia."""
    cercanos_resistencia = []
    cercanos_soporte = []

    for par in PAIRS:
        df = obtener_datos_kraken(par)
        if df is None or len(df) == 0:
            continue

        soporte, resistencia, _ = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]

        dist_res = abs(precio_actual - resistencia) / resistencia
        dist_sup = abs(precio_actual - soporte) / soporte

        if dist_res <= REPORTE_MARGEN:
            cercanos_resistencia.append((par, dist_res * 100))
        if dist_sup <= REPORTE_MARGEN:
            cercanos_soporte.append((par, dist_sup * 100))

    fecha = datetime.now(timezone.utc) - timedelta(hours=5)
    fecha_local = fecha.strftime("%Y-%m-%d %H:%M")

    mensaje = f"📊 <b>Reporte Diario - {fecha_local}</b>\n"

    if cercanos_resistencia:
        mensaje += "\n🚀 <b>Cerca de resistencia:</b>\n"
        for par, dist in cercanos_resistencia:
            mensaje += f"• {par} → {dist:.2f}% de la resistencia\n"
    else:
        mensaje += "\n🚀 Ninguna moneda cerca de resistencia.\n"

    if cercanos_soporte:
        mensaje += "\n⚡ <b>Cerca de soporte:</b>\n"
        for par, dist in cercanos_soporte:
            mensaje += f"• {par} → {dist:.2f}% del soporte\n"
    else:
        mensaje += "\n⚡ Ninguna moneda cerca de soporte.\n"

    enviar_telegram(mensaje)

# === LOOP PRINCIPAL ===

if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")

    while True:
        try:
            hora_local = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%H:%M")

            # Enviar reporte diario a las 6:30 am (hora local)
            if hora_local == REPORTE_HORA:
                generar_reporte_diario()
                time.sleep(60)  # evitar que se repita en el mismo minuto

            # Ciclo normal de análisis
            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {datetime.utcnow().strftime('%H:%M:%S')} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)

