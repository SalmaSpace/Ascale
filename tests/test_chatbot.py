"""Tests unitaires du moteur chatbot (chatbot.py).

Les tests couvrent :
- La détection correcte de chaque intention
- L'ordre de priorité (éviter les faux positifs)
- Le fallback LLM (mocké pour ne pas consommer l'API en CI)
"""

from unittest.mock import patch

import pytest

import chatbot


# ── Helper ──────────────────────────────────────────────────────────────────

def rep(store, msg):
    """Raccourci : chatbot.repondre() avec LLM désactivé."""
    with patch("chatbot.OPENROUTER_API_KEY", ""):
        return chatbot.repondre(store, msg)


# ═══════════════════════════════════════════════════
# SALUTATIONS & POLITESSE
# ═══════════════════════════════════════════════════

class TestSalutations:
    def test_bonjour(self, store):
        r = rep(store, "bonjour")
        assert "Bienvenue" in r or "bonjour" in r.lower()

    def test_salut(self, store):
        r = rep(store, "salut")
        assert "Bienvenue" in r or "catalogue" in r.lower()

    def test_bonsoir(self, store):
        r = rep(store, "bonsoir")
        assert len(r) > 10

    def test_merci(self, store):
        r = rep(store, "merci")
        assert "plaisir" in r.lower() or "merci" in r.lower()

    def test_au_revoir(self, store):
        r = rep(store, "au revoir")
        assert "revoir" in r.lower() or "bientot" in r.lower() or "bientôt" in r.lower()

    def test_message_vide_retourne_aide(self, store):
        r = rep(store, "")
        assert "Bienvenue" in r


# ═══════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════

class TestActions:
    def test_je_veux_commander_retourne_action_pas_statut(self, store):
        """'je veux commander' ne doit pas déclencher _tenter_statut_commande."""
        r = rep(store, "je veux commander")
        assert "commander" in r.lower() or "commande" in r.lower()
        # Ne doit PAS contenir un message "aucune commande trouvée"
        assert "n'ai trouvé aucune commande" not in r

    def test_reserver_retourne_action_reservation(self, store):
        r = rep(store, "je veux réserver une visite")
        assert "réserver" in r.lower() or "reservation" in r.lower() or "créneau" in r.lower()

    def test_parler_conseiller(self, store):
        r = rep(store, "je voudrais parler à un conseiller")
        assert "+212" in r or "contact" in r.lower()


# ═══════════════════════════════════════════════════
# DEVIS
# ═══════════════════════════════════════════════════

class TestDevis:
    def test_devis_avec_surface_et_produit(self, store):
        r = rep(store, "je veux 20m² de marbre blanc de carrare")
        assert "Devis" in r or "devis" in r
        assert "MAD" in r

    def test_devis_surface_sans_produit_demande_precision(self, store):
        r = rep(store, "je veux 15 m²")
        assert "matériau" in r.lower() or "précisez" in r.lower() or "Devis" in r

    def test_devis_surface_invalide_ignoree(self, store):
        """'0 m²' ne doit pas produire de devis."""
        r = rep(store, "je veux 0 m² de marbre")
        assert "supérieure" in r or "0" in r or "Devis" not in r


# ═══════════════════════════════════════════════════
# STATUT COMMANDE
# ═══════════════════════════════════════════════════

class TestStatutCommande:
    def test_statut_commande_par_numero(self, store):
        r = rep(store, "statut commande 1")
        # La commande 1 existe dans les données seed
        assert "Commande" in r or "commande" in r.lower()

    def test_statut_commande_numero_inexistant(self, store):
        r = rep(store, "statut commande 99999")
        assert "aucune" in r.lower() or "introuvable" in r.lower() or "Commande" in r

    def test_statut_mot_cle_seul(self, store):
        r = rep(store, "quel est le statut de ma commande")
        assert "commande" in r.lower()


# ═══════════════════════════════════════════════════
# BUDGET
# ═══════════════════════════════════════════════════

class TestBudget:
    def test_budget_avec_montant(self, store):
        r = rep(store, "j'ai un budget de 1000 MAD")
        assert "MAD" in r or "budget" in r.lower()

    def test_budget_pas_cher(self, store):
        r = rep(store, "je cherche quelque chose de pas cher")
        assert "accessibles" in r.lower() or "MAD" in r

    def test_budget_premium(self, store):
        r = rep(store, "je veux du luxe, haut de gamme")
        assert "premium" in r.lower() or "MAD" in r


# ═══════════════════════════════════════════════════
# RECOMMANDATIONS PAR PIÈCE
# ═══════════════════════════════════════════════════

class TestRecommandations:
    def test_pour_cuisine(self, store):
        r = rep(store, "quel matériau pour ma cuisine ?")
        assert "granit" in r.lower() or "cuisine" in r.lower()

    def test_pour_salle_de_bain(self, store):
        r = rep(store, "je veux carreler ma salle de bain")
        assert "marbre" in r.lower() or "travertin" in r.lower() or "salle de bain" in r.lower()

    def test_pour_terrasse(self, store):
        r = rep(store, "matériau pour une terrasse extérieure")
        assert "travertin" in r.lower() or "granit" in r.lower() or "terrasse" in r.lower()

    def test_pour_escalier(self, store):
        r = rep(store, "j'ai un escalier à habiller")
        assert "granit" in r.lower() or "marbre" in r.lower() or "escalier" in r.lower()


