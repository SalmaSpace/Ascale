"""Modèles SQLAlchemy — correspond aux entités du MCD Ascale (Looping).

Entités : Categorie, Client, Produit, LigneCommande, Commande, Devis,
          Creneau, Reservation, MessageWhatsApp, Utilisateur.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Categorie(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    produits = db.relationship("Produit", backref="categorie", lazy="select")

    def __repr__(self):
        return f"<Categorie {self.nom}>"


class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    telephone = db.Column(db.String(50))
    adresse = db.Column(db.String(500))
    commandes = db.relationship("Commande", backref="client_obj", lazy="select")
    messages = db.relationship("MessageWhatsApp", backref="client_obj", lazy="select")

    def __repr__(self):
        return f"<Client {self.nom}>"


class Produit(db.Model):
    __tablename__ = "produits"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    prix = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, default="")
    categorie_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    seuil_alerte = db.Column(db.Integer, default=10)
    lignes = db.relationship("LigneCommande", backref="produit_obj", lazy="select")

    def __repr__(self):
        return f"<Produit {self.nom}>"


class LigneCommande(db.Model):
    __tablename__ = "lignes_commande"
    id = db.Column(db.Integer, primary_key=True)
    commande_id = db.Column(
        db.Integer, db.ForeignKey("commandes.id", ondelete="CASCADE"), nullable=False
    )
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"))
    produit_nom = db.Column(db.String(200), nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    prix_unitaire = db.Column(db.Float, nullable=False)

    @property
    def sous_total(self):
        return self.quantite * self.prix_unitaire

    def __repr__(self):
        return f"<LigneCommande {self.produit_nom} x{self.quantite}>"


class Commande(db.Model):
    __tablename__ = "commandes"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"))
    client_nom = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    statut = db.Column(db.String(50), default="Enregistrée")
    source = db.Column(db.String(20), default="admin")  # 'admin' ou 'public'
    lignes = db.relationship(
        "LigneCommande",
        backref="commande_obj",
        lazy="select",
        cascade="all, delete-orphan",
    )

    @property
    def total(self):
        return sum(ligne.sous_total for ligne in self.lignes)

    def __repr__(self):
        return f"<Commande {self.id} {self.client_nom}>"


class Devis(db.Model):
    """Devis (association Aboutir entre Client et Commande dans le MCD)."""

    __tablename__ = "devis"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"))
    date_devis = db.Column(db.DateTime, default=datetime.now)
    montant = db.Column(db.Float)
    statut = db.Column(db.String(50), default="En attente")
    commande_id = db.Column(db.Integer, db.ForeignKey("commandes.id"))

    def __repr__(self):
        return f"<Devis {self.id}>"


class Creneau(db.Model):
    __tablename__ = "creneaux"
    id = db.Column(db.Integer, primary_key=True)
    date_creneau = db.Column(db.Date, nullable=False)
    heure_debut = db.Column(db.Time, nullable=False)
    heure_fin = db.Column(db.Time, nullable=False)
    disponible = db.Column(db.Boolean, default=True)
    reservations = db.relationship("Reservation", backref="creneau_obj", lazy="select")

    def __repr__(self):
        return f"<Creneau {self.date_creneau} {self.heure_debut}>"


class Reservation(db.Model):
    __tablename__ = "reservations"
    id = db.Column(db.Integer, primary_key=True)
    creneau_id = db.Column(db.Integer, db.ForeignKey("creneaux.id"), nullable=False)
    client_nom = db.Column(db.String(200), nullable=False)
    client_telephone = db.Column(db.String(50), nullable=False)
    client_email = db.Column(db.String(200), nullable=False)
    date_reservation = db.Column(db.DateTime, default=datetime.now)
    statut = db.Column(db.String(50), default="Confirmée")
    email_envoye = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Reservation {self.id} {self.client_nom}>"


class MessageWhatsApp(db.Model):
    """Historique des messages WhatsApp (entité MESSAGE_WHATSAPP du MCD)."""

    __tablename__ = "messages_whatsapp"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"))
    date_envoi = db.Column(db.DateTime, default=datetime.now)
    contenu = db.Column(db.Text, nullable=False)
    sens = db.Column(db.String(10), default="entrant")  # 'entrant' ou 'sortant'

    def __repr__(self):
        return f"<MessageWhatsApp {self.id} {self.sens}>"


class Utilisateur(db.Model):
    __tablename__ = "utilisateurs"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(500), nullable=False)
    role = db.Column(db.String(50), default="gestionnaire")

    def __repr__(self):
        return f"<Utilisateur {self.nom}>"
