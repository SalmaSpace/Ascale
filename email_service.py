"""Envoi de l'email de confirmation de réservation, via SMTP (Flask-Mail).

Configuré uniquement par variables d'environnement (voir `.env.example`) :
tant qu'elles ne sont pas renseignées, `mail_configuree()` retourne False et
l'envoi est simplement ignoré (le client voit un message adapté sur la page
de confirmation) sans jamais faire planter le parcours de réservation. Le
SMS reste en simulation (voir templates/reservation_confirmee.html) : pas
d'API SMS branchée pour l'instant, coût/complexité non justifiés à ce stade.
"""

import logging
import os

from flask import render_template
from flask_mail import Message

logger = logging.getLogger(__name__)

MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").strip().lower() != "false"
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or MAIL_USERNAME


def mail_configuree() -> bool:
    """True une fois les identifiants SMTP renseignés dans .env."""
    return bool(MAIL_USERNAME and MAIL_PASSWORD)


def envoyer_confirmation_reservation(mail, reservation, creneau) -> bool:
    """Envoie l'email de confirmation à `reservation.client_email`.

    Retourne True si l'envoi a réussi, False sinon (identifiants absents ou
    erreur SMTP) — ne lève jamais d'exception : la réservation elle-même est
    déjà enregistrée à ce stade, un souci d'envoi ne doit pas faire échouer
    le parcours client.
    """
    if not mail_configuree():
        logger.info("Email de confirmation non envoyé : MAIL_USERNAME/MAIL_PASSWORD absents de .env.")
        return False

    try:
        message = Message(
            subject="Confirmation de votre visite showroom Ascale",
            recipients=[reservation.client_email],
            body=_corps_texte(reservation, creneau),
            html=render_template(
                "email_confirmation_reservation.html", reservation=reservation, creneau=creneau
            ),
        )
        mail.send(message)
        return True
    except Exception:
        logger.exception("Échec de l'envoi de l'email de confirmation pour la réservation n°%s", reservation.id)
        return False


def _corps_texte(reservation, creneau) -> str:
    if creneau is None:
        creneau_texte = ""
    else:
        creneau_texte = (
            f"{creneau.date_creneau.strftime('%d/%m/%Y')} "
            f"de {creneau.heure_debut.strftime('%Hh%M')} à {creneau.heure_fin.strftime('%Hh%M')}"
        )
    return (
        f"Bonjour {reservation.client_nom},\n\n"
        f"Votre visite du showroom Ascale est confirmée pour le {creneau_texte}.\n\n"
        f"Référence réservation n°{reservation.id}.\n\n"
        "À très bientôt,\nL'équipe Ascale"
    )
