import json
import os
import re
import socket
import urllib.parse
import urllib.request
from io import BytesIO
from itertools import groupby

from dotenv import load_dotenv

load_dotenv()

# Filet de sécurité : toute connexion réseau sans timeout explicite (il ne
# devrait plus y en avoir depuis le passage des emails à l'API Brevo, mais
# mieux vaut prévenir) échoue proprement en 10s au lieu de bloquer la requête
# jusqu'au timeout du worker gunicorn (SIGABRT -> 500).
socket.setdefaulttimeout(10)

from flask import Flask, Response, flash, redirect, render_template, request, send_file, session, url_for

import chatbot
import email_service
import facture_service
import whatsapp_config
from database import db
from models import CreneauIndisponibleError, Store, StockInsuffisantError, seed

TAILLE_MAX_CONVERSATION_CHATBOT = 30

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

def formater_date_fr(valeur):
    return f"{JOURS_FR[valeur.weekday()].capitalize()} {valeur.day} {MOIS_FR[valeur.month - 1]}"


def classe_swatch(nom):
    nom_lower = nom.lower()
    if "noir" in nom_lower:
        return "pub-swatch-noir"
    if "onyx" in nom_lower:
        return "pub-swatch-onyx"
    if "vert" in nom_lower:
        return "pub-swatch-vert"
    if "rose" in nom_lower:
        return "pub-swatch-rose"
    if "granit" in nom_lower:
        return "pub-swatch-granit"
    if "beige" in nom_lower or "travertin" in nom_lower or "crema" in nom_lower:
        return "pub-swatch-beige"
    return "pub-swatch-blanc"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-ascale-2026")

    # Base de données SQLite (fichier local, persiste entre les redémarrages)
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "ascale.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Surcharge pour les tests (ex. base in-memory)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    app.jinja_env.filters["date_fr"] = formater_date_fr
    app.jinja_env.filters["swatch"] = classe_swatch

    with app.app_context():
        db.create_all()
        app.store = Store(db)
        seed(app.store)

    register_routes(app)
    return app


