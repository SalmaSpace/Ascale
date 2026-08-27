"""Service layer — Store remplace le stockage en mémoire par SQLAlchemy (SQLite).

L'API publique de Store est conservée à l'identique : les routes de app.py
n'ont pas besoin de changer. Seul le backend de persistance change.
"""

from werkzeug.security import check_password_hash, generate_password_hash


class StockInsuffisantError(Exception):
    """Levée quand une commande demande plus de stock que disponible."""


class CreneauIndisponibleError(Exception):
    """Levée quand on tente de réserver un créneau inexistant ou déjà pris."""


class Store:
    """Accès aux données via SQLAlchemy (remplace l'ancien stockage en mémoire)."""

    def __init__(self, db):
        self._db = db

    # ---------- Clients ----------
    def list_clients(self):
        from database import Client
        return Client.query.order_by(Client.nom).all()

    def get_client(self, client_id):
        from database import Client
        return Client.query.get(client_id)

    def find_client_by_email(self, email):
        from database import Client
        return Client.query.filter_by(email=(email or "").strip().lower()).first()

    def add_client(self, nom, email=None, telephone=None, adresse=None):
        from database import Client
        client = Client(
            nom=nom,
            email=(email.strip().lower() if email else None),
            telephone=telephone,
            adresse=adresse,
        )
        self._db.session.add(client)
        self._db.session.commit()
        return client

    def update_client(self, client_id, nom, email=None, telephone=None, adresse=None):
        from database import Client
        client = Client.query.get(client_id)
        if client is None:
            return None
        client.nom = nom
        client.email = email
        client.telephone = telephone
        client.adresse = adresse
        self._db.session.commit()
        return client

    def delete_client(self, client_id):
        from database import Client
        client = Client.query.get(client_id)
        if client:
            self._db.session.delete(client)
            self._db.session.commit()

    # ---------- Produits ----------
    def list_produits(self):
        from database import Produit
        return Produit.query.order_by(Produit.nom).all()

    def get_produit(self, produit_id):
        from database import Produit
        return Produit.query.get(produit_id)

    def add_produit(self, nom, prix, stock, description="", categorie_id=None, seuil_alerte=10):
        from database import Produit
        produit = Produit(
            nom=nom,
            prix=prix,
            stock=stock,
            description=description,
            categorie_id=categorie_id,
            seuil_alerte=seuil_alerte,
        )
        self._db.session.add(produit)
        self._db.session.commit()
        return produit

    def update_produit(self, produit_id, nom, prix, stock, description=""):
        from database import Produit
        produit = Produit.query.get(produit_id)
        if produit is None:
            return None
        produit.nom = nom
        produit.prix = prix
        produit.stock = stock
        produit.description = description
        self._db.session.commit()
        return produit

    def delete_produit(self, produit_id):
        from database import Produit
        produit = Produit.query.get(produit_id)
        if produit:
            self._db.session.delete(produit)
            self._db.session.commit()

    # ---------- Catégories ----------
    def list_categories(self):
        from database import Categorie
        return Categorie.query.order_by(Categorie.nom).all()

    def add_categorie(self, nom):
        from database import Categorie
        cat = Categorie(nom=nom)
        self._db.session.add(cat)
        self._db.session.commit()
        return cat

    def list_produits_par_categorie(self, categorie_nom):
        from database import Produit, Categorie
        cat = Categorie.query.filter(Categorie.nom.ilike(f"%{categorie_nom}%")).first()
        if cat is None:
            return []
        return Produit.query.filter_by(categorie_id=cat.id).order_by(Produit.nom).all()

    # ---------- Commandes ----------
    def list_commandes(self):
        from database import Commande
        return Commande.query.order_by(Commande.date.desc()).all()

    def get_commande(self, commande_id):
        from database import Commande
        return Commande.query.get(commande_id)

    def creer_commande(self, client_id, lignes_demandees, source="admin"):
        """Crée une commande et décrémente le stock des produits commandés.

        Toute la commande est validée avant d'appliquer le moindre changement
        de stock, pour éviter une décrémentation partielle en cas d'erreur.
        """
        from database import Client, Produit, Commande, LigneCommande

        client = Client.query.get(client_id)
        if client is None:
            raise ValueError("Client introuvable.")

        lignes_validees = []
        for produit_id, quantite in lignes_demandees:
            produit = Produit.query.get(produit_id)
            if produit is None:
                raise ValueError("Produit introuvable.")
            if quantite <= 0:
                raise ValueError(f"Quantité invalide pour « {produit.nom} ».")
            if quantite > produit.stock:
                raise StockInsuffisantError(
                    f"Stock insuffisant pour « {produit.nom} » "
                    f"(disponible : {produit.stock} m²)."
                )
            lignes_validees.append((produit, quantite))

        if not lignes_validees:
            raise ValueError("Ajoutez au moins un article à la commande.")

        commande = Commande(
            client_id=client.id,
            client_nom=client.nom,
            source=source,
            statut="Enregistrée",
        )
        self._db.session.add(commande)
        self._db.session.flush()  # obtenir commande.id sans commit

        for produit, quantite in lignes_validees:
            ligne = LigneCommande(
                commande_id=commande.id,
                produit_id=produit.id,
                produit_nom=produit.nom,
                quantite=quantite,
                prix_unitaire=produit.prix,
            )
            self._db.session.add(ligne)
            produit.stock -= quantite

        self._db.session.commit()
        return commande

    def creer_commande_publique(self, nom, email, telephone, lignes_demandees):
        """Crée ou retrouve le client puis passe la commande (flux public).

        Cherche d'abord un client existant par email pour éviter les doublons.
        """
        client = self.find_client_by_email(email)
        if client is None:
            client = self.add_client(nom, email, telephone)
        else:
            # Mise à jour du nom/téléphone si déjà client
            if client.nom != nom:
                client.nom = nom
            if telephone and not client.telephone:
                client.telephone = telephone
            self._db.session.commit()

        return self.creer_commande(client.id, lignes_demandees, source="public")

    def supprimer_commande(self, commande_id):
        """Supprime une commande et recrédite le stock des produits concernés."""
        from database import Commande, Produit

        commande = Commande.query.get(commande_id)
        if commande is None:
            return
        for ligne in commande.lignes:
            produit = Produit.query.get(ligne.produit_id)
            if produit is not None:
                produit.stock += ligne.quantite
        self._db.session.delete(commande)
        self._db.session.commit()

    def mettre_a_jour_statut_commande(self, commande_id, nouveau_statut):
        from database import Commande
        commande = Commande.query.get(commande_id)
        if commande is None:
            return None
        commande.statut = nouveau_statut
        self._db.session.commit()
        return commande

    # ---------- Tableau de bord ----------
    def chiffre_affaires(self):
        from database import Commande
        commandes = Commande.query.all()
        return sum(c.total for c in commandes)

    def nb_commandes_publiques(self):
        from database import Commande
        return Commande.query.filter_by(source="public").count()

    def produits_stock_faible(self):
        """Produits dont le stock est bas mais pas nul (sous le seuil d'alerte)."""
        from database import Produit
        return Produit.query.filter(
            Produit.stock > 0, Produit.stock <= Produit.seuil_alerte
        ).order_by(Produit.stock).all()

    def produits_rupture(self):
        """Produits à stock zéro."""
        from database import Produit
        return Produit.query.filter(Produit.stock == 0).all()

    def top_produits_commandes(self, limit=5):
        """Top produits par quantité totale commandée (pour graphique)."""
        from database import LigneCommande, Produit
        from sqlalchemy import func
        return (
            self._db.session.query(
                Produit.nom,
                func.sum(LigneCommande.quantite).label("total_qte"),
                func.sum(LigneCommande.quantite * LigneCommande.prix_unitaire).label("total_ca"),
            )
            .join(LigneCommande, Produit.id == LigneCommande.produit_id)
            .group_by(Produit.id, Produit.nom)
            .order_by(func.sum(LigneCommande.quantite).desc())
            .limit(limit)
            .all()
        )

    def commandes_par_source(self):
        """Nombre de commandes par source (admin/public)."""
        from database import Commande
        from sqlalchemy import func
        rows = (
            self._db.session.query(Commande.source, func.count(Commande.id))
            .group_by(Commande.source)
            .all()
        )
        return {src: nb for src, nb in rows}

    # ---------- Créneaux & réservations ----------
    def list_creneaux(self):
        """Créneaux disponibles uniquement (pour la page de réservation publique)."""
        from database import Creneau
        return (
            Creneau.query
            .filter_by(disponible=True)
            .order_by(Creneau.date_creneau, Creneau.heure_debut)
            .all()
        )

    def list_tous_creneaux(self):
        """Tous les créneaux (pour l'interface admin)."""
        from database import Creneau
        return Creneau.query.order_by(Creneau.date_creneau, Creneau.heure_debut).all()

    def get_creneau(self, creneau_id):
        from database import Creneau
        return Creneau.query.get(creneau_id)

    def add_creneau(self, date_creneau, heure_debut, heure_fin):
        from database import Creneau
        creneau = Creneau(
            date_creneau=date_creneau,
            heure_debut=heure_debut,
            heure_fin=heure_fin,
        )
        self._db.session.add(creneau)
        self._db.session.commit()
        return creneau

    def list_reservations(self):
        from database import Reservation
        return Reservation.query.order_by(Reservation.date_reservation.desc()).all()

    def get_reservation(self, reservation_id):
        from database import Reservation
        return Reservation.query.get(reservation_id)

    def reserver_creneau(self, creneau_id, client_nom, client_telephone, client_email):
        """Réserve un créneau en appliquant la contrainte 0,1 du MCD."""
        from database import Creneau, Reservation

        creneau = Creneau.query.get(creneau_id)
        if creneau is None:
            raise CreneauIndisponibleError("Ce créneau n'existe pas.")
        if not creneau.disponible:
            raise CreneauIndisponibleError(
                "Ce créneau vient d'être réservé. Merci d'en choisir un autre."
            )

        reservation = Reservation(
            creneau_id=creneau.id,
            client_nom=client_nom,
            client_telephone=client_telephone,
            client_email=client_email,
        )
        creneau.disponible = False
        self._db.session.add(reservation)
        self._db.session.commit()
        return reservation

    def annuler_reservation(self, reservation_id):
        from database import Reservation, Creneau

        reservation = Reservation.query.get(reservation_id)
        if reservation is None:
            return
        creneau = Creneau.query.get(reservation.creneau_id)
        if creneau is not None:
            creneau.disponible = True
        self._db.session.delete(reservation)
        self._db.session.commit()

    # ---------- Utilisateurs ----------
    def add_utilisateur(self, nom, email, mot_de_passe, role="gestionnaire"):
        from database import Utilisateur

        utilisateur = Utilisateur(
            nom=nom,
            email=email.strip().lower(),
            mot_de_passe_hash=generate_password_hash(mot_de_passe),
            role=role,
        )
        self._db.session.add(utilisateur)
        self._db.session.commit()
        return utilisateur

    def get_utilisateur(self, utilisateur_id):
        from database import Utilisateur
        return Utilisateur.query.get(utilisateur_id)

    def verifier_identifiants(self, email, mot_de_passe):
        from database import Utilisateur

        email = (email or "").strip().lower()
        utilisateur = Utilisateur.query.filter_by(email=email).first()
        if utilisateur and check_password_hash(utilisateur.mot_de_passe_hash, mot_de_passe):
            return utilisateur
        return None


