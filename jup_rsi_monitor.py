
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from verify_jup_data import (
    fetch_candles,
    calculate_rsi,
    calculate_bollinger,
    RSI_PERIOD,
)

# ============================================================
# JUP RSI + BOLLINGER BANDS DISCORD NOTIFIER
# VERSION V1.0.3
#
# 1H JUPITER CHART
# RSI(14), BB(20,2)
# NO TRADING OR WALLET ACCESS
# ============================================================

STATE_FILE = Path("alert_state.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

CHART_URL = (
    "https://jup.ag/tokens/"
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
)


def utc(timestamp):
    return datetime.fromtimestamp(
        timestamp, timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def new_state(candle_time):
    return {
        "candle_time": candle_time,
        "rsi_30_touched": False,
        "rsi_70_touched": False,
        "lower_bb_touched": False,
        "upper_bb_touched": False,
        "oversold_sent": False,
        "overbought_sent": False,
    }


def load_state(candle_time):
    if not STATE_FILE.exists():
        return new_state(candle_time)

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        if not isinstance(data, dict):
            raise ValueError("Invalid state structure")

        if data.get("candle_time") != candle_time:
            print("New 1H candle: resetting signal flags")
            return new_state(candle_time)

        state = new_state(candle_time)

        for key in state:
            if key != "candle_time":
                state[key] = data.get(key) is True

        return state

    except (ValueError, OSError) as error:
        raise RuntimeError(
            "Cannot safely read alert state"
        ) from error


def save_state(state):
    temporary = STATE_FILE.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )

    temporary.replace(STATE_FILE)


def send_discord(kind, candle, rsi, upper, lower):
    if not WEBHOOK:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL secret is missing"
        )

    oversold = kind == "oversold"

    title = (
        "JUP 1H OVERSOLD ALERT"
        if oversold
        else "JUP 1H OVERBOUGHT ALERT"
    )

    description = (
        "RSI touched 30 or below AND the candle "
        "touched the lower Bollinger Band."
        if oversold
        else
        "RSI touched 70 or above AND the candle "
        "touched the upper Bollinger Band."
    )

    payload = {
        "username": "JUP RSI + BB Alerts",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": (
                    3066993 if oversold else 15158332
                ),
                "fields": [
                    {
                        "name": "RSI(14) at check",
                        "value": f"{rsi:.2f}",
                        "inline": True,
                    },
                    {
                        "name": "JUP price",
                        "value": f"${candle['close']:.6f}",
                        "inline": True,
                    },
                    {
                        "name": "Candle low",
                        "value": f"${candle['low']:.6f}",
                        "inline": True,
                    },
                    {
                        "name": "Lower BB",
                        "value": f"${lower:.6f}",
                        "inline": True,
                    },
                    {
                        "name": "Candle high",
                        "value": f"${candle['high']:.6f}",
                        "inline": True,
                    },
                    {
                        "name": "Upper BB",
                        "value": f"${upper:.6f}",
                        "inline": True,
                    },
                    {
                        "name": "1H candle started",
                        "value": utc(candle["time"]),
                        "inline": False,
                    },
                ],
                "url": CHART_URL,
                "footer": {
                    "text": (
                        "Jupiter 1H | RSI 14 | "
                        "BB 20,2 | V1.0.3"
                    )
                },
            }
        ],
    }

    request = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JUP-RSI-BB-Alert/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=30
        ) as response:
            if response.status not in (200, 204):
                raise RuntimeError(
                    f"Unexpected Discord status: "
                    f"{response.status}"
                )

            print(
                f"Discord {kind} alert sent successfully"
            )

    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Discord HTTP error: {error.code}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Discord connection failed"
        ) from error


def main():
    print("===================================")
    print("JUP RSI + BB DISCORD MONITOR V1.0.3")
    print("===================================")

    now = int(time.time())
    current_hour = (now // 3600) * 3600

    candles = fetch_candles()
    candle = candles[-1]

    # Never use stale or future candles.
    if candle["time"] != current_hour:
        print("WARNING: Current 1H candle unavailable")
        print("Expected:", utc(current_hour))
        print("Received:", utc(candle["time"]))
        print("Skipping alerts safely")
        return

    closes = [item["close"] for item in candles]

    rsi = calculate_rsi(closes, RSI_PERIOD)
    middle, upper, lower = calculate_bollinger(closes)

    state = load_state(candle["time"])

    print()
    print("Candle:", utc(candle["time"]))
    print("RSI(14):", round(rsi, 4))
    print("Price:", round(candle["close"], 8))
    print("Candle high:", round(candle["high"], 8))
    print("Candle low:", round(candle["low"], 8))
    print("BB middle:", round(middle, 8))
    print("BB upper:", round(upper, 8))
    print("BB lower:", round(lower, 8))

    # Latch conditions observed during this 1H candle.
    # Once observed, a flag remains true until the next
    # hourly candle begins.

    if rsi <= 30:
        state["rsi_30_touched"] = True

    if rsi >= 70:
        state["rsi_70_touched"] = True

    if candle["low"] <= lower:
        state["lower_bb_touched"] = True

    if candle["high"] >= upper:
        state["upper_bb_touched"] = True

    oversold = (
        state["rsi_30_touched"]
        and state["lower_bb_touched"]
    )

    overbought = (
        state["rsi_70_touched"]
        and state["upper_bb_touched"]
    )

    print()
    print("RSI <= 30 touched:", state["rsi_30_touched"])
    print("Lower BB touched:", state["lower_bb_touched"])
    print("RSI >= 70 touched:", state["rsi_70_touched"])
    print("Upper BB touched:", state["upper_bb_touched"])
    print("Oversold signal:", oversold)
    print("Overbought signal:", overbought)

    # Persist newly observed flags before attempting
    # notification, so they survive later checks.
    save_state(state)

    if oversold and not state["oversold_sent"]:
        print("NEW OVERSOLD SIGNAL")
        send_discord(
            "oversold", candle, rsi, upper, lower
        )
        state["oversold_sent"] = True
        save_state(state)

    if overbought and not state["overbought_sent"]:
        print("NEW OVERBOUGHT SIGNAL")
        send_discord(
            "overbought", candle, rsi, upper, lower
        )
        state["overbought_sent"] = True
        save_state(state)

    if not oversold and not overbought:
        print("No qualifying alert at this check")

    print("Monitoring check complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"MONITOR FAILED: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
