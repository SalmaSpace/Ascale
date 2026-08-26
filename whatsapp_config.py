"""Point d'intégration pour la vraie API WhatsApp Business Cloud (Meta).

Non activé pour le moment : le compte WhatsApp Business n'est pas encore
créé (à faire avec Nasser). Ce module prépare le branchement : une fois les
identifiants disponibles, il suffira de renseigner les variables
d'environnement ci-dessous pour que le webhook `/webhook/whatsapp`
(voir `app.py`) devienne actif et transmette les messages entrants à
`chatbot.repondre()`, exactement comme le fait déjà la page de simulation
`/chatbot`.
"""

import os

WHATSAPP_API_VERSION = "v20.0"
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")


def api_configuree() -> bool:
    """True une fois les identifiants WhatsApp Business renseignés."""
    return bool(WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN)


def envoyer_message(destinataire: str, texte: str) -> bool:
    """Envoie `texte` au numéro `destinataire` via l'API Graph de Meta.

    Retourne True si l'envoi a réussi, False sinon.
    Ne fait rien tant que les identifiants ne sont pas configurés.
    """
    import json
    import urllib.request
    import urllib.error

    if not api_configuree():
        return False

    url = (
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
        f"/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": destinataire,
        "type": "text",
        "text": {"body": texte},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False
