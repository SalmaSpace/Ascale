"""Logique métier du chatbot WhatsApp d'Ascale.

Ce module ne dépend pas de Flask : il prend un `Store` (voir `models.py`) et
un message texte, et retourne une réponse texte. L'objectif est de pouvoir
brancher cette même fonction `repondre()` sur un vrai webhook WhatsApp
Business (voir `whatsapp_config.py`) plus tard, en ne remplaçant que la
couche transport — actuellement la page de simulation `/chatbot`.

Le compte WhatsApp Business n'étant pas encore actif, la logique est ici
testée via une interface de simulation qui reproduit une conversation
WhatsApp.
"""

import re
import unicodedata
from itertools import count

_devis_ids = count(1)

MOTS_CLES_COMMANDE = ("commande", "statut", "suivi", "livr", "où en est", "ou en est")

SALUTATIONS = {"bonjour", "salut", "bonsoir", "bonsoir", "hello", "coucou", "slt", "bjr", "hey"}

MESSAGE_AIDE = (
    "👋 Bienvenue chez *Ascale Marbre* !\n"
    "Je peux vous aider à :\n"
    "• 🔎 Me renseigner sur un produit — ex. « avez-vous du marbre noir ? »\n"
    "• 💰 Obtenir un devis — ex. « je veux 20m² de Crema Marfil »\n"
    "• 📦 Suivre une commande — ex. « statut commande 1 » ou votre nom\n"
    "Que puis-je faire pour vous ?"
)

EXEMPLES = (
    "avez-vous du marbre noir ?",
    "je veux 20m² de Crema Marfil",
    "statut commande 1",
)


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def _normaliser(texte: str) -> str:
    return _sans_accents(texte or "").lower().strip()


def _meilleur_produit(store, texte):
    """Retrouve le produit le plus probablement évoqué dans `texte`.

    Approche volontairement simple (comptage des mots du nom du produit
    retrouvés tels quels parmi les mots du message) : suffisant pour un
    catalogue de quelques dizaines de références, sans dépendance NLP.
    Compare des mots entiers (et non des sous-chaînes) pour éviter des faux
    positifs comme "vert" détecté à l'intérieur de "travertin".
    """
    mots_message = set(re.findall(r"[a-z0-9]+", texte))
    meilleur, meilleur_score = None, 0
    for produit in store.list_produits():
        mots_produit = [m for m in _normaliser(produit.nom).split() if len(m) > 2]
        score = sum(1 for m in mots_produit if m in mots_message)
        if score > meilleur_score:
            meilleur, meilleur_score = produit, score
    return meilleur


def _tenter_devis(store, texte):
    match_quantite = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|metres?\s*carr[ée]?s?)", texte)
    if not match_quantite:
        return None

    quantite = float(match_quantite.group(1).replace(",", "."))
    if quantite <= 0:
        return "💰 Merci d'indiquer une surface supérieure à 0 m² pour votre devis."

    produit = _meilleur_produit(store, texte)
    if produit is None:
        return (
            "💰 Je n'ai pas identifié le produit pour votre devis. "
            "Précisez son nom, ex. « je veux 20m² de Crema Marfil »."
        )

    total = produit.prix * quantite
    quantite_affichee = int(quantite) if quantite.is_integer() else quantite
    numero = next(_devis_ids)
    disponibilite = (
        "✅ en stock" if produit.stock >= quantite else f"⚠️ stock limité ({produit.stock} m² disponibles)"
    )

    return (
        f"💰 *Devis n°{numero}*\n"
        f"{quantite_affichee} m² de {produit.nom}\n"
        f"Prix unitaire : {produit.prix:.0f} MAD/m²\n"
        f"Total estimé : {total:.0f} MAD\n"
        f"Disponibilité : {disponibilite}\n"
        f"Devis indicatif, sans engagement — contactez-nous pour confirmer la commande."
    )


def _tenter_statut_commande(store, texte):
    commande = None

    match_numero = re.search(r"(?:commande|n[°o]|#)\D{0,3}(\d+)", texte)
    if match_numero:
        commande = store.get_commande(int(match_numero.group(1)))

    if commande is None:
        for client in store.list_clients():
            nom_normalise = _normaliser(client.nom)
            if len(texte) >= 4 and len(nom_normalise) >= 4 and (
                nom_normalise in texte or texte in nom_normalise
            ):
                commandes_client = [c for c in store.list_commandes() if c.client_id == client.id]
                if commandes_client:
                    commande = commandes_client[0]
                break

    if commande is None:
        if not any(mot in texte for mot in MOTS_CLES_COMMANDE):
            return None
        return (
            "📦 Je n'ai trouvé aucune commande correspondante. "
            "Précisez le numéro de commande (ex. « statut commande 3 ») ou votre nom exact."
        )

    lignes = "\n".join(
        f"  – {ligne.quantite} m² de {ligne.produit_nom} ({ligne.sous_total:.0f} MAD)"
        for ligne in commande.lignes
    )
    return (
        f"📦 *Commande n°{commande.id}* — {commande.client_nom}\n"
        f"Statut : {commande.statut}\n"
        f"Date : {commande.date.strftime('%d/%m/%Y')}\n"
        f"{lignes}\n"
        f"Total : {commande.total:.0f} MAD"
    )


def _tenter_info_produit(store, texte):
    produit = _meilleur_produit(store, texte)
    if produit is None:
        return None

    disponibilite = f"{produit.stock} m² en stock" if produit.stock > 0 else "actuellement en rupture de stock"
    description = f"\n{produit.description}" if produit.description else ""
    return (
        f"✅ Oui, nous avons du *{produit.nom}*.\n"
        f"Prix : {produit.prix:.0f} MAD/m²\n"
        f"Disponibilité : {disponibilite}{description}\n"
        f"Pour un devis, précisez la surface souhaitée (ex. « je veux 15m² »)."
    )


def repondre(store, message: str, expediteur: str = "") -> str:
    """Calcule la réponse du chatbot à `message` pour un `store` donné.

    `expediteur` (numéro de téléphone WhatsApp) n'est pas encore utilisé,
    mais fait partie de la signature dès maintenant pour ne pas casser les
    appelants une fois le vrai webhook WhatsApp branché (identification du
    client par son numéro).
    """
    texte = _normaliser(message)
    if not texte:
        return MESSAGE_AIDE

    if texte in SALUTATIONS or any(texte.startswith(mot) for mot in SALUTATIONS):
        return MESSAGE_AIDE

    for tentative in (_tenter_devis, _tenter_statut_commande, _tenter_info_produit):
        reponse = tentative(store, texte)
        if reponse:
            return reponse

    return "🤔 Je n'ai pas compris votre demande.\n\n" + MESSAGE_AIDE
