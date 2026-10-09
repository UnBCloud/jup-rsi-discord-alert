
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TOKEN = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
BASE_URL = f"https://datapi.jup.ag/v2/charts/{TOKEN}"

RSI_PERIOD = 14
BB_PERIOD = 20
BB_MULTIPLIER = 2.0


def utc_time(timestamp):
    return datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch_candles():
    params = {
        "interval": "1_HOUR",
        "to": int(time.time()),
        "candles": 329,
        "type": "price",
        "quote": "usd",
    }

    url = BASE_URL + "?" + urllib.parse.urlencode(params)

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
            print("API HTTP status:", response.status)
            payload = json.load(response)

    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Jupiter API returned HTTP {error.code}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Jupiter API connection failed: "
            f"{type(error.reason).__name__}"
        ) from error

    raw_candles = payload.get("candles")

    if not isinstance(raw_candles, list):
        raise RuntimeError(
            "Unexpected API response: candles list missing"
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

        if not all(
            math.isfinite(candle[field])
            for field in ("open", "high", "low", "close")
        ):
            raise RuntimeError("Invalid candle price")

        candles.append(candle)

    candles.sort(key=lambda c: c["time"])

    timestamps = [c["time"] for c in candles]

    if len(timestamps) != len(set(timestamps)):
        raise RuntimeError("Duplicate candle timestamps")

    if len(candles) < 100:
        raise RuntimeError("Insufficient candle history")

    for previous, current in zip(
        candles, candles[1:]
    ):
        if current["time"] - previous["time"] != 3600:
            raise RuntimeError(
                "Missing or irregular 1-hour candles"
            )

    return candles


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        raise ValueError("Insufficient RSI history")

    changes = [
        closes[i] - closes[i - 1]
        for i in range(1, len(closes))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]

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

    return 100 - (100 / (1 + relative_strength))


def calculate_bollinger(closes):
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


def main():
    print("=== JUPITER CHART VERIFICATION ===")
    print("Token:", TOKEN)
    print("Timeframe: 1_HOUR")
    print("RSI period:", RSI_PERIOD)
    print("Bollinger Bands: 20, 2")
    print()

    candles = fetch_candles()

    current = candles[-1]
    closes = [c["close"] for c in candles]

    now = int(time.time())
    current_hour = (now // 3600) * 3600

    if current["time"] != current_hour:
        raise RuntimeError(
            "Latest candle is not the current 1H candle. "
            f"Latest: {utc_time(current['time'])}; "
            f"Expected: {utc_time(current_hour)}"
        )

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

    print("=== CANDLE DATA ===")
    print("Candles received:", len(candles))
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
    print("=== ALERT CONDITIONS ===")
    print("RSI <= 30:", rsi <= 30)
    print("Low <= Lower BB:", current["low"] <= lower)
    print("OVERSOLD SIGNAL:", oversold)

    print("RSI >= 70:", rsi >= 70)
    print("High >= Upper BB:", current["high"] >= upper)
    print("OVERBOUGHT SIGNAL:", overbought)

    print()
    print("Verification complete.")
    print("No Discord notification was sent.")


if __name__ == "__main__":
    main()
