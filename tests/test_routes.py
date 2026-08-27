"""Tests d'intégration des routes Flask (app.py).

Chaque test envoie une vraie requête HTTP via app.test_client() et vérifie
le code de statut et/ou le contenu de la réponse.
"""

import csv
import io

import pytest


# ═══════════════════════════════════════════════════
# PAGES PUBLIQUES
# ═══════════════════════════════════════════════════

class TestPagesPubliques:
    def test_accueil_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_nos_materiaux_200(self, client):
        r = client.get("/nos-materiaux")
        assert r.status_code == 200
        assert b"catalogue" in r.data.lower() or b"mat" in r.data.lower()

    def test_commander_get_200(self, client):
        r = client.get("/commander")
        assert r.status_code == 200

    def test_chatbot_page_200(self, client):
        r = client.get("/chatbot")
        assert r.status_code == 200

    def test_reservation_page_200(self, client):
        r = client.get("/reservation")
        assert r.status_code == 200

    def test_contact_get_200(self, client):
        r = client.get("/contact")
        assert r.status_code == 200

    def test_route_inexistante_404(self, client):
        r = client.get("/page-qui-nexiste-pas")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════
# PAGES ADMIN
# ═══════════════════════════════════════════════════

class TestPagesAdmin:
    def test_gestion_200(self, client):
        r = client.get("/gestion")
        assert r.status_code == 200

    def test_commandes_200(self, client):
        r = client.get("/commandes")
        assert r.status_code == 200

    def test_produits_200(self, client):
        r = client.get("/produits")
        assert r.status_code == 200

    def test_clients_200(self, client):
        r = client.get("/clients")
        assert r.status_code == 200

    def test_nouvelle_commande_get_200(self, client):
        r = client.get("/commandes/nouvelle")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════
# COMMANDE PUBLIQUE (POST /commander)
# ═══════════════════════════════════════════════════

