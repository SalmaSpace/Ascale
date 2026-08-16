"""Modèles de données et stockage en mémoire pour l'application Ascale.

Aucune base de données n'est utilisée pour le moment : toutes les données
vivent dans l'objet `Store`, en mémoire, et sont réinitialisées à chaque
redémarrage de l'application (`db.create_all()` n'est plus utilisé).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from itertools import count
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class Client:
    id: int
    nom: str
    email: Optional[str] = None
    telephone: Optional[str] = None


@dataclass
class Produit:
    id: int
    nom: str
    prix: float
    stock: int
    description: str = ""


@dataclass
class LigneCommande:
    produit_id: int
    produit_nom: str
    quantite: int
    prix_unitaire: float

    @property
    def sous_total(self) -> float:
        return self.quantite * self.prix_unitaire


@dataclass
class Commande:
    id: int
    client_id: int
    client_nom: str
    date: datetime
    lignes: list = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(ligne.sous_total for ligne in self.lignes)

    @property
    def statut(self) -> str:
        """Statut simulé de la commande, dérivé de son ancienneté.

        Il n'existe pas encore de vrai suivi logistique : ce calcul sert de
        placeholder démontrable (notamment pour le chatbot) en attendant un
        futur module de suivi de commande avec un statut stocké et mis à jour
        par l'équipe.
        """
        jours = (datetime.now() - self.date).days
        if jours < 1:
            return "Enregistrée"
        if jours < 3:
            return "En préparation"
        if jours < 6:
            return "Expédiée"
        return "Livrée"


@dataclass
class Creneau:
    """Créneau de visite showroom (entité CRENEAU du MCD)."""

    id: int
    date_creneau: date
    heure_debut: time
    heure_fin: time
    disponible: bool = True


@dataclass
class Reservation:
    """Réservation d'un créneau (association RESERVER du MCD).

    L'identité du client est stockée directement (nom/téléphone) plutôt que
    liée par une clé étrangère vers `Client` : la réservation est publique et
    ne nécessite pas que la personne soit déjà une fiche client enregistrée
    dans le CRM interne.
    """

    id: int
    creneau_id: int
    client_nom: str
    client_telephone: str
    client_email: str
    date_reservation: datetime
    statut: str = "Confirmée"
    email_envoye: bool = False


@dataclass
class Utilisateur:
    """Compte interne (entité UTILISATEUR du MCD) pour l'espace de gestion."""

    id: int
    nom: str
    email: str
    mot_de_passe_hash: str
    role: str = "gestionnaire"


class StockInsuffisantError(Exception):
    """Levée quand une commande demande plus de stock que disponible."""


class CreneauIndisponibleError(Exception):
    """Levée quand on tente de réserver un créneau inexistant ou déjà pris."""


