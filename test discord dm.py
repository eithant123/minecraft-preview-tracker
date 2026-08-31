"""
test_discord_dm.py tes — Manda un DM de prueba por Discord, sin depender
de que cambie el estado real del cupo. Útil para confirmar que el bot
y el discord_user_id guardado funcionan bien.

Se ejecuta manualmente desde GitHub Actions (workflow_dispatch), pasando
tu Discord ID como input. Reusa exactamente la misma función send_discord_dm
que ya usa check.py.
"""

import os
import sys

from check import send_discord_dm, TESTFLIGHT_URL

TEST_MESSAGE = (
    "👋 ¡Hola! Soy el bot de **WaitRadar**.\n\n"
    "Este es un mensaje de prueba para confirmar que tus avisos de cupo "
    "por Discord están funcionando correctamente. 🎉\n\n"
    f"🔗 Revisa el estado en vivo aquí: {TESTFLIGHT_URL}\n"
    "📊 O mira el dashboard completo: https://eithant123.github.io/minecraft-preview-tracker/"
)


def main() -> None:
    discord_user_id = os.environ.get("TEST_DISCORD_USER_ID")
    if not discord_user_id:
        print("Falta TEST_DISCORD_USER_ID", file=sys.stderr)
        sys.exit(1)

    print(f"Enviando DM de prueba a {discord_user_id}...")
    send_discord_dm(discord_user_id, TEST_MESSAGE)
    print("Listo. Revisa tus DMs en Discord.")


if __name__ == "__main__":
    main()