class TestCommandeurPublic:
    def _premier_produit_id(self, client):
        """Récupère l'ID du premier produit via la page catalogue."""
        r = client.get("/commander")
        # Les IDs produits sont dans le HTML sous la forme data-id="N"
        import re
        match = re.search(rb'data-id="(\d+)"', r.data)
        return int(match.group(1)) if match else 1

    def test_post_valide_redirige_vers_paiement(self, client):
        pid = self._premier_produit_id(client)
        r = client.post("/commander", data={
            "nom": "Test Client",
            "email": "test@example.com",
            "telephone": "0600000000",
            "produit_id": str(pid),
            "quantite": "1",
        }, follow_redirects=False)
        # Doit maintenant rediriger vers /paiement (étape 2)
        assert r.status_code in (302, 303)
        assert b"/paiement" in r.headers.get("Location", "").encode()

    def test_post_sans_nom_flash_erreur(self, client):
        pid = self._premier_produit_id(client)
        r = client.post("/commander", data={
            "nom": "",
            "email": "test@example.com",
            "telephone": "0600000000",
            "produit_id": str(pid),
            "quantite": "1",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b"nom" in r.data.lower() or b"renseigner" in r.data.lower()

    def test_post_email_invalide_flash_erreur(self, client):
        pid = self._premier_produit_id(client)
        r = client.post("/commander", data={
            "nom": "Test",
            "email": "pas-un-email",
            "telephone": "0600000000",
            "produit_id": str(pid),
            "quantite": "1",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b"email" in r.data.lower()

    def test_post_sans_produit_flash_erreur(self, client):
        r = client.post("/commander", data={
            "nom": "Test",
            "email": "test@example.com",
            "telephone": "0600000000",
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_post_stock_insuffisant_flash_erreur(self, client):
        # On demande une quantité astronomique
        pid = self._premier_produit_id(client)
        r = client.post("/commander", data={
            "nom": "Test",
            "email": "overstock@example.com",
            "telephone": "0600000000",
            "produit_id": str(pid),
            "quantite": "999999",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b"stock" in r.data.lower() or b"insuffisant" in r.data.lower()


# ═══════════════════════════════════════════════════
# CHATBOT
# ═══════════════════════════════════════════════════

class TestChatbotRoutes:
    def test_envoyer_message_redirige(self, client):
        r = client.post("/chatbot/envoyer", data={"message": "bonjour"})
        assert r.status_code in (302, 303)

    def test_widget_json_retourne_reponse(self, client):
        r = client.post("/chatbot/widget/envoyer",
                        data={"message": "bonjour"},
                        content_type="application/x-www-form-urlencoded")
        assert r.status_code == 200
        data = r.get_json()
        assert "reponse" in data
        assert len(data["reponse"]) > 0

    def test_widget_message_vide_retourne_400(self, client):
        r = client.post("/chatbot/widget/envoyer",
                        data={"message": ""},
                        content_type="application/x-www-form-urlencoded")
        assert r.status_code == 400

    def test_reinitialiser_conversation(self, client):
        # D'abord envoyer un message pour créer une session
        client.post("/chatbot/envoyer", data={"message": "bonjour"})
        r = client.post("/chatbot/reinitialiser")
        assert r.status_code in (302, 303)


# ═══════════════════════════════════════════════════
# EXPORT CSV
# ═══════════════════════════════════════════════════

class TestExportCsv:
    def test_export_commandes_csv_content_type(self, client):
        r = client.get("/admin/commandes/export")
        assert r.status_code == 200
        assert "text/csv" in r.content_type

    def test_export_commandes_csv_a_un_entete(self, client):
        r = client.get("/admin/commandes/export")
        content = r.data.decode("utf-8-sig")  # retire le BOM
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        assert "ID" in header
        assert "Client" in header
        assert "Statut" in header

    def test_export_clients_csv_content_type(self, client):
        r = client.get("/admin/clients/export")
        assert r.status_code == 200
        assert "text/csv" in r.content_type

    def test_export_clients_csv_a_un_entete(self, client):
        r = client.get("/admin/clients/export")
        content = r.data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        assert "Nom" in header
        assert "Email" in header


# ═══════════════════════════════════════════════════
# GESTION STATUT COMMANDE
# ═══════════════════════════════════════════════════

class TestStatutCommande:
    def test_mise_a_jour_statut_valide(self, client):
        r = client.post("/commandes/1/statut",
                        data={"statut": "Expédiée"},
                        follow_redirects=True)
        assert r.status_code == 200

    def test_mise_a_jour_statut_invalide_flash(self, client):
        r = client.post("/commandes/1/statut",
                        data={"statut": "StatutInvalideXYZ"},
                        follow_redirects=True)
        assert r.status_code == 200
        assert b"invalide" in r.data.lower() or b"statut" in r.data.lower()


# ═══════════════════════════════════════════════════
# WEBHOOK WHATSAPP
# ═══════════════════════════════════════════════════

class TestWebhookWhatsapp:
    def test_verification_sans_token_retourne_403(self, client):
        r = client.get("/webhook/whatsapp", query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "mauvais-token",
            "hub.challenge": "challenge123",
        })
        assert r.status_code == 403

    def test_post_webhook_sans_config_retourne_200(self, client):
        """Le webhook doit toujours répondre 200 (convention Meta)."""
        r = client.post("/webhook/whatsapp",
                        json={"entry": []},
                        content_type="application/json")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════
# AJOUT PRODUIT / CLIENT (admin)
# ═══════════════════════════════════════════════════

class TestAdminCrud:
    def test_ajouter_produit_redirige(self, client):
        r = client.post("/produits/ajouter", data={
            "nom": "Nouveau Produit Test",
            "prix": "750",
            "stock": "30",
            "description": "Test ajout produit",
        })
        assert r.status_code in (302, 303)

    def test_ajouter_produit_champs_invalides_flash(self, client):
        r = client.post("/produits/ajouter", data={
            "nom": "",
            "prix": "-10",
            "stock": "0",
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_ajouter_client_redirige(self, client):
        r = client.post("/clients/ajouter", data={
            "nom": "Nouveau Client Test",
            "email": "nouveau@test.com",
            "telephone": "0600000099",
        })
        assert r.status_code in (302, 303)

    def test_ajouter_client_sans_nom_flash(self, client):
        r = client.post("/clients/ajouter",
                        data={"nom": ""},
                        follow_redirects=True)
        assert r.status_code == 200
