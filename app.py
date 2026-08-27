import csv
import json
import os
import re
from functools import wraps
from io import StringIO
from itertools import groupby

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
from flask_mail import Mail

import chatbot
import email_service
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

STATUTS_COMMANDE = ["Enregistrée", "En préparation", "Expédiée", "Livrée", "Annulée"]


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


def login_required(vue):
    @wraps(vue)
    def wrapper(*args, **kwargs):
        if not session.get("utilisateur_id"):
            flash("Merci de vous connecter pour accéder à cette page.", "error")
            return redirect(url_for("connexion", next=request.path))
        return vue(*args, **kwargs)

    return wrapper


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-ascale-2026")

    # Base de données SQLite (fichier local, persiste entre les redémarrages)
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "ascale.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["MAIL_SERVER"] = email_service.MAIL_SERVER
    app.config["MAIL_PORT"] = email_service.MAIL_PORT
    app.config["MAIL_USE_TLS"] = email_service.MAIL_USE_TLS
    app.config["MAIL_USERNAME"] = email_service.MAIL_USERNAME
    app.config["MAIL_PASSWORD"] = email_service.MAIL_PASSWORD
    app.config["MAIL_DEFAULT_SENDER"] = email_service.MAIL_DEFAULT_SENDER

    # Surcharge pour les tests (ex. base in-memory, mail supprimé)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.mail = Mail(app)

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

    # ---------- Commande publique ----------
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

            try:
                commande = store.creer_commande_publique(nom, email, telephone, lignes_demandees)
            except (StockInsuffisantError, ValueError) as exc:
                flash(str(exc), "error")
                return render_template("commander.html", produits=produits)

            return redirect(url_for("commande_confirmee", commande_id=commande.id))

        return render_template("commander.html", produits=produits)

    @app.route("/commande/confirmee/<int:commande_id>")
    def commande_confirmee(commande_id):
        commande = store.get_commande(commande_id)
        if commande is None:
            flash("Commande introuvable.", "error")
            return redirect(url_for("commander"))
        return render_template("commande_confirmee.html", commande=commande)

    # ---------- Gestion interne ----------
    @app.route("/gestion")
    def index():
        commandes = store.list_commandes()
        top = store.top_produits_commandes(5)
        sources = store.commandes_par_source()
        return render_template(
            "index.html",
            nb_produits=len(store.list_produits()),
            nb_clients=len(store.list_clients()),
            chiffre_affaires=store.chiffre_affaires(),
            dernieres_commandes=commandes[:5],
            nb_commandes_publiques=store.nb_commandes_publiques(),
            stock_faible=store.produits_stock_faible(),
            rupture=store.produits_rupture(),
            # JSON pour Chart.js (Jinja échappe, on double-encode)
            chart_top_noms=json.dumps([r.nom.rsplit(" ", 1)[-1] for r in top]),
            chart_top_qtes=json.dumps([float(r.total_qte) for r in top]),
            chart_sources_labels=json.dumps(list(sources.keys())),
            chart_sources_data=json.dumps(list(sources.values())),
        )

    # ---------- Produits ----------
    @app.route("/produits")
    def produits():
        return render_template("produits.html", produits=store.list_produits())

    @app.route("/produits/ajouter", methods=["POST"])
    def ajouter_produit():
        try:
            nom = request.form["nom"].strip()
            prix = float(request.form["prix"])
            stock = int(request.form["stock"])
            if not nom or prix < 0 or stock < 0:
                raise ValueError
        except (KeyError, ValueError):
            flash("Merci de renseigner un nom, un prix et un stock valides.", "error")
            return redirect(url_for("produits"))

        description = request.form.get("description", "").strip()
        store.add_produit(nom, prix, stock, description)
        flash(f"Produit « {nom} » ajouté.", "success")
        return redirect(url_for("produits"))

    @app.route("/produits/<int:produit_id>/modifier", methods=["GET", "POST"])
    def modifier_produit(produit_id):
        produit = store.get_produit(produit_id)
        if produit is None:
            flash("Produit introuvable.", "error")
            return redirect(url_for("produits"))

        if request.method == "POST":
            try:
                nom = request.form["nom"].strip()
                prix = float(request.form["prix"])
                stock = int(request.form["stock"])
                if not nom or prix < 0 or stock < 0:
                    raise ValueError
            except (KeyError, ValueError):
                flash("Merci de renseigner un nom, un prix et un stock valides.", "error")
                return redirect(url_for("modifier_produit", produit_id=produit_id))

            description = request.form.get("description", "").strip()
            store.update_produit(produit_id, nom, prix, stock, description)
            flash(f"Produit « {nom} » mis à jour.", "success")
            return redirect(url_for("produits"))

        return render_template("modifier_produit.html", produit=produit)

    @app.route("/produits/<int:produit_id>/supprimer", methods=["POST"])
    def supprimer_produit(produit_id):
        store.delete_produit(produit_id)
        flash("Produit supprimé.", "success")
        return redirect(url_for("produits"))

    # ---------- Clients ----------
    @app.route("/clients")
    def clients():
        return render_template("clients.html", clients=store.list_clients())

    @app.route("/clients/ajouter", methods=["POST"])
    def ajouter_client():
        nom = request.form.get("nom", "").strip()
        if not nom:
            flash("Le nom du client est obligatoire.", "error")
            return redirect(url_for("clients"))

        store.add_client(
            nom,
            request.form.get("email") or None,
            request.form.get("telephone") or None,
        )
        flash(f"Client « {nom} » ajouté.", "success")
        return redirect(url_for("clients"))

    @app.route("/clients/<int:client_id>/modifier", methods=["GET", "POST"])
    def modifier_client(client_id):
        client = store.get_client(client_id)
        if client is None:
            flash("Client introuvable.", "error")
            return redirect(url_for("clients"))

        if request.method == "POST":
            nom = request.form.get("nom", "").strip()
            if not nom:
                flash("Le nom du client est obligatoire.", "error")
                return redirect(url_for("modifier_client", client_id=client_id))

            store.update_client(
                client_id,
                nom,
                request.form.get("email") or None,
                request.form.get("telephone") or None,
            )
            flash(f"Client « {nom} » mis à jour.", "success")
            return redirect(url_for("clients"))

        return render_template("modifier_client.html", client=client)

    @app.route("/clients/<int:client_id>/supprimer", methods=["POST"])
    def supprimer_client(client_id):
        store.delete_client(client_id)
        flash("Client supprimé.", "success")
        return redirect(url_for("clients"))

    # ---------- Commandes (admin) ----------
    @app.route("/commandes")
    def commandes():
        return render_template(
            "commandes.html",
            commandes=store.list_commandes(),
            statuts=STATUTS_COMMANDE,
        )

    @app.route("/commandes/nouvelle", methods=["GET", "POST"])
    def nouvelle_commande():
        if request.method == "POST":
            try:
                client_id = int(request.form["client_id"])
            except (KeyError, ValueError):
                flash("Merci de choisir un client.", "error")
                return redirect(url_for("nouvelle_commande"))

            produit_ids = request.form.getlist("produit_id")
            quantites = request.form.getlist("quantite")

            lignes_demandees = []
            for produit_id, quantite in zip(produit_ids, quantites):
                if not produit_id or not quantite:
                    continue
                try:
                    lignes_demandees.append((int(produit_id), int(quantite)))
                except ValueError:
                    flash("Quantité invalide.", "error")
                    return redirect(url_for("nouvelle_commande"))

            try:
                commande = store.creer_commande(client_id, lignes_demandees)
            except (StockInsuffisantError, ValueError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("nouvelle_commande"))

            flash(f"Commande n°{commande.id} enregistrée pour {commande.client_nom}.", "success")
            return redirect(url_for("commandes"))

        return render_template(
            "nouvelle_commande.html",
            clients=store.list_clients(),
            produits=store.list_produits(),
        )

    @app.route("/commandes/<int:commande_id>/statut", methods=["POST"])
    def mettre_a_jour_statut(commande_id):
        nouveau_statut = request.form.get("statut", "").strip()
        if nouveau_statut not in STATUTS_COMMANDE:
            flash("Statut invalide.", "error")
        else:
            store.mettre_a_jour_statut_commande(commande_id, nouveau_statut)
            flash(f"Statut mis à jour : {nouveau_statut}.", "success")
        return redirect(url_for("commandes"))

    @app.route("/commandes/<int:commande_id>/supprimer", methods=["POST"])
    def supprimer_commande(commande_id):
        store.supprimer_commande(commande_id)
        flash("Commande supprimée, le stock a été recrédité.", "success")
        return redirect(url_for("commandes"))

    @app.route("/admin/commandes/export")
    def export_commandes_csv():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Date", "Client", "Produits", "Total (MAD)", "Statut", "Source"])
        for c in store.list_commandes():
            produits_str = " | ".join(
                f"{l.quantite}m² {l.produit_nom}" for l in c.lignes
            )
            writer.writerow([
                c.id,
                c.date.strftime("%d/%m/%Y %H:%M"),
                c.client_nom,
                produits_str,
                f"{c.total:.2f}",
                c.statut,
                c.source,
            ])
        return Response(
            "﻿" + output.getvalue(),  # BOM UTF-8 pour Excel
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=commandes_ascale.csv"},
        )

    @app.route("/admin/clients/export")
    def export_clients_csv():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Nom", "Email", "Téléphone", "Adresse"])
        for c in store.list_clients():
            writer.writerow([c.id, c.nom, c.email or "", c.telephone or "", c.adresse or ""])
        return Response(
            "﻿" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=clients_ascale.csv"},
        )

    # ---------- Chatbot ----------
    def _chatbot_repondre_et_stocker(message):
        conversation = session.get("chatbot_conversation", [])
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
        if message:
            _chatbot_repondre_et_stocker(message)
        return redirect(url_for("chatbot_page"))

    @app.route("/chatbot/widget/envoyer", methods=["POST"])
    def chatbot_widget_envoyer():
        message = request.form.get("message", "").strip()
        if not message:
            return {"erreur": "Message vide."}, 400
        reponse = _chatbot_repondre_et_stocker(message)
        return {"reponse": reponse}

    @app.route("/chatbot/reinitialiser", methods=["POST"])
    def chatbot_reinitialiser():
        session.pop("chatbot_conversation", None)
        if request.accept_mimetypes.best == "application/json":
            return {"ok": True}
        return redirect(url_for("chatbot_page"))

    @app.context_processor
    def injecter_widget_chatbot():
        return {"conversation_widget": session.get("chatbot_conversation", [])}

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
            app.mail, reservation, creneau
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
                app.mail, nom, email, telephone, sujet, message, reponse_bot
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

    # ---------- Connexion ----------
    @app.route("/connexion", methods=["GET", "POST"])
    def connexion():
        if request.method == "POST":
            email = request.form.get("email", "")
            mot_de_passe = request.form.get("mot_de_passe", "")
            utilisateur = store.verifier_identifiants(email, mot_de_passe)
            if utilisateur is None:
                flash("Email ou mot de passe incorrect.", "error")
                return redirect(url_for("connexion", next=request.args.get("next", "")))

            session["utilisateur_id"] = utilisateur.id
            flash(f"Bienvenue, {utilisateur.nom}.", "success")
            return redirect(request.args.get("next") or url_for("admin_reservations"))

        return render_template("connexion.html")

    @app.route("/deconnexion", methods=["POST"])
    def deconnexion():
        session.pop("utilisateur_id", None)
        flash("Vous êtes déconnecté.", "success")
        return redirect(url_for("index"))

    # ---------- Admin réservations ----------
    @app.route("/admin/reservations")
    @login_required
    def admin_reservations():
        creneaux_par_id = {c.id: c for c in store.list_tous_creneaux()}
        return render_template(
            "admin_reservations.html",
            reservations=store.list_reservations(),
            creneaux_par_id=creneaux_par_id,
        )

    @app.route("/admin/reservations/<int:reservation_id>/annuler", methods=["POST"])
    @login_required
    def admin_reservation_annuler(reservation_id):
        store.annuler_reservation(reservation_id)
        flash("Réservation annulée, le créneau est de nouveau disponible.", "success")
        return redirect(url_for("admin_reservations"))

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
    app.run(debug=True)
