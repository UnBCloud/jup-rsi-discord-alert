
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ============================================================
# JUP RSI + BOLLINGER BANDS DISCORD ALERT BOT
# VERSION: V1.0.2 - JUPITER API VERIFICATION
#
# Data source: Jupiter's actual JUP chart API
# Timeframe: 1 Hour
# RSI: 14 (Wilder smoothing)
# Bollinger Bands: 20 periods, 2 standard deviations
#
# VERIFICATION ONLY - NO DISCORD NOTIFICATIONS
# ============================================================

TOKEN = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
BASE_URL = f"https://datapi.jup.ag/v2/charts/{TOKEN}"

TIMEFRAME = "1_HOUR"
REQUESTED_CANDLES = 329
MINIMUM_CANDLES = 100

RSI_PERIOD = 14
BB_PERIOD = 20
BB_MULTIPLIER = 2.0


# ============================================================
# TIME FORMATTING
# ============================================================

def utc_time(timestamp):
    return datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# FETCH JUPITER CANDLES
# ============================================================

def fetch_candles():
    # Jupiter expects a 13-digit millisecond timestamp.
    timestamp_ms = int(time.time() * 1000)

    params = {
        "interval": TIMEFRAME,
        "to": timestamp_ms,
        "candles": REQUESTED_CANDLES,
        "type": "price",
        "quote": "usd",
    }

    url = BASE_URL + "?" + urllib.parse.urlencode(params)

    print("=== JUPITER API REQUEST ===", flush=True)
    print("API:", BASE_URL, flush=True)
    print("Timeframe:", TIMEFRAME, flush=True)
    print("Timestamp (ms):", timestamp_ms, flush=True)
    print("Candles requested:", REQUESTED_CANDLES, flush=True)

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://jup.ag",
            "Referer": "https://jup.ag/",
        },
    )

    try:
        with urllib.request.urlopen(
            request, timeout=30
        ) as response:
            print(
                "API HTTP status:",
                response.status,
                flush=True
            )
            payload = json.load(response)

    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Jupiter API returned HTTP {error.code}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Jupiter API connection failed: "
            f"{type(error.reason).__name__}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected API response format")

    raw_candles = payload.get("candles")

    if not isinstance(raw_candles, list):
        print("Response fields:", list(payload.keys()))
        raise RuntimeError(
            "Jupiter response has no candles list"
        )

    print(
        "Candles received (raw):",
        len(raw_candles),
        flush=True
    )

    candles = []

    for item in raw_candles:
        candle = {
            "time": int(item["time"]),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        }

        prices = (
            candle["open"],
            candle["high"],
            candle["low"],
            candle["close"],
        )

        if not all(math.isfinite(price) for price in prices):
            raise RuntimeError("Invalid candle price")

        if (
            candle["high"] < max(
                candle["open"],
                candle["close"],
                candle["low"]
            )
            or candle["low"] > min(
                candle["open"],
                candle["close"],
                candle["high"]
            )
        ):
            raise RuntimeError("Invalid OHLC candle")

        candles.append(candle)

    candles.sort(key=lambda c: c["time"])

    timestamps = [c["time"] for c in candles]

    if len(timestamps) != len(set(timestamps)):
        raise RuntimeError("Duplicate candle timestamps")

    print(
        "Candles received (validated):",
        len(candles),
        flush=True
    )

    if candles:
        print(
            "Oldest candle:",
            utc_time(candles[0]["time"]),
            flush=True
        )
        print(
            "Newest candle:",
            utc_time(candles[-1]["time"]),
            flush=True
        )

    if len(candles) < MINIMUM_CANDLES:
        raise RuntimeError(
            "Insufficient candle history: "
            f"requested {REQUESTED_CANDLES}, "
            f"received {len(candles)}, "
            f"minimum required {MINIMUM_CANDLES}"
        )

    for previous, current in zip(candles, candles[1:]):
        difference = current["time"] - previous["time"]

        if difference != 3600:
            raise RuntimeError(
                "Missing or irregular 1-hour candles: "
                f"{utc_time(previous['time'])} to "
                f"{utc_time(current['time'])}"
            )

    return candles


