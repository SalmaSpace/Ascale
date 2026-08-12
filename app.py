from flask import Flask, flash, redirect, render_template, request, url_for

from models import Store, StockInsuffisantError, seed


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"

    app.store = Store()
    seed(app.store)

    register_routes(app)
    return app


def register_routes(app):
    store = app.store

    @app.route("/")
    def index():
        commandes = store.list_commandes()
        return render_template(
            "index.html",
            nb_produits=len(store.list_produits()),
            nb_clients=len(store.list_clients()),
            chiffre_affaires=store.chiffre_affaires(),
            dernieres_commandes=commandes[:5],
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

    # ---------- Commandes ----------
    @app.route("/commandes")
    def commandes():
        return render_template("commandes.html", commandes=store.list_commandes())

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

    @app.route("/commandes/<int:commande_id>/supprimer", methods=["POST"])
    def supprimer_commande(commande_id):
        store.supprimer_commande(commande_id)
        flash("Commande supprimée, le stock a été recrédité.", "success")
        return redirect(url_for("commandes"))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