def seed(store: Store) -> None:
    """Peuple la base avec des données de démonstration (négoce de marbre luxe).

    Appelé uniquement si la base est vide (Client.count == 0).
    """
    from database import Client

    if Client.query.count() > 0:
        return  # déjà seedé, on ne recrée pas les données

    # --- Catégories ---
    cat_marbre    = store.add_categorie("Marbre")
    cat_granit    = store.add_categorie("Granit")
    cat_onyx      = store.add_categorie("Onyx")
    cat_travertin = store.add_categorie("Travertin")

    # --- Clients ---
    c1 = store.add_client("Karim Benjelloun",          "karim.benjelloun@gmail.com",       "0661234567")
    c2 = store.add_client("Atelier Zellige Design",    "contact@atelierzellige.ma",        "0522334455")
    c3 = store.add_client("Nadia El Fassi",            "nadia.elfassi@outlook.com",        "0662345678")
    c4 = store.add_client("Batico Construction",       "contact@batico-construction.ma",   "0522556677")
    c5 = store.add_client("Riad Dar Yasmine",          "reservation@riaddaryasmine.ma",    "0524123456")
    c6 = store.add_client("Hammou Architecte",         "h.architecte@gmail.com",           "0670112233")
    c7 = store.add_client("Immo Prestige Casablanca",  "achats@immo-prestige.ma",          "0522778899")

    # ── MARBRE (10 références) ──────────────────────────────────────────────
    p1 = store.add_produit(
        "Marbre Blanc de Carrare",    950.0, 85,
        "Italie — dalle premium pour sol, plan de travail et revêtement mural.",
        categorie_id=cat_marbre.id, seuil_alerte=15,
    )
    p2 = store.add_produit(
        "Marbre Noir Marquina",       1100.0, 60,
        "Espagne — veines blanches sur fond noir intense, très recherché.",
        categorie_id=cat_marbre.id, seuil_alerte=10,
    )
    p3 = store.add_produit(
        "Marbre Beige Crema Marfil",  420.0, 200,
        "Espagne — teinte beige chaleureuse, parfait pour sol et escalier.",
        categorie_id=cat_marbre.id, seuil_alerte=30,
    )
    store.add_produit(
        "Marbre Vert Guatemala",      1380.0, 30,
        "Inde — veines vertes profondes, plan de travail et sol d'exception.",
        categorie_id=cat_marbre.id, seuil_alerte=5,
    )
    store.add_produit(
        "Marbre Rose Portugal",       720.0, 55,
        "Portugal — teinte rosée délicate pour sol et habillage mural.",
        categorie_id=cat_marbre.id, seuil_alerte=8,
    )
    store.add_produit(
        "Marbre Blanc Thassos",       880.0, 40,
        "Grèce — blanc immaculé pur, translucidité naturelle, salle de bain haut de gamme.",
        categorie_id=cat_marbre.id, seuil_alerte=8,
    )
    store.add_produit(
        "Marbre Gris Bardiglio",      680.0, 65,
        "Italie — gris ardoisé avec veinures fines, ambiance contemporaine.",
        categorie_id=cat_marbre.id, seuil_alerte=10,
    )
    store.add_produit(
        "Marbre Jaune Giallo Siena",  560.0, 50,
        "Italie — jaune doré et ocre, apporte chaleur et caractère à l'espace.",
        categorie_id=cat_marbre.id, seuil_alerte=8,
    )
    store.add_produit(
        "Marbre Emperador Dark",      750.0, 45,
        "Espagne — brun profond veiné de blanc, très élégant pour plan de travail.",
        categorie_id=cat_marbre.id, seuil_alerte=8,
    )
    store.add_produit(
        "Marbre Blanc Local",         250.0, 300,
        "Maroc — marbre local économique, idéal pour grands chantiers et revêtements muraux.",
        categorie_id=cat_marbre.id, seuil_alerte=40,
    )

    # ── GRANIT (4 références) ───────────────────────────────────────────────
    p_g1 = store.add_produit(
        "Granit Noir Absolu",         550.0, 110,
        "Inde — noir intense et uniforme, plan de travail cuisine, sol à fort trafic.",
        categorie_id=cat_granit.id, seuil_alerte=15,
    )
    store.add_produit(
        "Granit Gris Baltic Brown",   480.0, 90,
        "Finlande — gris tacheté brun-or, robuste et résistant aux intempéries.",
        categorie_id=cat_granit.id, seuil_alerte=12,
    )
    store.add_produit(
        "Granit Rouge India",         520.0, 75,
        "Inde — rouge vif avec cristaux noirs et gris, sol et façade extérieure.",
        categorie_id=cat_granit.id, seuil_alerte=10,
    )
    store.add_produit(
        "Granit Bleu Bahia",          780.0, 35,
        "Brésil — pièce unique aux reflets bleus irisés, comptoir et revêtement prestige.",
        categorie_id=cat_granit.id, seuil_alerte=5,
    )

    # ── ONYX (3 références) ─────────────────────────────────────────────────
    p4 = store.add_produit(
        "Onyx Blanc Translucide",     2200.0, 25,
        "Iran — revêtement mural rétroéclairé et éléments décoratifs, forte translucidité.",
        categorie_id=cat_onyx.id, seuil_alerte=5,
    )
    store.add_produit(
        "Onyx Vert Malachite",        2800.0, 18,
        "Iran — vert profond marbré, panneaux décoratifs et surfaces de prestige.",
        categorie_id=cat_onyx.id, seuil_alerte=3,
    )
    store.add_produit(
        "Onyx Miel Doré",             1800.0, 22,
        "Pakistan — teintes miel et ambre rétroéclairées, comptoir et réception hôtelière.",
        categorie_id=cat_onyx.id, seuil_alerte=4,
    )

    # ── TRAVERTIN (3 références) ────────────────────────────────────────────
    p6 = store.add_produit(
        "Travertin Beige",            280.0, 200,
        "Turquie — sol intérieur et extérieur, terrasse, salle de bain, très abordable.",
        categorie_id=cat_travertin.id, seuil_alerte=30,
    )
    store.add_produit(
        "Travertin Noce",             320.0, 160,
        "Turquie — teinte brun-noyer chaleureuse, sol et revêtement mural contemporain.",
        categorie_id=cat_travertin.id, seuil_alerte=25,
    )
    store.add_produit(
        "Travertin Silver",           350.0, 120,
        "Turquie — gris argenté, finition brossée antidérapante, terrasse et piscine.",
        categorie_id=cat_travertin.id, seuil_alerte=20,
    )

    # --- Commandes de démonstration ---
    store.creer_commande(c1.id, [(p1.id, 12), (p4.id, 4)])
    store.creer_commande(c2.id, [(p6.id, 40), (p3.id, 25)])
    store.creer_commande(c3.id, [(p2.id, 8), (p_g1.id, 15)])
    cmd4 = store.creer_commande(c4.id, [(p6.id, 80), (p3.id, 50)])
    store.mettre_a_jour_statut_commande(cmd4.id, "Expédiée")
    store.creer_commande(c5.id, [(p1.id, 6)])
    store.creer_commande(c6.id, [(p2.id, 20), (p4.id, 3)])
    cmd7 = store.creer_commande(c7.id, [(p_g1.id, 30), (p3.id, 60)])
    store.mettre_a_jour_statut_commande(cmd7.id, "Livrée")

    # --- Utilisateur interne ---
    store.add_utilisateur("Nasser", "nasser@ascale.ma", "Marbre2026!", role="gestionnaire")

    # --- Créneaux showroom (5 prochains jours ouvrés) ---
    from datetime import date, time, timedelta

    jour = date.today()
    jours_ajoutes = 0
    creneaux_crees = []
    while jours_ajoutes < 5:
        if jour.weekday() < 5:
            creneaux_crees.append(store.add_creneau(jour, time(9, 0), time(13, 0)))
            creneaux_crees.append(store.add_creneau(jour, time(14, 0), time(18, 0)))
            jours_ajoutes += 1
        jour += timedelta(days=1)

    store.reserver_creneau(
        creneaux_crees[0].id, "Nadia El Fassi", "0662345678", "nadia.elfassi@outlook.com"
    )
