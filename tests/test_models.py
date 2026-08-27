"""Tests unitaires de la couche service Store (models.py)."""

import pytest
from datetime import date, time

from database import Creneau
from models import CreneauIndisponibleError, StockInsuffisantError


# ═══════════════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════════════

class TestClients:
    def test_add_client_persiste(self, store):
        client = store.add_client("Alice Martin", "alice@test.com", "0600000001")
        assert client.id is not None
        assert client.nom == "Alice Martin"

    def test_find_client_by_email_trouve(self, store):
        store.add_client("Bob Dupont", "bob@test.com")
        found = store.find_client_by_email("bob@test.com")
        assert found is not None
        assert found.nom == "Bob Dupont"

    def test_find_client_by_email_insensible_casse(self, store):
        store.add_client("Carol", "Carol@Test.COM")
        assert store.find_client_by_email("carol@test.com") is not None

    def test_find_client_by_email_inconnu_retourne_none(self, store):
        assert store.find_client_by_email("inexistant@test.com") is None

    def test_update_client(self, store):
        client = store.add_client("Ancien Nom", "update@test.com")
        store.update_client(client.id, "Nouveau Nom", "update@test.com", "0600000099")
        updated = store.get_client(client.id)
        assert updated.nom == "Nouveau Nom"
        assert updated.telephone == "0600000099"

    def test_delete_client(self, store):
        client = store.add_client("À Supprimer", "del@test.com")
        cid = client.id
        store.delete_client(cid)
        assert store.get_client(cid) is None


# ═══════════════════════════════════════════════════
# PRODUITS
# ═══════════════════════════════════════════════════

class TestProduits:
    def test_add_produit_persiste(self, store):
        p = store.add_produit("Pierre Test", 500.0, 20, "Description test")
        assert p.id is not None
        assert p.nom == "Pierre Test"
        assert p.prix == 500.0
        assert p.stock == 20

    def test_get_produit_inconnu_retourne_none(self, store):
        assert store.get_produit(99999) is None

    def test_update_produit(self, store):
        p = store.add_produit("Ancienne Pierre", 100.0, 10)
        store.update_produit(p.id, "Nouvelle Pierre", 200.0, 50)
        updated = store.get_produit(p.id)
        assert updated.nom == "Nouvelle Pierre"
        assert updated.prix == 200.0
        assert updated.stock == 50

    def test_produits_stock_faible_sous_seuil(self, store):
        p = store.add_produit("Pierre Basse", 400.0, 3, seuil_alerte=10)
        faibles = store.produits_stock_faible()
        ids = [x.id for x in faibles]
        assert p.id in ids

    def test_produits_stock_faible_exclut_rupture(self, store):
        p = store.add_produit("Pierre Rupture", 400.0, 0, seuil_alerte=10)
        faibles = store.produits_stock_faible()
        assert p.id not in [x.id for x in faibles]

    def test_produits_rupture(self, store):
        p = store.add_produit("Pierre Vide", 400.0, 0)
        rupture = store.produits_rupture()
        assert p.id in [x.id for x in rupture]

    def test_produits_rupture_exclut_stock_dispo(self, store):
        p = store.add_produit("Pierre Dispo", 400.0, 5)
        rupture = store.produits_rupture()
        assert p.id not in [x.id for x in rupture]


# ═══════════════════════════════════════════════════
# COMMANDES
# ═══════════════════════════════════════════════════

