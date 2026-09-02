"""Envoi des emails (réservation, facture, contact) via l'API HTTP de Brevo.

Configuré uniquement par variables d'environnement (voir `.env.example`) :
tant que `BREVO_API_KEY` n'est pas renseignée, `mail_configuree()` retourne
False et l'envoi est simplement ignoré (le client voit un message adapté)
sans jamais faire planter le parcours client. Le SMS reste en simulation
(voir templates/reservation_confirmee.html) : pas d'API SMS branchée pour
l'instant, coût/complexité non justifiés à ce stade.

Pourquoi Brevo plutôt que du SMTP direct (Gmail) : plusieurs hébergeurs
(dont le plan gratuit de Render) bloquent ou dégradent silencieusement les
connexions SMTP sortantes — la connexion reste ouverte sans jamais répondre
jusqu'à ce que le serveur d'app tue la requête. L'API Brevo passe en HTTPS
(port 443), qui n'est jamais bloqué de cette façon.
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.request

from flask import render_template

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Ascale Showroom")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def mail_configuree() -> bool:
    """True une fois la clé API Brevo renseignée dans .env."""
    return bool(BREVO_API_KEY and BREVO_SENDER_EMAIL)


def _envoyer_brevo(to_email, to_name, subject, html_body, text_body=None, attachments=None):
    """Appelle l'API Brevo. Retourne True si l'envoi a réussi, False sinon.

    `attachments` : liste de tuples (nom_fichier, bytes) à joindre en pièce jointe.
    Ne lève jamais d'exception.
    """
    if not mail_configuree():
        return False

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body
    if attachments:
        payload["attachment"] = [
            {"name": nom, "content": base64.b64encode(contenu).decode("ascii")}
            for nom, contenu in attachments
        ]

    req = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("Brevo a refusé l'email pour %s : %s — %s", to_email, exc.code, detail)
        return False
    except Exception:
        logger.exception("Échec de l'envoi Brevo pour %s", to_email)
        return False


def envoyer_confirmation_reservation(reservation, creneau) -> bool:
    """Envoie l'email de confirmation à `reservation.client_email`."""
    html = render_template(
        "email_confirmation_reservation.html", reservation=reservation, creneau=creneau
    )
    return _envoyer_brevo(
        reservation.client_email,
        reservation.client_nom,
        "Confirmation de votre visite showroom Ascale",
        html,
        text_body=_corps_texte(reservation, creneau),
    )


def envoyer_contact(nom, email, telephone, sujet, message, reponse_chatbot=None) -> bool:
    """Envoie le message de contact à l'entreprise ET un accusé de réception au client."""
    corps_interne = (
        f"Nouveau message de contact\n"
        f"{'=' * 40}\n"
        f"Nom      : {nom}\n"
        f"Email    : {email}\n"
        f"Téléphone: {telephone or 'Non renseigné'}\n"
        f"Sujet    : {sujet}\n"
        f"{'=' * 40}\n\n"
        f"{message}\n"
    )
    ok_interne = _envoyer_brevo(
        BREVO_SENDER_EMAIL, "Ascale",
        f"[Ascale Contact] {sujet} — {nom}",
        f"<pre>{corps_interne}</pre>",
        text_body=corps_interne,
    )

    corps_client = (
        f"Bonjour {nom},\n\n"
        f"Nous avons bien reçu votre message concernant : « {sujet} ».\n"
        f"Notre équipe vous répondra dans les 24h ouvrées.\n\n"
    )
    if reponse_chatbot:
        corps_client += (
            f"En attendant, voici une réponse automatique à votre demande :\n\n"
            f"{reponse_chatbot}\n\n"
            f"{'─' * 40}\n\n"
        )
    corps_client += (
        f"Votre message :\n{message}\n\n"
        f"Cordialement,\nL'équipe Ascale\n"
        f"📞 +212 5 22 XX XX XX | ✉️ contact@ascale.ma"
    )
    ok_client = _envoyer_brevo(
        email, nom,
        "Votre message a bien été reçu — Ascale",
        f"<pre>{corps_client}</pre>",
        text_body=corps_client,
    )

    return ok_interne and ok_client


def envoyer_facture_commande(commande, client, pdf_bytes: bytes) -> bool:
    """Envoie la facture PDF en pièce jointe au client + notification interne."""
    nom_fichier = f"facture_ascale_{commande.id:04d}.pdf"
    email_client = client.email if client else None

    ok_client = True
    if email_client:
        corps = (
            f"Bonjour {commande.client_nom},\n\n"
            f"Votre commande n°{commande.id} a bien été enregistrée.\n"
            f"Veuillez trouver ci-joint votre facture pro forma.\n\n"
            f"Récapitulatif :\n"
        )
        for l in commande.lignes:
            corps += f"  • {l.quantite} m² de {l.produit_nom} — {l.sous_total:.0f} MAD\n"
        corps += (
            f"\nTotal : {commande.total:.0f} MAD\n\n"
            "Notre équipe vous contactera sous 24h pour confirmer les modalités.\n"
            "Aucun débit n'a été effectué — règlement à la confirmation.\n\n"
            "Cordialement,\nL'équipe Ascale\n"
            "📞 +212 5 22 XX XX XX | ✉️ contact@ascale.ma"
        )
        ok_client = _envoyer_brevo(
            email_client, commande.client_nom,
            f"Votre commande Ascale n°{commande.id} — Facture pro forma",
            f"<pre>{corps}</pre>",
            text_body=corps,
            attachments=[(nom_fichier, pdf_bytes)],
        )

    produits_str = " | ".join(f"{l.quantite}m² {l.produit_nom}" for l in commande.lignes)
    corps_interne = (
        f"Nouvelle commande publique n°{commande.id}\n"
        f"Client : {commande.client_nom}\n"
        f"Email  : {email_client or 'Non renseigné'}\n"
        f"Tél.   : {client.telephone if client else 'Non renseigné'}\n"
        f"Adresse: {client.adresse if client else 'Non renseignée'}\n"
        f"Produits : {produits_str}\n"
        f"Total  : {commande.total:.0f} MAD\n"
    )
    ok_interne = _envoyer_brevo(
        BREVO_SENDER_EMAIL, "Ascale",
        f"[Ascale] Nouvelle commande n°{commande.id} — {commande.client_nom}",
        f"<pre>{corps_interne}</pre>",
        text_body=corps_interne,
        attachments=[(nom_fichier, pdf_bytes)],
    )

    return ok_client and ok_interne


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
