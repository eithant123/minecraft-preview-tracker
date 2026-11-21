"""
test_notify_all.py — Verifica de punta a punta que los avisos funcionan:
lee user_prefs de Supabase (igual que check.py) y, si se pide, manda un
mensaje de prueba por Telegram a cada usuario registrado.

IMPORTANTE: los logs de GitHub Actions de un repositorio público los puede
ver cualquiera, así que este script NUNCA imprime IDs completos, usernames
ni nombres: solo el número de usuario y los últimos 3 dígitos del ID.

Por defecto solo LISTA (no manda nada). Para mandar, el workflow debe
recibir ENVIAR=si.
"""

import os
import sys
from collections import Counter

import requests

TEST_MESSAGE = (
    "🧪 Mensaje de prueba de WaitRadar: tus avisos de cupo por Telegram "
    "están activos. No tienes que hacer nada."
)


def mask(tid) -> str:
    s = str(tid)
    return "***" + s[-3:] if len(s) > 3 else "***"


def load_users() -> list:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Faltan los secretos SUPABASE_URL o SUPABASE_KEY.", file=sys.stderr)
        sys.exit(1)
    resp = requests.get(
        f"{url}/rest/v1/user_prefs",
        params={"select": "*"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=15,
    )
    print(f"Supabase respondió: {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    users = load_users()
    print(f"Usuarios registrados leídos: {len(users)}")
    if not users:
        print("-> La lista está vacía: revisa las reglas (RLS) de user_prefs en Supabase o la llave usada.", file=sys.stderr)
        sys.exit(1)

    # Posibles cuentas repetidas (mismo @usuario o mismo nombre), sin mostrar cuáles
    keys = Counter()
    for u in users:
        k = (u.get("telegram_username") or u.get("telegram_first_name") or "").strip().lower()
        if k:
            keys[k] += 1
    repeated = sum(1 for n in keys.values() if n > 1)
    print(f"Grupos con el mismo @usuario o nombre (posibles duplicados): {repeated}")

    for i, u in enumerate(users, 1):
        print(
            f"  #{i} id {mask(u.get('telegram_id'))} | "
            f"premium={'si' if u.get('is_premium') else 'no'} | "
            f"discord={'si' if u.get('discord_user_id') else 'no'} | "
            f"silenciado={'si' if u.get('muted_until') else 'no'}"
        )

    if os.environ.get("ENVIAR", "no").lower() != "si":
        print("Modo lista: no se mandó ningún mensaje. Para probar el envío, corre el workflow con enviar = si.")
        return

    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("Falta el secreto TELEGRAM_TOKEN.", file=sys.stderr)
        sys.exit(1)

    ok = fail = 0
    for i, u in enumerate(users, 1):
        chat_id = u.get("telegram_id")
        if not chat_id:
            continue
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": TEST_MESSAGE},
                timeout=15,
            )
            if r.ok:
                ok += 1
                print(f"  #{i} ({mask(chat_id)}): enviado")
            else:
                fail += 1
                print(f"  #{i} ({mask(chat_id)}): falló con código {r.status_code}", file=sys.stderr)
        except Exception as e:
            fail += 1
            print(f"  #{i} ({mask(chat_id)}): error de red ({type(e).__name__})", file=sys.stderr)

    print(f"Resultado: {ok} enviados, {fail} fallidos.")
    if fail and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