class TestCommandes:
    def _setup(self, store):
        """Crée un client et un produit de base pour les tests de commande."""
        client = store.add_client("Client Test", "cmd@test.com")
        produit = store.add_produit("Marbre Test", 1000.0, 50)
        return client, produit

    def test_creer_commande_success(self, store):
        client, produit = self._setup(store)
        stock_avant = produit.stock
        commande = store.creer_commande(client.id, [(produit.id, 10)])
        assert commande.id is not None
        assert commande.statut == "Enregistrée"
        assert len(commande.lignes) == 1
        assert commande.lignes[0].quantite == 10
        # Stock décrémenté
        assert store.get_produit(produit.id).stock == stock_avant - 10

    def test_creer_commande_total_correct(self, store):
        client, produit = self._setup(store)
        commande = store.creer_commande(client.id, [(produit.id, 5)])
        assert commande.total == 5 * 1000.0

    def test_creer_commande_stock_insuffisant_leve_exception(self, store):
        client, produit = self._setup(store)
        with pytest.raises(StockInsuffisantError):
            store.creer_commande(client.id, [(produit.id, 9999)])

    def test_creer_commande_atomique_aucun_stock_decremente(self, store):
        """Si un produit manque de stock, AUCUN stock ne doit être décrémenté."""
        client = store.add_client("Atomique", "atomique@test.com")
        p1 = store.add_produit("Produit OK",  500.0, 10)
        p2 = store.add_produit("Produit KO",  500.0,  2)  # stock insuffisant pour 5
        stock_p1_avant = p1.stock

        with pytest.raises(StockInsuffisantError):
            store.creer_commande(client.id, [(p1.id, 3), (p2.id, 5)])

        # p1 ne doit pas avoir été décrémenté
        assert store.get_produit(p1.id).stock == stock_p1_avant

    def test_creer_commande_client_inconnu_leve_exception(self, store):
        _, produit = self._setup(store)
        with pytest.raises(ValueError):
            store.creer_commande(99999, [(produit.id, 1)])

    def test_supprimer_commande_recredite_stock(self, store):
        client, produit = self._setup(store)
        stock_avant = produit.stock
        commande = store.creer_commande(client.id, [(produit.id, 8)])
        store.supprimer_commande(commande.id)
        assert store.get_produit(produit.id).stock == stock_avant

    def test_supprimer_commande_inexistante_ne_plante_pas(self, store):
        store.supprimer_commande(99999)  # ne doit pas lever d'exception

    def test_mettre_a_jour_statut(self, store):
        client, produit = self._setup(store)
        commande = store.creer_commande(client.id, [(produit.id, 1)])
        store.mettre_a_jour_statut_commande(commande.id, "Expédiée")
        assert store.get_commande(commande.id).statut == "Expédiée"

    def test_creer_commande_publique_cree_client_si_nouveau(self, store):
        produit = store.add_produit("Publi-Pierre", 800.0, 20)
        commande = store.creer_commande_publique(
            "Nouveau Client", "nouveau@test.com", "0600000010", [(produit.id, 3)]
        )
        assert commande.source == "public"
        assert store.find_client_by_email("nouveau@test.com") is not None

    def test_creer_commande_publique_reutilise_client_existant(self, store):
        store.add_client("Existant", "existant@test.com", "0600000011")
        produit = store.add_produit("Publi-Pierre2", 800.0, 20)
        store.creer_commande_publique("Existant", "existant@test.com", "0600000011", [(produit.id, 2)])
        # Il ne doit pas y avoir de doublon client
        clients = [c for c in store.list_clients() if c.email == "existant@test.com"]
        assert len(clients) == 1

    def test_commandes_par_source(self, store):
        client = store.add_client("Source Test", "src@test.com")
        p = store.add_produit("Src Produit", 500.0, 50)
        store.creer_commande(client.id, [(p.id, 1)], source="admin")
        store.creer_commande_publique("Public", "pub@test.com", "0600000020", [(p.id, 1)])
        sources = store.commandes_par_source()
        assert sources.get("admin", 0) >= 1
        assert sources.get("public", 0) >= 1

    def test_top_produits_commandes(self, store):
        client = store.add_client("Top Test", "top@test.com")
        p1 = store.add_produit("Top A", 500.0, 500)
        p2 = store.add_produit("Top B", 500.0, 100)
        # 200 m² > seed max (Marbre Beige Crema Marfil : 135 m² cumulés)
        store.creer_commande(client.id, [(p1.id, 200), (p2.id, 5)])
        top = store.top_produits_commandes(2)
        assert len(top) >= 1
        assert top[0].nom == "Top A"


# ═══════════════════════════════════════════════════
# CRÉNEAUX & RÉSERVATIONS
# ═══════════════════════════════════════════════════

class TestCreneaux:
    def _creer_creneau(self, store, disponible=True):
        from database import db
        c = Creneau(
            date_creneau=date(2099, 1, 15),
            heure_debut=time(9, 0),
            heure_fin=time(13, 0),
            disponible=disponible,
        )
        db.session.add(c)
        db.session.commit()
        return c

    def test_reserver_creneau_success(self, store, app):
        with app.app_context():
            c = self._creer_creneau(store)
            resa = store.reserver_creneau(c.id, "Test Résa", "0600000030", "resa@test.com")
            assert resa.id is not None
            assert resa.client_nom == "Test Résa"
            # Le créneau est marqué indisponible
            from database import Creneau as C
            c_db = C.query.get(c.id)
            assert c_db.disponible is False

    def test_reserver_creneau_indisponible_leve_exception(self, store, app):
        with app.app_context():
            c = self._creer_creneau(store, disponible=False)
            with pytest.raises(CreneauIndisponibleError):
                store.reserver_creneau(c.id, "Test", "0600000031", "x@test.com")

    def test_reserver_creneau_inexistant_leve_exception(self, store):
        with pytest.raises(CreneauIndisponibleError):
            store.reserver_creneau(99999, "Test", "0600000032", "y@test.com")

    def test_list_creneaux_filtre_disponible(self, store, app):
        with app.app_context():
            c_dispo = self._creer_creneau(store, disponible=True)
            c_pris  = self._creer_creneau(store, disponible=False)
            dispo = [c.id for c in store.list_creneaux()]
            assert c_dispo.id in dispo
            assert c_pris.id  not in dispo

    def test_list_tous_creneaux_retourne_tous(self, store, app):
        with app.app_context():
            c1 = self._creer_creneau(store, disponible=True)
            c2 = self._creer_creneau(store, disponible=False)
            tous = [c.id for c in store.list_tous_creneaux()]
            assert c1.id in tous
            assert c2.id in tous

    def test_annuler_reservation_libere_creneau(self, store, app):
        with app.app_context():
            c = self._creer_creneau(store)
            resa = store.reserver_creneau(c.id, "Annul", "0600000040", "annul@test.com")
            store.annuler_reservation(resa.id)
            from database import Creneau as C
            assert C.query.get(c.id).disponible is True
