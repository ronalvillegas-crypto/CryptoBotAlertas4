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

# Pares principales a monitorear
PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
         "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"]

# Timeframes a analizar
TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}

# Margen para alertas (2%)
ALERTA_MARGEN = 0.02


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
    """Obtiene datos OHLC desde Kraken."""
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
    """Calcula niveles de soporte y resistencia."""
    maximo = df["high"].max()
    minimo = df["low"].min()
    rango = maximo - minimo
    resistencia = maximo
    soporte = minimo
    return soporte, resistencia, rango


def analizar_moneda(par):
    """Analiza cada par y envía alertas si toca soporte o resistencia."""
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        try:
            df = obtener_datos_kraken(par)
            if df is None or len(df) == 0:
                continue

            soporte, resistencia, rango = calcular_niveles(df)
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

        except Exception as e:
            print(f"❌ Error analizando {par} en {tf}: {e}")
            traceback.print_exc()
            continue


def generar_resumen_diario():
    """Envía un mensaje de resumen diario al canal."""
    ahora = datetime.now(timezone.utc)
    enviar_telegram(f"🗓️ <b>Resumen diario:</b> análisis automático completado a las {ahora.strftime('%H:%M UTC')}.")


def notificar_reinicio():
    """Envía una alerta al iniciar o reiniciar el bot."""
    ahora = datetime.now(timezone.utc)
    enviar_telegram(
        f"⚙️ <b>El bot se ha reiniciado y está operativo nuevamente ✅</b>\n"
        f"⏰ Hora de reinicio: {ahora.strftime('%Y-%m-%d %H:%M UTC')}"
    )


# === LOOP PRINCIPAL ===

if __name__ == "__main__":
    # Notificación de arranque
    notificar_reinicio()
    resumen_enviado_hoy = False

    while True:
        try:
            ahora_utc = datetime.now(timezone.utc)
            hora_actual = ahora_utc.strftime("%H:%M")  # Hora UTC
            hora_resumen = "10:30"  # Equivale a 6:30 AM (UTC-4)

            # Enviar resumen diario a la hora definida
            if hora_actual == hora_resumen and not resumen_enviado_hoy:
                generar_resumen_diario()
                resumen_enviado_hoy = True
                print("📤 Resumen diario enviado correctamente.")

            # Reiniciar bandera a medianoche UTC
            if ahora_utc.strftime("%H:%M") == "00:00":
                resumen_enviado_hoy = False

            # Analizar monedas
            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {ahora_utc.strftime('%H:%M:%S')} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)

