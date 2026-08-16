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


def envoyer_message(destinataire: str, texte: str) -> None:
    """Enverra `texte` au numéro `destinataire` via l'API Graph de Meta.

    Non implémenté tant que le compte WhatsApp Business n'est pas actif :
    ce point d'entrée existe pour que l'appel soit déjà prêt côté code une
    fois les identifiants disponibles (appel HTTP vers l'API Graph avec
    WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID).
    """
    if not api_configuree():
        return
    raise NotImplementedError(
        "Envoi via l'API WhatsApp Business à implémenter une fois le compte activé."
    )
