"""Tests d'intégration des routes Flask (app.py).

Chaque test envoie une vraie requête HTTP via app.test_client() et vérifie
le code de statut et/ou le contenu de la réponse.
"""

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
