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
ULTIMO_RESUMEN = None  # Control de envío diario

# === FUNCIONES ===
def enviar_telegram(mensaje):
    """Envía un mensaje al canal de Telegram configurado"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Error enviando mensaje a Telegram: {e}")

def obtener_datos(par, intervalo):
    """Obtiene datos OHLC desde Kraken con fallback a Coinbase o KuCoin"""
    base, quote = par.split('/')

    # === Kraken ===
    url_kraken = f"https://api.kraken.com/0/public/OHLC?pair={base}{quote}&interval={intervalo}"
    try:
        r = requests.get(url_kraken, timeout=10)
        data = r.json()
        key = list(data["result"].keys())[0]
        df = pd.DataFrame(data["result"][key], columns=["time", "open", "high", "low", "close", "v", "v2", "v3"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        print(f"📊 Datos obtenidos de Kraken para {par} ({intervalo}m)")
        return df
    except Exception:
        print(f"⚠️ Kraken falló para {par}, intentando Coinbase...")
        enviar_telegram(f"⚙️ Kraken falló para <b>{par}</b>, intentando datos de <b>Coinbase</b>...")

    # === Coinbase ===
    try:
        url_cb = f"https://api.exchange.coinbase.com/products/{base}-{quote}/candles?granularity={intervalo*60}"
        r = requests.get(url_cb, timeout=10)
        data = r.json()
        df = pd.DataFrame(data, columns=["time", "low", "high", "open", "close", "volume"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        print(f"📊 Datos obtenidos de Coinbase para {par}")
        enviar_telegram(f"✅ Usando datos de <b>Coinbase</b> para <b>{par}</b>.")
        return df
    except Exception:
        print(f"⚠️ Coinbase falló para {par}, intentando KuCoin...")
        enviar_telegram(f"⚙️ Coinbase falló para <b>{par}</b>, intentando datos de <b>KuCoin</b>...")

    # === KuCoin ===
    try:
        url_kucoin = f"https://api.kucoin.com/api/v1/market/candles?type={intervalo}min&symbol={base}-{quote}"
        r = requests.get(url_kucoin, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["data"], columns=["time", "open", "close", "high", "low", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        print(f"📊 Datos obtenidos de KuCoin para {par}")
        enviar_telegram(f"✅ Usando datos de <b>KuCoin</b> para <b>{par}</b>.")
        return df
    except Exception as e:
        print(f"❌ No se pudieron obtener datos para {par}: {e}")
        enviar_telegram(f"❌ No se pudieron obtener datos de <b>{par}</b> en Kraken, Coinbase ni KuCoin.")
        return None

def calcular_niveles(df):
    """Calcula soporte y resistencia simples"""
    maximo = df["high"].max()
    minimo = df["low"].min()
    return minimo, maximo

def analizar_moneda(par):
    """Analiza una moneda en todos los timeframes"""
    print(f"\n🔄 Analizando {par} ...")
    resultados = {}
    for tf, minutos in TIMEFRAMES.items():
        df = obtener_datos(par, minutos)
        if df is None or df.empty:
            print(f"⚠️ Sin datos válidos para {par} en {tf}")
            continue

        soporte, resistencia = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]

        distancia_sup = abs(precio_actual - resistencia) / resistencia
        distancia_inf = abs(precio_actual - soporte) / soporte

        print(f"🧾 {par} [{tf}] → Precio: {precio_actual:.2f}, Soporte: {soporte:.2f}, Resistencia: {resistencia:.2f}")

        if distancia_sup <= ALERTA_MARGEN:
            estado = "🔴 Cerca de resistencia"
            enviar_telegram(
                f"🚀 <b>{par}</b> está cerca de su <b>resistencia</b> ({tf})\n"
                f"💰 Precio actual: <b>{precio_actual:.2f}</b>\n"
                f"📈 Nivel de resistencia: <b>{resistencia:.2f}</b>"
            )
        elif distancia_inf <= ALERTA_MARGEN:
            estado = "🟢 Cerca de soporte"
            enviar_telegram(
                f"⚡ <b>{par}</b> está cerca de su <b>soporte</b> ({tf})\n"
                f"💰 Precio actual: <b>{precio_actual:.2f}</b>\n"
                f"📉 Nivel de soporte: <b>{soporte:.2f}</b>"
            )
        else:
            estado = "⚪ Zona neutral"

        resultados[tf] = {
            "precio": precio_actual,
            "soporte": soporte,
            "resistencia": resistencia,
            "estado": estado
        }
    return resultados

def resumen_diario():
    """Genera y envía un resumen diario con todos los pares"""
    resumen = f"📅 <b>Resumen diario – {datetime.now(timezone.utc).strftime('%Y-%m-%d')}</b>\n\n"
    for par in PAIRS:
        try:
            df = obtener_datos(par, 240)  # 4h
            if df is None or df.empty:
                continue

            soporte, resistencia = calcular_niveles(df)
            precio_actual = df["close"].iloc[-1]

            distancia_sup = abs(precio_actual - resistencia) / resistencia
            distancia_inf = abs(precio_actual - soporte) / soporte

            if distancia_sup <= ALERTA_MARGEN:
                estado = f"🔴 Cerca de resistencia ({resistencia:.2f})"
            elif distancia_inf <= ALERTA_MARGEN:
                estado = f"🟢 Cerca de soporte ({soporte:.2f})"
            else:
                estado = "⚪ Zona neutral"

            resumen += f"{par} → Precio: {precio_actual:.2f} | {estado}\n"

        except Exception as e:
            resumen += f"{par} → ⚠️ Error al obtener datos ({e})\n"

    enviar_telegram(resumen.strip())

# === LOOP PRINCIPAL ===
if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas cripto iniciado correctamente ✅")

    while True:
        try:
            hora_actual = datetime.now(timezone.utc)
            hora_str = hora_actual.strftime("%H:%M")

            # Enviar resumen diario una sola vez a medianoche UTC
            if hora_actual.hour == 0 and (ULTIMO_RESUMEN is None or ULTIMO_RESUMEN != hora_actual.date()):
                resumen_diario()
                ULTIMO_RESUMEN = hora_actual.date()

            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {hora_str} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)