# ============================================================
# RSI(14) - WILDER SMOOTHING
# ============================================================

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        raise ValueError("Insufficient RSI history")

    changes = [
        closes[i] - closes[i - 1]
        for i in range(1, len(closes))
    ]

    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        average_gain = (
            average_gain * (period - 1) + gains[i]
        ) / period

        average_loss = (
            average_loss * (period - 1) + losses[i]
        ) / period

    if average_gain == 0 and average_loss == 0:
        return 50.0

    if average_loss == 0:
        return 100.0

    relative_strength = average_gain / average_loss

    return 100 - 100 / (1 + relative_strength)


# ============================================================
# BOLLINGER BANDS (20, 2)
# ============================================================

def calculate_bollinger(closes):
    if len(closes) < BB_PERIOD:
        raise ValueError("Insufficient Bollinger history")

    window = closes[-BB_PERIOD:]

    middle = sum(window) / BB_PERIOD

    variance = sum(
        (price - middle) ** 2
        for price in window
    ) / BB_PERIOD

    deviation = math.sqrt(variance)

    upper = middle + BB_MULTIPLIER * deviation
    lower = middle - BB_MULTIPLIER * deviation

    return middle, upper, lower


# ============================================================
# MAIN VERIFICATION
# ============================================================

def main():
    print("========================================")
    print("JUPITER 1H INDICATOR VERIFICATION")
    print("VERSION: V1.0.2")
    print("========================================")
    print()

    print("Token:", TOKEN)
    print("Timeframe:", TIMEFRAME)
    print("RSI period:", RSI_PERIOD)
    print("Bollinger Bands:", BB_PERIOD, BB_MULTIPLIER)
    print()

    candles = fetch_candles()

    current = candles[-1]
    closes = [candle["close"] for candle in candles]

    now = int(time.time())
    current_hour = (now // 3600) * 3600

    print()
    print("=== CANDLE FRESHNESS ===")
    print("Current UTC hour:", utc_time(current_hour))
    print("Latest API candle:", utc_time(current["time"]))

    if current["time"] != current_hour:
        raise RuntimeError(
            "Latest candle is not the current 1-hour candle. "
            f"Latest: {utc_time(current['time'])}; "
            f"Expected: {utc_time(current_hour)}"
        )

    print("Candle freshness: PASS")

    rsi = calculate_rsi(closes, RSI_PERIOD)

    middle, upper, lower = calculate_bollinger(closes)

    oversold = (
        rsi <= 30
        and current["low"] <= lower
    )

    overbought = (
        rsi >= 70
        and current["high"] >= upper
    )

    print()
    print("=== CURRENT 1H CANDLE ===")
    print("Candle start:", utc_time(current["time"]))
    print("Checked at:", utc_time(now))
    print("Open:", f"{current['open']:.8f}")
    print("High:", f"{current['high']:.8f}")
    print("Low:", f"{current['low']:.8f}")
    print("Close:", f"{current['close']:.8f}")

    print()
    print("=== INDICATORS ===")
    print("RSI(14):", f"{rsi:.4f}")
    print("BB Middle:", f"{middle:.8f}")
    print("BB Upper:", f"{upper:.8f}")
    print("BB Lower:", f"{lower:.8f}")

    print()
    print("=== OVERSOLD CONDITIONS ===")
    print("RSI <= 30:", rsi <= 30)
    print(
        "Candle low <= Lower BB:",
        current["low"] <= lower
    )
    print("OVERSOLD SIGNAL:", oversold)

    print()
    print("=== OVERBOUGHT CONDITIONS ===")
    print("RSI >= 70:", rsi >= 70)
    print(
        "Candle high >= Upper BB:",
        current["high"] >= upper
    )
    print("OVERBOUGHT SIGNAL:", overbought)

    print()
    print("========================================")
    print("VERIFICATION COMPLETED SUCCESSFULLY")
    print("No Discord notifications were sent.")
    print("========================================")


if __name__ == "__main__":
    main()