class Store:
    """Dépôt de données en mémoire (tient lieu de base de données)."""

    def __init__(self):
        self._clients: dict[int, Client] = {}
        self._produits: dict[int, Produit] = {}
        self._commandes: dict[int, Commande] = {}
        self._creneaux: dict[int, Creneau] = {}
        self._reservations: dict[int, Reservation] = {}
        self._utilisateurs: dict[int, Utilisateur] = {}
        self._client_ids = count(1)
        self._produit_ids = count(1)
        self._commande_ids = count(1)
        self._creneau_ids = count(1)
        self._reservation_ids = count(1)
        self._utilisateur_ids = count(1)

    # ---------- Clients ----------
    def list_clients(self):
        return sorted(self._clients.values(), key=lambda c: c.nom.lower())

    def get_client(self, client_id):
        return self._clients.get(client_id)

    def add_client(self, nom, email=None, telephone=None):
        client = Client(id=next(self._client_ids), nom=nom, email=email, telephone=telephone)
        self._clients[client.id] = client
        return client

    def update_client(self, client_id, nom, email=None, telephone=None):
        client = self._clients.get(client_id)
        if client is None:
            return None
        client.nom = nom
        client.email = email
        client.telephone = telephone
        return client

    def delete_client(self, client_id):
        self._clients.pop(client_id, None)

    # ---------- Produits ----------
    def list_produits(self):
        return sorted(self._produits.values(), key=lambda p: p.nom.lower())

    def get_produit(self, produit_id):
        return self._produits.get(produit_id)

    def add_produit(self, nom, prix, stock, description=""):
        produit = Produit(
            id=next(self._produit_ids), nom=nom, prix=prix, stock=stock, description=description
        )
        self._produits[produit.id] = produit
        return produit

    def update_produit(self, produit_id, nom, prix, stock, description=""):
        produit = self._produits.get(produit_id)
        if produit is None:
            return None
        produit.nom = nom
        produit.prix = prix
        produit.stock = stock
        produit.description = description
        return produit

    def delete_produit(self, produit_id):
        self._produits.pop(produit_id, None)

    # ---------- Commandes ----------
    def list_commandes(self):
        return sorted(self._commandes.values(), key=lambda c: c.date, reverse=True)

    def get_commande(self, commande_id):
        return self._commandes.get(commande_id)

    def creer_commande(self, client_id, lignes_demandees):
        """Crée une commande et décrémente le stock des produits commandés.

        `lignes_demandees` est une liste de tuples (produit_id, quantite).
        Toute la commande est validée avant d'appliquer le moindre changement
        de stock, pour éviter une décrémentation partielle en cas d'erreur.
        """
        client = self._clients.get(client_id)
        if client is None:
            raise ValueError("Client introuvable.")

        lignes_validees = []
        for produit_id, quantite in lignes_demandees:
            produit = self._produits.get(produit_id)
            if produit is None:
                raise ValueError("Produit introuvable.")
            if quantite <= 0:
                raise ValueError(f"Quantité invalide pour « {produit.nom} ».")
            if quantite > produit.stock:
                raise StockInsuffisantError(
                    f"Stock insuffisant pour « {produit.nom} » (disponible : {produit.stock})."
                )
            lignes_validees.append((produit, quantite))

        if not lignes_validees:
            raise ValueError("Ajoutez au moins un article à la commande.")

        commande = Commande(
            id=next(self._commande_ids),
            client_id=client.id,
            client_nom=client.nom,
            date=datetime.now(),
        )
        for produit, quantite in lignes_validees:
            commande.lignes.append(
                LigneCommande(
                    produit_id=produit.id,
                    produit_nom=produit.nom,
                    quantite=quantite,
                    prix_unitaire=produit.prix,
                )
            )
            produit.stock -= quantite

        self._commandes[commande.id] = commande
        return commande

    def supprimer_commande(self, commande_id):
        """Supprime une commande et recrédite le stock des produits concernés."""
        commande = self._commandes.pop(commande_id, None)
        if commande is None:
            return
        for ligne in commande.lignes:
            produit = self._produits.get(ligne.produit_id)
            if produit is not None:
                produit.stock += ligne.quantite

    # ---------- Tableau de bord ----------
    def chiffre_affaires(self):
        return sum(commande.total for commande in self._commandes.values())

    # ---------- Créneaux & réservations ----------
    def list_creneaux(self):
        return sorted(self._creneaux.values(), key=lambda c: (c.date_creneau, c.heure_debut))

    def get_creneau(self, creneau_id):
        return self._creneaux.get(creneau_id)

    def add_creneau(self, date_creneau, heure_debut, heure_fin):
        creneau = Creneau(
            id=next(self._creneau_ids),
            date_creneau=date_creneau,
            heure_debut=heure_debut,
            heure_fin=heure_fin,
        )
        self._creneaux[creneau.id] = creneau
        return creneau

    def list_reservations(self):
        return sorted(self._reservations.values(), key=lambda r: r.date_reservation, reverse=True)

    def get_reservation(self, reservation_id):
        return self._reservations.get(reservation_id)

    def reserver_creneau(self, creneau_id, client_nom, client_telephone, client_email):
        """Réserve `creneau_id` pour un client, en empêchant la double réservation.

        Le MCD borne la participation d'un CRENEAU à l'association RESERVER à
        0,1 : un créneau ne peut être réservé qu'une seule fois. On applique
        cette règle ici en vérifiant `disponible` avant toute création.
        """
        creneau = self._creneaux.get(creneau_id)
        if creneau is None:
            raise CreneauIndisponibleError("Ce créneau n'existe pas.")
        if not creneau.disponible:
            raise CreneauIndisponibleError(
                "Ce créneau vient d'être réservé par quelqu'un d'autre. Merci d'en choisir un autre."
            )

        reservation = Reservation(
            id=next(self._reservation_ids),
            creneau_id=creneau.id,
            client_nom=client_nom,
            client_telephone=client_telephone,
            client_email=client_email,
            date_reservation=datetime.now(),
        )
        creneau.disponible = False
        self._reservations[reservation.id] = reservation
        return reservation

    def annuler_reservation(self, reservation_id):
        """Annule une réservation et rend son créneau à nouveau disponible."""
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            return
        creneau = self._creneaux.get(reservation.creneau_id)
        if creneau is not None:
            creneau.disponible = True

    # ---------- Utilisateurs (accès interne) ----------
    def add_utilisateur(self, nom, email, mot_de_passe, role="gestionnaire"):
        utilisateur = Utilisateur(
            id=next(self._utilisateur_ids),
            nom=nom,
            email=email.strip().lower(),
            mot_de_passe_hash=generate_password_hash(mot_de_passe),
            role=role,
        )
        self._utilisateurs[utilisateur.id] = utilisateur
        return utilisateur

    def get_utilisateur(self, utilisateur_id):
        return self._utilisateurs.get(utilisateur_id)

    def verifier_identifiants(self, email, mot_de_passe):
        """Retourne l'Utilisateur correspondant si email + mot de passe sont valides, sinon None."""
        email = (email or "").strip().lower()
        for utilisateur in self._utilisateurs.values():
            if utilisateur.email == email and check_password_hash(utilisateur.mot_de_passe_hash, mot_de_passe):
                return utilisateur
        return None


