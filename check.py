"""
check.py — Revisa si hay cupos disponibles en el beta de Minecraft Preview
(TestFlight, iOS) y avisa por Telegram a cada usuario registrado si el
estado cambió, respetando las preferencias propias de cada uno.

Se ejecuta automáticamente por GitHub Actions cada 15 minutos (ver
.github/workflows/check.yml). No necesita laptop ni servidor propio.

Cada usuario se registra iniciando sesión con Telegram en settings.html,
lo que crea su fila en la tabla user_prefs (Supabase). Por cada uno se
respeta:
  - notify_on_open / notify_on_close: qué cambios de estado avisan
  - quiet_hours_enabled/start/end/utc_offset_hours: horario sin avisos
  - muted_until: silencio temporal (ISO datetime UTC)
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

DEFAULT_PREFS = {
    "notify_on_open": True,
    "notify_on_close": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "08:00",
    "utc_offset_hours": -4,
    "muted_until": None,
    "is_premium": False,
    "discord_user_id": None,
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


def load_all_users() -> list:
    """Trae todos los usuarios registrados desde Supabase (tabla user_prefs).
    Cada uno con su propio telegram_id y sus propias preferencias.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Faltan SUPABASE_URL o SUPABASE_KEY, no se puede avisar a nadie.", file=sys.stderr)
        return []
    try:
        resp = requests.get(
            f"{url}/rest/v1/user_prefs",
            params={"select": "*"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"No se pudo leer user_prefs de Supabase: {e}", file=sys.stderr)
        return []


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


def send_telegram(chat_id, message: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token or not chat_id:
        print("Falta TELEGRAM_TOKEN o chat_id, no se envía aviso.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=15)
    except Exception as e:
        print(f"No se pudo avisar a {chat_id}: {e}", file=sys.stderr)


def send_discord_dm(discord_user_id: str, message: str) -> None:
    """Manda un mensaje directo (DM) a un usuario de Discord por su ID,
    usando la API REST del bot — no necesita mantenerse conectado 24/7,
    solo dos llamadas HTTP: abrir el canal de DM y mandar el mensaje.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token or not discord_user_id:
        print("Falta DISCORD_BOT_TOKEN o discord_user_id, no se envía DM.")
        return

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    try:
        # 1. Abrir (o reusar) el canal de DM con ese usuario
        dm_resp = requests.post(
            "https://discord.com/api/v10/users/@me/channels",
            json={"recipient_id": discord_user_id},
            headers=headers,
            timeout=15,
        )
        dm_resp.raise_for_status()
        channel_id = dm_resp.json()["id"]

        # 2. Mandar el mensaje a ese canal
        msg_resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json={"content": message},
            headers=headers,
            timeout=15,
        )
        msg_resp.raise_for_status()
    except Exception as e:
        print(f"No se pudo mandar DM de Discord a {discord_user_id}: {e}", file=sys.stderr)


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
    pending_status = data.get("pending_status")

    data["last_checked"] = now_iso

    if current_status == previous_status:
        # Sin cambios: limpiamos cualquier pendiente de una lectura rara anterior
        data["pending_status"] = None
        data["status"] = current_status
        print(f"Sin cambios. Estado actual: {current_status}")
        save_status(data)
        return

    if current_status != pending_status:
        # Primera vez que vemos este posible cambio: lo guardamos como "pendiente"
        # y esperamos al próximo chequeo (~15 min) para confirmarlo antes de avisar.
        # Esto evita mandar avisos falsos si departures.to tuvo un tropiezo momentáneo.
        data["pending_status"] = current_status
        data["status"] = previous_status  # seguimos mostrando el último estado confirmado
        print(f"Posible cambio detectado ({previous_status} -> {current_status}), esperando confirmación en el próximo chequeo.")
        save_status(data)
        return

    # current_status == pending_status: segundo chequeo seguido coincide, confirmamos el cambio
    data["pending_status"] = None
    data["status"] = current_status

    if previous_status != current_status:
        data["history"].append({"status": current_status, "changed_at": now_iso})
        print(f"Estado cambió (confirmado): {previous_status} -> {current_status}")

        users = load_all_users()
        print(f"Avisando a {len(users)} usuario(s) registrado(s)...")

        for u in users:
            prefs = dict(DEFAULT_PREFS)
            prefs.update(u)
            chat_id = u.get("telegram_id")

            if is_muted(prefs, now):
                print(f"{chat_id}: silenciado manualmente, no se avisa.")
                continue
            if is_quiet_hours(prefs, now):
                print(f"{chat_id}: en horario de silencio, no se avisa.")
                continue
            if current_status == "open" and not prefs.get("notify_on_open", True):
                print(f"{chat_id}: notify_on_open desactivado, no se avisa.")
                continue
            if current_status == "full" and not prefs.get("notify_on_close", True):
                print(f"{chat_id}: notify_on_close desactivado, no se avisa.")
                continue

            discord_msg = None
            if current_status == "open":
                telegram_msg = (
                    "🟢 ¡Hay cupos en Minecraft Preview (TestFlight)! "
                    f"Entra ya: {TESTFLIGHT_URL}"
                )
                discord_msg = f"🟢 ¡Hay cupos en Minecraft Preview! Entra ya: {TESTFLIGHT_URL}"
            else:
                telegram_msg = "🔴 El beta de Minecraft Preview se llenó de nuevo."
                discord_msg = "🔴 El beta de Minecraft Preview se llenó de nuevo."

            send_telegram(chat_id, telegram_msg)

            # Discord: solo para usuarios premium que guardaron su ID
            if prefs.get("is_premium") and prefs.get("discord_user_id"):
                send_discord_dm(prefs["discord_user_id"], discord_msg)

    save_status(data)


if __name__ == "__main__":
    main()