# ═══════════════════════════════════════════════════
# FAQ
# ═══════════════════════════════════════════════════

class TestFaq:
    def test_horaires(self, store):
        r = rep(store, "quels sont vos horaires ?")
        assert "lundi" in r.lower() or "9h" in r or "horaires" in r.lower()

    def test_adresse(self, store):
        r = rep(store, "quelle est votre adresse ?")
        assert "casablanca" in r.lower() or "adresse" in r.lower() or "+212" in r

    def test_livraison(self, store):
        r = rep(store, "vous livrez partout au Maroc ?")
        assert "livraison" in r.lower() or "jours" in r.lower()

    def test_paiement(self, store):
        r = rep(store, "quels modes de paiement acceptez-vous ?")
        assert "virement" in r.lower() or "acompte" in r.lower() or "paiement" in r.lower()

    def test_entretien_marbre(self, store):
        r = rep(store, "comment entretenir mon marbre ?")
        assert "marbre" in r.lower() or "entretien" in r.lower() or "acide" in r.lower()

    def test_entretien_granit(self, store):
        r = rep(store, "entretien du granit")
        assert "granit" in r.lower()

    def test_difference_marbre_granit(self, store):
        r = rep(store, "quelle est la différence entre le marbre et le granit ?")
        assert "marbre" in r.lower() and "granit" in r.lower()


# ═══════════════════════════════════════════════════
# CATALOGUE
# ═══════════════════════════════════════════════════

class TestCatalogue:
    def test_catalogue_complet(self, store):
        r = rep(store, "quels produits avez-vous ?")
        assert "Catalogue" in r or "MAD" in r

    def test_categorie_marbre(self, store):
        r = rep(store, "avez-vous du marbre ?")
        assert "marbre" in r.lower()

    def test_categorie_granit(self, store):
        r = rep(store, "montrez-moi vos granits")
        assert "granit" in r.lower()

    def test_categorie_onyx(self, store):
        r = rep(store, "avez-vous de l'onyx ?")
        assert "onyx" in r.lower()

    def test_categorie_travertin(self, store):
        r = rep(store, "travertin disponible ?")
        assert "travertin" in r.lower()


# ═══════════════════════════════════════════════════
# FAUX POSITIFS — ordre de priorité critique
# ═══════════════════════════════════════════════════

class TestFauxPositifs:
    def test_entretien_marbre_passe_par_faq_pas_catalogue(self, store):
        """'entretien du marbre' doit aller dans FAQ, pas dans catalogue catégorie."""
        r = rep(store, "entretien du marbre")
        # La réponse FAQ contient des conseils d'entretien, pas une liste de produits
        assert "acide" in r.lower() or "nettoyer" in r.lower() or "entretien" in r.lower()
        assert "MAD/m²" not in r  # ne doit pas être une liste produits

    def test_je_veux_commander_ne_declenche_pas_statut(self, store):
        r = rep(store, "je veux commander")
        assert "n'ai trouvé aucune commande" not in r

    def test_livraison_ne_declenche_pas_statut_commande(self, store):
        """'livraison' ne doit pas déclencher _tenter_statut_commande."""
        r = rep(store, "comment se passe la livraison ?")
        assert "livraison" in r.lower() or "jours" in r.lower()
        assert "n'ai trouvé aucune commande" not in r

    def test_avez_vous_marbre_retourne_catalogue_categorie_pas_produit_unique(self, store):
        """'avez-vous du marbre' (score=1) → catégorie, pas une fiche produit unique."""
        r = rep(store, "avez-vous du marbre ?")
        # Doit lister plusieurs produits (catalogue catégorie)
        assert r.count("•") >= 1 or "marbres" in r.lower()


# ═══════════════════════════════════════════════════
# FALLBACK LLM
# ═══════════════════════════════════════════════════

class TestFallbackLlm:
    def test_fallback_sans_cle_retourne_message_aide(self, store):
        """Sans OPENROUTER_API_KEY, le fallback classique s'affiche."""
        with patch("chatbot.OPENROUTER_API_KEY", ""):
            r = chatbot.repondre(store, "blabla incompréhensible zzz")
        assert "n'ai pas compris" in r.lower() or "Bienvenue" in r

    def test_fallback_avec_llm_mocke_retourne_reponse_llm(self, store):
        """Quand OpenRouter répond, le chatbot retourne sa réponse."""
        reponse_llm_simulee = "La pose d'un carrelage nécessite une colle adaptée à la pierre naturelle."
        with patch("chatbot.OPENROUTER_API_KEY", "fake-key-pour-test"), \
             patch("chatbot._tenter_llm", return_value=reponse_llm_simulee):
            r = chatbot.repondre(store, "quels outils faut-il pour poser du carrelage ?")
        assert r == reponse_llm_simulee

    def test_fallback_llm_echec_retourne_message_aide(self, store):
        """Si le LLM échoue (retourne None), le fallback classique s'affiche."""
        with patch("chatbot.OPENROUTER_API_KEY", "fake-key"), \
             patch("chatbot._tenter_llm", return_value=None):
            r = chatbot.repondre(store, "question sans réponse connue xyz")
        assert "n'ai pas compris" in r.lower() or "Bienvenue" in r