def seed(store: Store) -> None:
    """Peuple le store avec des données de démonstration (négoce de marbre de luxe)."""
    c1 = store.add_client("Karim Benjelloun", "karim.benjelloun@gmail.com", "0661234567")
    c2 = store.add_client(
        "Atelier Zellige — Architecture & Design", "contact@atelierzellige.ma", "0522334455"
    )
    store.add_client("Nadia El Fassi", "nadia.elfassi@outlook.com", "0662345678")
    store.add_client("Batico Construction", "contact@batico-construction.ma", "0522556677")
    store.add_client("Riad Dar Yasmine", "reservation@riaddaryasmine.ma", "0524123456")

    p1 = store.add_produit(
        "Marbre Blanc de Carrare",
        1850.0,
        85,
        "Italie — dalle premium pour sol, plan de travail et revêtement mural haut de gamme.",
    )
    store.add_produit(
        "Marbre Noir Marquina",
        1950.0,
        60,
        "Espagne — sol et plan de travail d'exception, veines blanches marquées sur fond noir.",
    )
    p3 = store.add_produit(
        "Marbre Beige Crema Marfil",
        890.0,
        120,
        "Espagne — sol, escalier et habillage mural, teinte beige intemporelle.",
    )
    p4 = store.add_produit(
        "Onyx Blanc translucide",
        4800.0,
        25,
        "Iran — revêtement mural rétroéclairé et éléments décoratifs, forte translucidité.",
    )
    store.add_produit(
        "Marbre Vert Guatemala",
        3200.0,
        30,
        "Inde — plan de travail et sol d'exception, veines vertes profondes.",
    )
    p6 = store.add_produit(
        "Travertin Beige",
        520.0,
        150,
        "Turquie — sol intérieur et extérieur, terrasse, salle de bain.",
    )
    store.add_produit(
        "Marbre Rose Portugal",
        1650.0,
        45,
        "Portugal — sol et habillage mural, teinte rosée délicate.",
    )
    store.add_produit(
        "Granit Noir Absolu",
        1100.0,
        70,
        "Inde — plan de travail cuisine, sol à fort trafic, noir intense et uniforme.",
    )

    # Prix au m² (dalles/plaques), stock exprimé en m² disponibles.
    store.creer_commande(c1.id, [(p1.id, 12), (p4.id, 4)])
    store.creer_commande(c2.id, [(p6.id, 40), (p3.id, 20)])

    # ---------- Utilisateur interne (démo, espace de gestion protégé) ----------
    store.add_utilisateur("Nasser", "nasser@ascale.ma", "Marbre2026!", role="gestionnaire")

    # ---------- Créneaux de visite showroom (5 prochains jours ouvrés) ----------
    jour = date.today()
    jours_ajoutes = 0
    creneaux_crees = []
    while jours_ajoutes < 5:
        if jour.weekday() < 5:  # lundi à vendredi
            creneaux_crees.append(store.add_creneau(jour, time(9, 0), time(13, 0)))
            creneaux_crees.append(store.add_creneau(jour, time(14, 0), time(18, 0)))
            jours_ajoutes += 1
        jour += timedelta(days=1)

    store.reserver_creneau(
        creneaux_crees[0].id, "Nadia El Fassi", "0662345678", "nadia.elfassi@outlook.com"
    )
