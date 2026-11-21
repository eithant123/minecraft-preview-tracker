"""
test_telegram.py — Manda un mensaje de prueba por Telegram, sin depender
de que cambie el estado real del cupo. Si Telegram rechaza el mensaje,
muestra el motivo exacto en el log de GitHub Actions y marca el workflow
en rojo.

Se ejecuta a mano desde GitHub Actions (workflow_dispatch), pasando tu
Telegram ID como input.
"""

import os
import sys

import requests

TEST_MESSAGE = (
    "👋 ¡Hola! Soy el bot de WaitRadar.\n\n"
    "Este es un mensaje de prueba para confirmar que tus avisos de cupo "
    "por Telegram funcionan bien. 🎉\n\n"
    "📊 Dashboard: https://eithant123.github.io/minecraft-preview-tracker/"
)


def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TEST_TELEGRAM_ID", "").strip()

    if not token:
        print("Falta el secreto TELEGRAM_TOKEN en GitHub.", file=sys.stderr)
        sys.exit(1)
    if not chat_id.lstrip("-").isdigit():
        print("El Telegram ID debe ser solo números.", file=sys.stderr)
        sys.exit(1)

    print(f"Enviando mensaje de prueba a {chat_id}...")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": TEST_MESSAGE},
        timeout=15,
    )
    print(f"Respuesta de Telegram: {resp.status_code} {resp.text}")

    if resp.ok:
        print("Listo. Revisa tu Telegram.")
        return

    if resp.status_code == 401:
        print("-> El TELEGRAM_TOKEN es incorrecto o fue regenerado.", file=sys.stderr)
    elif resp.status_code == 403:
        print("-> El bot no puede escribirte: abre el bot en Telegram y toca Start (o desbloquéalo).", file=sys.stderr)
    elif resp.status_code == 400:
        print("-> Telegram no encontró ese chat: revisa que el ID sea el tuyo.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
