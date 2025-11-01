import os
import time
import requests
import pandas as pd
import traceback
from datetime import datetime, timezone, timedelta
from threading import Thread

# === CONFIGURACIÓN PRINCIPAL ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
    "LTC/USDT", "LINK/USDT"
]

TIMEFRAMES = {"1h": 60, "4h": 240, "1d": 1440}
ALERTA_MARGEN = 0.003   # 0.3 %
RESET_MARGEN = 0.01     # 1 %
VELAS_RECIENTES = 50

# --- Control de alertas y fallos ---
alertas_enviadas = {}
fallos_pares = {}
pares_pausados = {}
ultima_fecha_reporte = None
ultimo_mensaje_id = None

# === FUNCIONES AUXILIARES ===
def enviar_telegram(mensaje):
    """Envía mensaje al canal configurado en Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Error enviando mensaje a Telegram: {e}")

def obtener_usdt_usd():
    """Obtiene el precio actual USDT/USD (≈ 1) para ajustar conversiones."""
    try:
        r = requests.get("https://api.kraken.com/0/public/Ticker?pair=USDTUSD", timeout=10)
        data = r.json()
        precio = float(list(data["result"].values())[0]["c"][0])
        return precio
    except Exception:
        return 1.0  # fallback

USDT_USD = obtener_usdt_usd()

# === FUENTES DE DATOS ===
def obtener_datos_kraken(par, intervalo):
    base, quote = par.split('/')
    symbol = f"{base}{quote}"
    url = f"https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={intervalo}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if "result" not in data or not data["result"]:
            return None
        key = list(data["result"].keys())[0]
        df = pd.DataFrame(data["result"][key], columns=["time","open","high","low","close","v","v2","v3"])
        df[["close","high","low"]] = df[["close","high","low"]].astype(float)
        return df
    except Exception:
        return None

def obtener_datos_coinbase(par, intervalo):
    """Coinbase trabaja en USD, se convierte a USDT automáticamente."""
    base, quote = par.split('/')
    granularity = intervalo * 60
    url = f"https://api.exchange.coinbase.com/products/{base}-USD/candles?granularity={granularity}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        df = pd.DataFrame(data, columns=["time","low","high","open","close","volume"])
        df[["close","high","low"]] = df[["close","high","low"]].astype(float)
        df[["close","high","low"]] = df[["close","high","low"]] / USDT_USD
        return df
    except Exception:
        return None

def obtener_datos_kucoin(par, intervalo):
    """KuCoin devuelve datos en USDT directamente."""
    base, quote = par.split('/')
    ku_interval = {60: "1hour", 240: "4hour", 1440: "1day"}.get(intervalo, "1hour")
    url = f"https://api.kucoin.com/api/v1/market/candles?type={ku_interval}&symbol={base}-{quote}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json().get("data", [])
        if not data:
            return None
        df = pd.DataFrame(data, columns=["time","open","close","high","low","volume","v2"])
        df[["close","high","low"]] = df[["close","high","low"]].astype(float)
        return df
    except Exception:
        return None

def obtener_datos(par, intervalo):
    """Intenta Kraken → Coinbase → KuCoin"""
    for fn in [obtener_datos_kraken, obtener_datos_coinbase, obtener_datos_kucoin]:
        df = fn(par, intervalo)
        if df is not None and not df.empty:
            return df
    return None

# === ANÁLISIS ===
def calcular_niveles(df):
    """Calcula soporte y resistencia usando las últimas velas."""
    df_recent = df.tail(VELAS_RECIENTES)
    soporte = df_recent["low"].min()
    resistencia = df_recent["high"].max()
    return soporte, resistencia

def analizar_moneda(par):
    """Analiza una moneda en todos los timeframes."""
    if par in pares_pausados and datetime.now(timezone.utc) < pares_pausados[par]:
        print(f"⏸️ {par} pausado hasta {pares_pausados[par].strftime('%H:%M:%S')} UTC")
        return

    print(f"🔄 Analizando {par} ...")
    exito = False

    for tf, minutos in TIMEFRAMES.items():
        df = obtener_datos(par, minutos)
        if df is None or df.empty:
            continue

        exito = True
        soporte, resistencia = calcular_niveles(df)
        precio_actual = df["close"].iloc[-1]

        distancia_sup = (resistencia - precio_actual) / resistencia * 100
        distancia_inf = (precio_actual - soporte) / soporte * 100

        clave_res = f"{par}_{tf}_resistencia"
        clave_sup = f"{par}_{tf}_soporte"

        # --- ALERTAS ---
        if abs(distancia_sup) <= ALERTA_MARGEN * 100 and not alertas_enviadas.get(clave_res):
            enviar_telegram(f"🚀 <b>{par}</b> tocando resistencia ({tf})\n📈 {resistencia:.2f} | 💰 {precio_actual:.2f}")
            alertas_enviadas[clave_res] = True

        if abs(distancia_inf) <= ALERTA_MARGEN * 100 and not alertas_enviadas.get(clave_sup):
            enviar_telegram(f"⚡ <b>{par}</b> tocando soporte ({tf})\n📉 {soporte:.2f} | 💰 {precio_actual:.2f}")
            alertas_enviadas[clave_sup] = True

        if alertas_enviadas.get(clave_res) and abs(distancia_sup) > RESET_MARGEN * 100:
            alertas_enviadas[clave_res] = False
        if alertas_enviadas.get(clave_sup) and abs(distancia_inf) > RESET_MARGEN * 100:
            alertas_enviadas[clave_sup] = False

    # --- GESTIÓN DE FALLOS ---
    if not exito:
        fallos_pares[par] = fallos_pares.get(par, 0) + 1
        if fallos_pares[par] >= 3:
            pares_pausados[par] = datetime.now(timezone.utc) + timedelta(minutes=30)
            enviar_telegram(f"⏸️ <b>{par}</b> pausado 30 minutos por fallos consecutivos.")
            fallos_pares[par] = 0
    else:
        fallos_pares[par] = 0

def generar_reporte(tf="1h"):
    """Genera texto con soportes, resistencias y distancias en el timeframe seleccionado."""
    minutos = TIMEFRAMES.get(tf, 60)
    mensaje = f"📊 <b>REPORTE DE SOPORTES Y RESISTENCIAS ({tf})</b>\n\n"
    for par in PAIRS:
        try:
            df = obtener_datos(par, minutos)
            if df is None or df.empty:
                continue
            soporte, resistencia = calcular_niveles(df)
            precio_actual = df["close"].iloc[-1]

            distancia_sup = (resistencia - precio_actual) / resistencia * 100
            distancia_inf = (precio_actual - soporte) / soporte * 100

            mensaje += (
                f"💎 <b>{par}</b>\n"
                f"📉 Soporte: {soporte:.2f}\n"
                f"📈 Resistencia: {resistencia:.2f}\n"
                f"💰 Precio: {precio_actual:.2f}\n"
                f"📊 Distancia al soporte: {distancia_inf:.2f}%\n"
                f"📊 Distancia a resistencia: {distancia_sup:.2f}%\n\n"
            )
        except:
            continue
    return mensaje.strip()

def enviar_reporte_diario():
    """Envía el reporte diario a las 06:30 UTC."""
    global ultima_fecha_reporte
    ahora = datetime.now(timezone.utc)
    if ultima_fecha_reporte == ahora.date():
        return
    if ahora.strftime("%H:%M") == "06:30":
        enviar_telegram(generar_reporte("1h"))
        ultima_fecha_reporte = ahora.date()

# === ESCUCHA DE COMANDOS TELEGRAM ===
def escuchar_comandos():
    """Escucha comandos manuales enviados al bot."""
    global ultimo_mensaje_id
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    while True:
        try:
            r = requests.get(url, timeout=20)
            data = r.json()
            if "result" in data and len(data["result"]) > 0:
                mensaje = data["result"][-1]
                msg_id = mensaje["update_id"]
                if msg_id != ultimo_mensaje_id:
                    ultimo_mensaje_id = msg_id
                    texto = mensaje["message"].get("text", "").strip().lower()
                    if texto.startswith("/reporte"):
                        partes = texto.split()
                        tf = partes[1] if len(partes) > 1 and partes[1] in TIMEFRAMES else "1h"
                        enviar_telegram(generar_reporte(tf))
            time.sleep(5)
        except:
            time.sleep(10)

# === LOOP PRINCIPAL ===
if __name__ == "__main__":
    enviar_telegram("🤖 Bot cripto con alertas + comando /reporte (1h, 4h, 1d) ✅")

    Thread(target=escuchar_comandos, daemon=True).start()

    while True:
        try:
            enviar_reporte_diario()

            for par in PAIRS:
                analizar_moneda(par)
                time.sleep(3)

            print(f"💓 Bot activo y ejecutándose... {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
            time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle principal: {e}")
            traceback.print_exc()
            time.sleep(60)




