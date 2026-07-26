"""
check.py — Revisa si hay cupos disponibles en el beta de Minecraft Preview
(TestFlight, iOS) y avisa por Telegram si el estado cambió.

Se ejecuta automáticamente por GitHub Actions cada 15 minutos (ver
.github/workflows/check.yml). No necesita laptop ni servidor propio.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

# Link público oficial del beta de Minecraft Preview en TestFlight
TESTFLIGHT_URL = "https://departures.to/apps/12975"

# Frase que Apple muestra cuando el beta NO tiene cupos disponibles
FULL_PHRASE = "Reached capacity"

STATUS_FILE = "status.json"


def check_status() -> str:
    """Devuelve 'open' o 'full' según el contenido de la página de TestFlight."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 "
            "Mobile/15E148 Safari/604.1"
        )
    }
    resp = requests.get(TESTFLIGHT_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    text = resp.text
    return "full" if FULL_PHRASE in text else "open"


def load_previous_status() -> dict:
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"status": None, "history": []}


def save_status(data: dict) -> None:
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID, no se envía aviso.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=15)


def main() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        current_status = check_status()
    except Exception as e:
        print(f"Error revisando TestFlight: {e}", file=sys.stderr)
        sys.exit(0)  # no rompemos el workflow por un error de red puntual

    data = load_previous_status()
    previous_status = data["status"]

    data["last_checked"] = now
    data["status"] = current_status

    if previous_status != current_status:
        data["history"].append({"status": current_status, "changed_at": now})
        if current_status == "open":
            send_telegram(
                "🟢 ¡Hay cupos en Minecraft Preview (TestFlight)! "
                f"Entra ya: {TESTFLIGHT_URL}"
            )
        else:
            send_telegram("🔴 El beta de Minecraft Preview se llenó de nuevo.")
        print(f"Estado cambió: {previous_status} -> {current_status}")
    else:
        print(f"Sin cambios. Estado actual: {current_status}")

    save_status(data)


if __name__ == "__main__":
    main()
