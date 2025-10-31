import os
import time
import requests
import pandas as pd
import traceback
from datetime import datetime, timezone

# === CONFIGURACIÓN PRINCIPAL ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ Falta TELEGRAM_TOKEN en variables de entorno.")
if not CHAT_ID_RAW:
    raise ValueError("❌ Falta CHAT_ID / TELEGRAM_CHAT_ID en variables de entorno.")

try:
    CHAT_ID = int(CHAT_ID_RAW)
except Exception:
    raise ValueError("❌ TELEGRAM_CHAT_ID debe ser un número (chat id).")

PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT"
]

TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}
ALERTA_MARGEN = 0.02  # 2%

# === UTILIDADES ===
def enviar_telegram(mensaje):
    """Envía un mensaje a Telegram con manejo de errores."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Telegram API respondió {r.status_code}: {r.text}")
    except Exception as e:
        print(f"⚠️ Error enviando mensaje a Telegram: {e}")

# === OBTENCIÓN DE DATOS DESDE EXCHANGES ===
def obtener_datos_kraken(par, intervalo):
    base, quote = par.split('/')
    url = f"https://api.kraken.com/0/public/OHLC?pair={base}{quote}&interval={intervalo}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if "error" in data and data["error"]:
            return None
        key = list(data["result"].keys())[0]
        df = pd.DataFrame(data["result"][key], columns=["time", "open", "high", "low", "close", "v", "v2", "v3"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception:
        return None

def obtener_datos_coinbase(par, intervalo):
    base, quote = par.split('/')
    symbol = f"{base}-{quote}"
    mapping = {60: 60, 240: 3600, 1440: 86400}
    granularity = mapping.get(intervalo, 3600)
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={granularity}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        df = pd.DataFrame(data, columns=["time", "low", "high", "open", "close", "volume"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception:
        return None

def obtener_datos_kucoin(par, intervalo):
    base, quote = par.split('/')
    symbol = f"{base}-{quote}"
    mapping = {60: "1hour", 240: "4hour", 1440: "1day"}
    tf = mapping.get(intervalo, "1hour")
    url = f"https://api.kucoin.com/api/v1/market/candles?type={tf}&symbol={symbol}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        payload = r.json()
        data = payload.get("data")
        if not data:
            return None
        df = pd.DataFrame(data, columns=["time", "open", "close", "high", "low", "volume", "v2"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception:
        return None

def obtener_datos(par, intervalo):
    """Usa Kraken → Coinbase → KuCoin en orden de prioridad. Retorna (df, fuente)"""
    for fuente, fn in [
        ("Kraken", obtener_datos_kraken),
        ("Coinbase", obtener_datos_coinbase),
        ("KuCoin", obtener_datos_kucoin)
    ]:
        df = fn(par, intervalo)
        if df is not None and not df.empty:
            print(f"📊 Datos de {par} obtenidos desde {fuente}")
            return df, fuente
    print(f"⚠️ No se pudieron obtener datos para {par} desde ninguna fuente.")
    return None, None

# === CÁLCULOS ===
def calcular_niveles(df):
    try:
        soporte = df["low"].min()
        resistencia = df["high"].max()
        return soporte, resistencia
    except Exception:
        return None, None

def safe_ratio(a, b):
    try:
        if b == 0 or b is None:
            return 999
        return abs(a - b) / b
    except Exception:
        return 999

# === LÓGICA DE ALERTAS ===
def analizar_moneda(par):
    print(f"🔄 Analizando {par} ...")
    for tf, minutos in TIMEFRAMES.items():
        df, fuente = obtener_datos(par, minutos)
        if df is None or df.empty or fuente is None:
            continue
        soporte, resistencia = calcular_niveles(df)
        if soporte is None or resistencia is None:
            continue
        precio = df["close"].iloc[-1]
        if safe_ratio(precio, resistencia) <= ALERTA_MARGEN:
            enviar_telegram(
                f"🚀 <b>{par}</b> tocando resistencia ({tf})\n"
                f"📊 <b>Fuente:</b> {fuente}\n"
                f"💹 Resistencia: <b>{resistencia:.2f}</b>\n"
                f"💰 Precio actual: {precio:.2f}"
            )
        if safe_ratio(precio, soporte) <= ALERTA_MARGEN:
            enviar_telegram(
                f"⚡ <b>{par}</b> tocando soporte ({tf})\n"
                f"📊 <b>Fuente:</b> {fuente}\n"
                f"💹 Soporte: <b>{soporte:.2f}</b>\n"
                f"💰 Precio actual: {precio:.2f}"
            )

# === LOOP PRINCIPAL ===
if __name__ == "__main__":
    enviar_telegram("🤖 Bot iniciado con fallback activo (Kraken → Coinbase → KuCoin) ✅")

    while True:
        try:
            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)
            print(f"💓 Bot activo y ejecutándose... {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
            time.sleep(300)
        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)