def register_routes(app):
    store = app.store

    # ---------- Site public ----------
    @app.route("/")
    def accueil():
        tous_produits = store.list_produits()
        noms_phares = [
            "Marbre Blanc de Carrare",
            "Onyx Blanc translucide",
            "Marbre Noir Marquina",
            "Marbre Vert Guatemala",
        ]
        produits_par_nom = {p.nom: p for p in tous_produits}
        produits_phares = [produits_par_nom[nom] for nom in noms_phares if nom in produits_par_nom]
        if not produits_phares:
            produits_phares = tous_produits[:4]
        return render_template("accueil.html", produits_phares=produits_phares)

    @app.route("/nos-materiaux")
    def nos_materiaux():
        return render_template("nos_materiaux.html", produits=store.list_produits())

    # ---------- Commande publique — étape 1 : sélection produits ----------
    @app.route("/commander", methods=["GET", "POST"])
    def commander():
        produits = store.list_produits()

        if request.method == "POST":
            nom = request.form.get("nom", "").strip()
            email = request.form.get("email", "").strip()
            telephone = request.form.get("telephone", "").strip()

            if not nom or not telephone or not email:
                flash("Merci de renseigner votre nom, téléphone et email.", "error")
                return render_template("commander.html", produits=produits)

            if not EMAIL_REGEX.match(email):
                flash("Adresse email invalide.", "error")
                return render_template("commander.html", produits=produits)

            produit_ids = request.form.getlist("produit_id")
            quantites = request.form.getlist("quantite")

            lignes_demandees = []
            for pid, qty in zip(produit_ids, quantites):
                if not pid or not qty:
                    continue
                try:
                    q = int(qty)
                    if q > 0:
                        lignes_demandees.append((int(pid), q))
                except ValueError:
                    flash("Quantité invalide.", "error")
                    return render_template("commander.html", produits=produits)

            if not lignes_demandees:
                flash("Sélectionnez au moins un produit avec une quantité.", "error")
                return render_template("commander.html", produits=produits)

            # Vérifier stock avant de stocker en session
            for pid, qty in lignes_demandees:
                p = store.get_produit(pid)
                if p is None or p.stock < qty:
                    nom_p = p.nom if p else f"Produit #{pid}"
                    flash(f"Stock insuffisant pour {nom_p}.", "error")
                    return render_template("commander.html", produits=produits)

            # Calculer le total pour affichage
            total = sum(
                store.get_produit(pid).prix * qty
                for pid, qty in lignes_demandees
                if store.get_produit(pid)
            )

            session["panier"] = {
                "nom": nom,
                "email": email,
                "telephone": telephone,
                "lignes": lignes_demandees,
                "total": total,
            }
            return redirect(url_for("paiement"))

        return render_template("commander.html", produits=produits)

    # ---------- Commande publique — étape 2 : adresse + paiement ----------
    MODES_PAIEMENT = ["carte", "virement", "especes"]

    def _valider_adresse_nominatim(adresse: str) -> bool:
        """Vérifie via Nominatim que l'adresse existe. Retourne True si trouvée ou si API indisponible."""
        try:
            params = urllib.parse.urlencode({"q": adresse, "format": "json", "limit": "1"})
            url = f"https://nominatim.openstreetmap.org/search?{params}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Ascale-Marbre/1.0 contact@ascale.ma"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return len(data) > 0
        except Exception:
            return True  # Ne pas bloquer si l'API est indisponible

    @app.route("/paiement", methods=["GET", "POST"])
    def paiement():
        panier = session.get("panier")
        if not panier:
            flash("Votre panier est vide. Veuillez sélectionner des produits.", "error")
            return redirect(url_for("commander"))

        produits_map = {p.id: p for p in store.list_produits()}
        lignes_recap = [
            {
                "nom": produits_map[pid].nom if pid in produits_map else f"Produit #{pid}",
                "prix": produits_map[pid].prix if pid in produits_map else 0,
                "quantite": qty,
                "sous_total": produits_map[pid].prix * qty if pid in produits_map else 0,
            }
            for pid, qty in panier["lignes"]
        ]

        if request.method == "POST":
            adresse = request.form.get("adresse", "").strip()
            mode_paiement = request.form.get("mode_paiement", "").strip()

            if not adresse:
                flash("L'adresse de livraison est obligatoire.", "error")
                return render_template(
                    "paiement.html", panier=panier, lignes_recap=lignes_recap,
                    modes=MODES_PAIEMENT
                )

            if mode_paiement not in MODES_PAIEMENT:
                flash("Mode de paiement invalide.", "error")
                return render_template(
                    "paiement.html", panier=panier, lignes_recap=lignes_recap,
                    modes=MODES_PAIEMENT
                )

            # Validation adresse via Nominatim (non bloquante)
            adresse_valide = _valider_adresse_nominatim(adresse)
            if not adresse_valide:
                flash(
                    "Adresse introuvable — veuillez vérifier ou sélectionner depuis la liste de suggestions.",
                    "error"
                )
                return render_template(
                    "paiement.html", panier=panier, lignes_recap=lignes_recap,
                    modes=MODES_PAIEMENT
                )

            # Créer la commande
            try:
                commande = store.creer_commande_publique(
                    panier["nom"], panier["email"], panier["telephone"],
                    [tuple(l) for l in panier["lignes"]]
                )
            except (StockInsuffisantError, ValueError) as exc:
                flash(str(exc), "error")
                return render_template(
                    "paiement.html", panier=panier, lignes_recap=lignes_recap,
                    modes=MODES_PAIEMENT
                )

            # Mettre à jour l'adresse du client
            client = store.get_client(commande.client_id)
            if client:
                from database import db as _db
                client.adresse = adresse
                _db.session.commit()

            # Générer et envoyer la facture PDF
            try:
                pdf_bytes = facture_service.generer_facture_pdf(commande, client)
                email_service.envoyer_facture_commande(commande, client, pdf_bytes)
            except Exception:
                pdf_bytes = None

            # Stocker les bytes PDF en session (pour téléchargement immédiat)
            if pdf_bytes:
                session["facture_pdf"] = pdf_bytes.hex()
                session["facture_id"] = commande.id

            session.pop("panier", None)
            return redirect(url_for("commande_recu", commande_id=commande.id))

        return render_template(
            "paiement.html", panier=panier, lignes_recap=lignes_recap, modes=MODES_PAIEMENT
        )

    # ---------- Commande publique — étape 3 : reçu ----------
    @app.route("/commande/recu/<int:commande_id>")
    def commande_recu(commande_id):
        commande = store.get_commande(commande_id)
        if commande is None:
            flash("Commande introuvable.", "error")
            return redirect(url_for("commander"))
        client = store.get_client(commande.client_id)
        return render_template("recu.html", commande=commande, client=client)

    @app.route("/commande/facture/<int:commande_id>.pdf")
    def telecharger_facture(commande_id):
        commande = store.get_commande(commande_id)
        if commande is None:
            flash("Commande introuvable.", "error")
            return redirect(url_for("commander"))
        client = store.get_client(commande.client_id)
        try:
            pdf_bytes = facture_service.generer_facture_pdf(commande, client)
        except Exception:
            flash("Erreur lors de la génération de la facture.", "error")
            return redirect(url_for("commande_recu", commande_id=commande_id))
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"facture_ascale_{commande_id:04d}.pdf",
        )

    @app.route("/commande/confirmee/<int:commande_id>")
    def commande_confirmee(commande_id):
        commande = store.get_commande(commande_id)
        if commande is None:
            flash("Commande introuvable.", "error")
            return redirect(url_for("commander"))
        return render_template("commande_confirmee.html", commande=commande)

    # ---------- Chatbot ----------
    def _chatbot_repondre_et_stocker(message, mode="specialise"):
        conversation = session.get("chatbot_conversation", [])
        if mode == "libre":
            reponse = chatbot.repondre_libre(store, message)
        else:
            reponse = chatbot.repondre(store, message)
        conversation.append({"role": "client", "texte": message})
        conversation.append({"role": "bot", "texte": reponse})
        session["chatbot_conversation"] = conversation[-TAILLE_MAX_CONVERSATION_CHATBOT:]
        return reponse

    @app.route("/chatbot")
    def chatbot_page():
        conversation = session.get("chatbot_conversation", [])
        return render_template(
            "chatbot.html", conversation=conversation, exemples=chatbot.EXEMPLES
        )

    @app.route("/chatbot/envoyer", methods=["POST"])
    def chatbot_envoyer():
        message = request.form.get("message", "").strip()
        mode = session.get("chatbot_mode", "specialise")
        if message:
            _chatbot_repondre_et_stocker(message, mode)
        return redirect(url_for("chatbot_page"))

    @app.route("/chatbot/widget/envoyer", methods=["POST"])
    def chatbot_widget_envoyer():
        message = request.form.get("message", "").strip()
        if not message:
            return {"erreur": "Message vide."}, 400
        mode = session.get("chatbot_mode", "specialise")
        reponse = _chatbot_repondre_et_stocker(message, mode)
        return {"reponse": reponse}

    @app.route("/chatbot/reinitialiser", methods=["POST"])
    def chatbot_reinitialiser():
        session.pop("chatbot_conversation", None)
        if request.accept_mimetypes.best == "application/json":
            return {"ok": True}
        return redirect(url_for("chatbot_page"))

    @app.route("/chatbot/mode/<mode>", methods=["POST"])
    def chatbot_changer_mode(mode):
        if mode in ("specialise", "libre"):
            session["chatbot_mode"] = mode
            session.pop("chatbot_conversation", None)
        if request.accept_mimetypes.best == "application/json":
            return {"mode": session.get("chatbot_mode", "specialise")}
        return redirect(url_for("chatbot_page"))

    @app.context_processor
    def injecter_widget_chatbot():
        return {
            "conversation_widget": session.get("chatbot_conversation", []),
            "chatbot_mode": session.get("chatbot_mode", "specialise"),
        }

    # ---------- Réservation ----------
    @app.route("/reservation")
    def reservation_page():
        creneaux_par_jour = [
            (jour, list(groupe))
            for jour, groupe in groupby(store.list_creneaux(), key=lambda c: c.date_creneau)
        ]
        return render_template("reservation.html", creneaux_par_jour=creneaux_par_jour)

    @app.route("/reservation/confirmer", methods=["POST"])
    def reservation_confirmer():
        try:
            creneau_id = int(request.form["creneau_id"])
        except (KeyError, ValueError):
            flash("Merci de choisir un créneau.", "error")
            return redirect(url_for("reservation_page"))

        nom = request.form.get("nom", "").strip()
        telephone = request.form.get("telephone", "").strip()
        email = request.form.get("email", "").strip()
        if not nom or not telephone or not email:
            flash("Merci de renseigner votre nom, téléphone et email.", "error")
            return redirect(url_for("reservation_page"))
        if not EMAIL_REGEX.match(email):
            flash("Merci de renseigner une adresse email valide.", "error")
            return redirect(url_for("reservation_page"))

        try:
            reservation = store.reserver_creneau(creneau_id, nom, telephone, email)
        except CreneauIndisponibleError as exc:
            flash(str(exc), "error")
            return redirect(url_for("reservation_page"))

        creneau = store.get_creneau(reservation.creneau_id)
        reservation.email_envoye = email_service.envoyer_confirmation_reservation(
            reservation, creneau
        )
        from database import db as _db
        _db.session.commit()

        return redirect(url_for("reservation_confirmee", reservation_id=reservation.id))

    @app.route("/reservation/confirmee/<int:reservation_id>")
    def reservation_confirmee(reservation_id):
        reservation = store.get_reservation(reservation_id)
        if reservation is None:
            flash("Réservation introuvable.", "error")
            return redirect(url_for("reservation_page"))
        return render_template(
            "reservation_confirmee.html",
            reservation=reservation,
            creneau=store.get_creneau(reservation.creneau_id),
        )

    # ---------- Contact (formulaire + email auto) ----------
    SUJETS_CONTACT = [
        "Demande de devis",
        "Renseignement sur un produit",
        "Suivi de commande",
        "Réservation showroom",
        "Partenariat / Architecture",
        "Autre",
    ]

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            nom = request.form.get("nom", "").strip()
            email = request.form.get("email", "").strip()
            telephone = request.form.get("telephone", "").strip()
            sujet = request.form.get("sujet", "").strip()
            message = request.form.get("message", "").strip()

            if not nom or not email or not message:
                flash("Merci de renseigner votre nom, email et message.", "error")
                return render_template("contact.html", sujets=SUJETS_CONTACT)
            if not EMAIL_REGEX.match(email):
                flash("Adresse email invalide.", "error")
                return render_template("contact.html", sujets=SUJETS_CONTACT)

            # Le chatbot tente de pré-répondre au message
            reponse_bot = chatbot.repondre(store, message)
            # N'inclure la réponse bot que si elle n'est pas le fallback
            if "Je n'ai pas compris" in reponse_bot:
                reponse_bot = None

            email_envoye = email_service.envoyer_contact(
                nom, email, telephone, sujet, message, reponse_bot
            )

            if email_envoye:
                flash(
                    "Votre message a bien été envoyé ! Vous recevrez un accusé de réception par email.",
                    "success",
                )
            else:
                flash(
                    "Message enregistré. Nos serveurs email ne sont pas encore configurés — "
                    "contactez-nous directement au +212 5 22 XX XX XX.",
                    "info",
                )
            return redirect(url_for("contact"))

        return render_template("contact.html", sujets=SUJETS_CONTACT)

    # ---------- Webhook WhatsApp Business ----------
    @app.route("/webhook/whatsapp", methods=["GET"])
    def whatsapp_verifier():
        mode = request.args.get("hub.mode")
        jeton = request.args.get("hub.verify_token")
        defi = request.args.get("hub.challenge", "")
        if (
            whatsapp_config.WHATSAPP_VERIFY_TOKEN
            and mode == "subscribe"
            and jeton == whatsapp_config.WHATSAPP_VERIFY_TOKEN
        ):
            return defi, 200
        return "Vérification échouée.", 403

    @app.route("/webhook/whatsapp", methods=["POST"])
    def whatsapp_recevoir():
        if not whatsapp_config.api_configuree():
            return "", 200

        data = request.get_json(silent=True) or {}
        try:
            entry = data["entry"][0]["changes"][0]["value"]
            msg = entry["messages"][0]
            expediteur = msg["from"]
            texte = msg["text"]["body"]
        except (KeyError, IndexError):
            return "", 200

        reponse = chatbot.repondre(store, texte, expediteur=expediteur)
        whatsapp_config.envoyer_message(expediteur, reponse)
        return "", 200


app = create_app()

if __name__ == "__main__":
    # debug=True uniquement en local, sur demande explicite (FLASK_DEBUG=true dans .env).
    # En prod, gunicorn importe directement l'objet `app` ci-dessus et ne passe
    # jamais par ce bloc — mais on évite quand même que debug=True soit la valeur
    # par défaut si jamais `python app.py` est lancé directement sur un serveur.
    debug = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
    app.run(debug=debug)
