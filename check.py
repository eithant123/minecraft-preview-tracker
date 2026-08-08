"""
check.py — Revisa si hay cupos disponibles en el beta de Minecraft Preview
(TestFlight, iOS) y avisa por Telegram si el estado cambió.

Se ejecuta automáticamente por GitHub Actions cada 15 minutos (ver
.github/workflows/check.yml). No necesita laptop ni servidor propio.

Respeta las preferencias guardadas en prefs.json:
  - notify_on_open / notify_on_close: qué cambios de estado avisan
  - quiet_hours_enabled/start/end/utc_offset_hours: horario sin avisos
  - muted_until: silencio temporal (ISO datetime UTC) — mientras no pase esa
    fecha, no se manda ningún aviso aunque el estado cambie
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

# Link público oficial del beta de Minecraft Preview en TestFlight
TESTFLIGHT_URL = "https://departures.to/apps/12975"

# Frase que la página muestra cuando el beta NO tiene cupos disponibles
FULL_PHRASE = "Reached capacity"

STATUS_FILE = "status.json"
PREFS_FILE = "prefs.json"

DEFAULT_PREFS = {
    "notify_on_open": True,
    "notify_on_close": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "08:00",
    "utc_offset_hours": -4,
    "muted_until": None,
}


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


def load_prefs() -> dict:
    """Lee prefs.json y completa cualquier campo faltante con el default."""
    prefs = dict(DEFAULT_PREFS)
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                prefs.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"No se pudo leer prefs.json, uso defaults: {e}", file=sys.stderr)
    return prefs


def is_muted(prefs: dict, now_utc: datetime) -> bool:
    muted_until = prefs.get("muted_until")
    if not muted_until:
        return False
    try:
        until = datetime.fromisoformat(muted_until.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return now_utc < until
    except ValueError:
        print(f"muted_until inválido en prefs.json: {muted_until!r}", file=sys.stderr)
        return False


def is_quiet_hours(prefs: dict, now_utc: datetime) -> bool:
    if not prefs.get("quiet_hours_enabled"):
        return False
    offset = timedelta(hours=prefs.get("utc_offset_hours", 0))
    local_now = (now_utc + offset).time()

    start = datetime.strptime(prefs["quiet_hours_start"], "%H:%M").time()
    end = datetime.strptime(prefs["quiet_hours_end"], "%H:%M").time()

    if start <= end:
        return start <= local_now < end
    # Rango que cruza medianoche (ej. 23:00 -> 08:00)
    return local_now >= start or local_now < end


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID, no se envía aviso.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=15)


def main() -> None:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    try:
        current_status = check_status()
    except Exception as e:
        print(f"Error revisando TestFlight: {e}", file=sys.stderr)
        sys.exit(0)  # no rompemos el workflow por un error de red puntual

    data = load_previous_status()
    previous_status = data["status"]

    data["last_checked"] = now_iso
    data["status"] = current_status

    if previous_status != current_status:
        data["history"].append({"status": current_status, "changed_at": now_iso})
        print(f"Estado cambió: {previous_status} -> {current_status}")

        prefs = load_prefs()

        if is_muted(prefs, now):
            print("Silenciado manualmente (muted_until) — no se envía aviso.")
        elif is_quiet_hours(prefs, now):
            print("Dentro del horario de silencio — no se envía aviso.")
        elif current_status == "open" and not prefs.get("notify_on_open", True):
            print("notify_on_open está desactivado — no se envía aviso.")
        elif current_status == "full" and not prefs.get("notify_on_close", True):
            print("notify_on_close está desactivado — no se envía aviso.")
        else:
            if current_status == "open":
                send_telegram(
                    "🟢 ¡Hay cupos en Minecraft Preview (TestFlight)! "
                    f"Entra ya: {TESTFLIGHT_URL}"
                )
            else:
                send_telegram("🔴 El beta de Minecraft Preview se llenó de nuevo.")
    else:
        print(f"Sin cambios. Estado actual: {current_status}")

    save_status(data)


if __name__ == "__main__":
    main()
