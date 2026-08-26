"""Logique métier du chatbot WhatsApp d'Ascale.

Ce module ne dépend pas de Flask : il prend un `Store` et un message texte,
et retourne une réponse texte. La même fonction `repondre()` est branchée sur :
  - la page de simulation /chatbot (via POST JSON)
  - le webhook WhatsApp Business réel (voir whatsapp_config.py)

Intents gérés (ordre de priorité) :
  1. Salutations / aide
  2. Devis (surface en m² + produit)
  3. Statut commande (numéro ou nom client)
  4. Catalogue complet
  5. Recherche par catégorie (marbre, granit, onyx, travertin)
  6. Info produit spécifique
  7. FAQ — horaires, adresse, livraison, paiement, entretien
  8. Actions — commander, réserver, contacter
  9. Remerciements / au revoir
 10. Fallback
"""

import re
import unicodedata
from itertools import count

_devis_ids = count(1)

MOTS_CLES_COMMANDE = ("commande", "statut", "suivi", "ou en est")

SALUTATIONS = {"bonjour", "salut", "bonsoir", "hello", "coucou", "slt", "bjr", "hey", "salam", "ahlan"}

REMERCIEMENTS = {"merci", "super", "parfait", "nickel", "ok", "cool", "top", "bien", "bravo", "excellent"}

AU_REVOIR = {"au revoir", "bye", "bonne journee", "bonne soiree", "a bientot", "ciao", "adieu", "tchao"}

INFO_ASCALE = {
    "adresse": "📍 Showroom Ascale — Casablanca, Maroc\nZone Industrielle Oukacha, Rue 7",
    "telephone": "📞 +212 5 22 XX XX XX",
    "email": "✉️ contact@ascale.ma",
    "horaires": "🕘 Lundi–Vendredi : 9h–13h / 14h–18h\n🕘 Samedi : 9h–13h\n🔴 Dimanche : Fermé",
    "livraison": (
        "🚚 Livraison disponible sur tout le Maroc.\n"
        "Délai moyen : 5–10 jours ouvrés selon la distance.\n"
        "Tarif calculé selon le volume et la destination."
    ),
    "paiement": (
        "💳 Modes de paiement acceptés :\n"
        "• Virement bancaire (RIB fourni sur devis)\n"
        "• Chèque certifié\n"
        "• Espèces (showroom uniquement)\n"
        "Un acompte de 30% est demandé à la confirmation de commande."
    ),
    "entretien_marbre": (
        "🧹 Entretien du marbre :\n"
        "• Nettoyage : chiffon humide + savon doux neutre\n"
        "• Évitez : vinaigre, citron, produits acides ou abrasifs\n"
        "• Protection : traitement hydrofuge annuel recommandé\n"
        "• Taches : essuyez immédiatement pour éviter l'absorption"
    ),
    "entretien_granit": (
        "🧹 Entretien du granit :\n"
        "• Très résistant aux acides et aux rayures\n"
        "• Nettoyage : eau savonneuse ordinaire\n"
        "• Imperméabilisation conseillée tous les 2 ans"
    ),
}

MESSAGE_AIDE = (
    "👋 Bienvenue chez *Ascale Marbre* !\n"
    "Spécialiste en marbre, granit et onyx haut de gamme.\n\n"
    "Je peux vous aider à :\n"
    "• 🔎 Consulter notre catalogue — ex. « quels produits avez-vous ? »\n"
    "• 💰 Obtenir un devis — ex. « je veux 20m² de Crema Marfil »\n"
    "• 📦 Suivre une commande — ex. « statut commande 3 »\n"
    "• 📅 Réserver une visite showroom — ex. « je veux réserver »\n"
    "• 🛒 Passer une commande en ligne — ex. « je veux commander »\n"
    "• ℹ️ Infos pratiques — horaires, adresse, livraison, paiement\n\n"
    "Que puis-je faire pour vous ?"
)

EXEMPLES = (
    "avez-vous du marbre blanc ?",
    "je veux 20m² de Crema Marfil",
    "statut commande 1",
    "quels sont vos horaires ?",
    "je veux réserver une visite",
)


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def _normaliser(texte: str) -> str:
    return _sans_accents(texte or "").lower().strip()


def _mots(texte: str) -> set:
    return set(re.findall(r"[a-z0-9]+", texte))


def _meilleur_produit(store, texte, score_min=1):
    """Retrouve le produit le plus probablement évoqué dans `texte`.

    Comparaison mot par mot (mots entiers) pour éviter les faux positifs
    comme « vert » détecté dans « travertin ».
    Retourne (produit, score). Retourne (None, 0) si score < score_min.
    """
    mots_message = _mots(texte)
    meilleur, meilleur_score = None, 0
    for produit in store.list_produits():
        mots_produit = [m for m in _normaliser(produit.nom).split() if len(m) > 2]
        score = sum(1 for m in mots_produit if m in mots_message)
        if score > meilleur_score:
            meilleur, meilleur_score = produit, score
    if meilleur_score < score_min:
        return None, 0
    return meilleur, meilleur_score


# ---------- Intent : Devis ----------

def _tenter_devis(store, texte):
    match_quantite = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|metres?\s*carr[ée]?s?)", texte)
    if not match_quantite:
        return None

    quantite = float(match_quantite.group(1).replace(",", "."))
    if quantite <= 0:
        return "💰 Merci d'indiquer une surface supérieure à 0 m² pour votre devis."

    produit, _ = _meilleur_produit(store, texte)
    if produit is None:
        return (
            "💰 Je n'ai pas identifié le matériau pour votre devis.\n"
            "Précisez son nom, ex. « je veux 20m² de Crema Marfil »."
        )

    total = produit.prix * quantite
    quantite_affichee = int(quantite) if quantite.is_integer() else quantite
    numero = next(_devis_ids)
    disponibilite = (
        "✅ en stock" if produit.stock >= quantite
        else f"⚠️ stock limité ({produit.stock} m² disponibles)"
    )

    return (
        f"💰 *Devis n°{numero}*\n"
        f"Matériau : {produit.nom}\n"
        f"Surface : {quantite_affichee} m²\n"
        f"Prix unitaire : {produit.prix:.0f} MAD/m²\n"
        f"*Total estimé : {total:.0f} MAD*\n"
        f"Disponibilité : {disponibilite}\n\n"
        f"Devis indicatif, sans engagement.\n"
        f"Pour confirmer, passez commande sur notre site ou contactez-nous."
    )


# ---------- Intent : Statut commande ----------

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
            "📦 Je n'ai trouvé aucune commande correspondante.\n"
            "Précisez le numéro (ex. « statut commande 3 ») ou votre nom exact."
        )

    lignes = "\n".join(
        f"  – {ligne.quantite} m² de {ligne.produit_nom} ({ligne.sous_total:.0f} MAD)"
        for ligne in commande.lignes
    )
    return (
        f"📦 *Commande n°{commande.id}* — {commande.client_nom}\n"
        f"Statut : *{commande.statut}*\n"
        f"Date : {commande.date.strftime('%d/%m/%Y')}\n"
        f"{lignes}\n"
        f"*Total : {commande.total:.0f} MAD*"
    )


# ---------- Intent : Catalogue complet ----------

def _tenter_catalogue(store, texte):
    mots_catalogue = (
        "catalogue", "produit", "materiaux", "materiau", "liste", "quoi",
        "vous avez", "avez vous", "qu est ce que", "proposez", "vendez", "gamme"
    )
    if not any(m in texte for m in mots_catalogue):
        return None

    produits = store.list_produits()
    if not produits:
        return "Notre catalogue est en cours de mise à jour. Contactez-nous directement."

    lignes = []
    for p in produits:
        stock_info = f"{p.stock} m²" if p.stock > 0 else "sur commande"
        lignes.append(f"  • {p.nom} — {p.prix:.0f} MAD/m² ({stock_info})")

    return (
        f"🏛️ *Catalogue Ascale* ({len(produits)} références)\n\n"
        + "\n".join(lignes)
        + "\n\nPour un devis, précisez la surface souhaitée (ex. « 15m² de Travertin »)."
    )


# ---------- Intent : Recherche par catégorie ----------

CATEGORIES_MOTS = {
    "marbre":    {"mots": ("marbre", "marble", "calcaire"), "pluriel": "marbres"},
    "granit":    {"mots": ("granit", "granite"),            "pluriel": "granits"},
    "onyx":      {"mots": ("onyx",),                        "pluriel": "onyx"},
    "travertin": {"mots": ("travertin", "travertine"),      "pluriel": "travertins"},
}


def _tenter_categorie(store, texte):
    categorie_trouvee = None
    pluriel = None
    for cat_nom, cfg in CATEGORIES_MOTS.items():
        if any(m in texte for m in cfg["mots"]):
            categorie_trouvee = cat_nom
            pluriel = cfg["pluriel"]
            break

    if categorie_trouvee is None:
        return None

    produits = store.list_produits_par_categorie(categorie_trouvee)
    if not produits:
        produits = [p for p in store.list_produits() if categorie_trouvee in _normaliser(p.nom)]

    if not produits:
        return f"Nous n'avons pas de {categorie_trouvee} en stock actuellement. Contactez-nous pour plus d'info."

    lignes = []
    for p in produits:
        stock_info = f"{p.stock} m² en stock" if p.stock > 0 else "⚠️ stock limité"
        lignes.append(f"  • {p.nom}\n    {p.prix:.0f} MAD/m² — {stock_info}")

    return (
        f"✅ Nos *{pluriel}* disponibles ({len(produits)} références) :\n\n"
        + "\n".join(lignes)
        + "\n\nPour un devis précis, indiquez la surface souhaitée."
    )


# ---------- Intent : Info produit spécifique ----------

def _tenter_info_produit(store, texte):
    # Score minimum 2 : évite que "avez-vous du marbre" (score 1)
    # soit traité comme une info produit plutôt qu'une recherche de catégorie.
    produit, _ = _meilleur_produit(store, texte, score_min=2)
    if produit is None:
        return None

    disponibilite = (
        f"{produit.stock} m² en stock" if produit.stock > 0
        else "⚠️ actuellement en rupture de stock"
    )
    description = f"\n📋 {produit.description}" if produit.description else ""
    categorie = f"\nCatégorie : {produit.categorie.nom}" if produit.categorie else ""

    return (
        f"✅ *{produit.nom}*{categorie}\n"
        f"Prix : *{produit.prix:.0f} MAD/m²*\n"
        f"Disponibilité : {disponibilite}"
        f"{description}\n\n"
        f"Pour un devis, précisez la surface souhaitée (ex. « je veux 15m² »)."
    )


# ---------- Intent : FAQ ----------

def _tenter_faq(store, texte):
    # Horaires
    if any(m in texte for m in ("horaire", "ouvert", "heure", "ferme", "quand")):
        return f"🕘 *Horaires Ascale*\n{INFO_ASCALE['horaires']}"

    # Adresse / localisation
    if any(m in texte for m in ("adresse", "ou etes", "trouver", "localisation", "showroom", "localiser", "situe")):
        return (
            f"{INFO_ASCALE['adresse']}\n"
            f"{INFO_ASCALE['telephone']}\n"
            f"{INFO_ASCALE['email']}\n\n"
            "Venez découvrir nos matériaux en personne !"
        )

    # Contact
    if any(m in texte for m in ("contact", "telephone", "appel", "joindre", "email", "mail")):
        return (
            f"📞 *Nous contacter*\n"
            f"{INFO_ASCALE['telephone']}\n"
            f"{INFO_ASCALE['email']}\n"
            f"{INFO_ASCALE['adresse']}\n\n"
            "Ou réservez directement une visite showroom."
        )

    # Livraison
    if any(m in texte for m in ("livraison", "livrer", "expedition", "transport", "delai", "recevoir")):
        return INFO_ASCALE["livraison"]

    # Paiement
    if any(m in texte for m in ("paiement", "payer", "modalite", "virement", "cheque", "acompte", "prix")):
        return INFO_ASCALE["paiement"]

    # Entretien
    if any(m in texte for m in ("entretien", "nettoyer", "nettoyage", "entretenir", "tache", "produit nettoyant")):
        if any(m in texte for m in ("granit",)):
            return INFO_ASCALE["entretien_granit"]
        return INFO_ASCALE["entretien_marbre"]

    # Différence marbre/granit
    if any(m in texte for m in ("difference", "choisir", "vs", "versus", "ou granit", "ou marbre", "lequel")):
        return (
            "🏛️ *Marbre vs Granit*\n\n"
            "**Marbre :**\n"
            "• Pierre calcaire métamorphique, veines naturelles uniques\n"
            "• Plus sensible aux acides (citron, vinaigre)\n"
            "• Idéal : intérieur, revêtement mural, salle de bain\n"
            "• Prix : 890–4800 MAD/m²\n\n"
            "**Granit :**\n"
            "• Pierre ignée très dure, quasi indestructible\n"
            "• Résiste aux acides, rayures et chaleur\n"
            "• Idéal : plan de travail cuisine, sol à fort trafic\n"
            "• Prix : 1100 MAD/m²\n\n"
            "Besoin d'un conseil personnalisé ? Réservez une visite showroom !"
        )

    return None


# ---------- Intent : Recommandations par usage ----------

USAGES = {
    "cuisine": {
        "mots": ("cuisine", "plan de travail", "cuisson"),
        "cat": "granit",
        "raison": "Le granit résiste aux acides (citron, vinaigre), à la chaleur et aux rayures — parfait en cuisine.",
    },
    "salle de bain": {
        "mots": ("salle de bain", "douche", "bain", "sanitaire", "wc", "sdb"),
        "cat": "marbre",
        "raison": "Le marbre et le travertin apportent élégance et facilité d'entretien à la salle de bain.",
    },
    "salon": {
        "mots": ("salon", "living", "sejour", "reception"),
        "cat": "marbre",
        "raison": "Un marbre Carrare ou Crema Marfil habille le salon d'une touche de luxe intemporel.",
    },
    "terrasse": {
        "mots": ("terrasse", "exterieur", "jardin", "piscine", "balcon"),
        "cat": "travertin",
        "raison": "Le travertin antidérapant et le granit résistent parfaitement aux intempéries en extérieur.",
    },
    "escalier": {
        "mots": ("escalier", "marche", "escaliers"),
        "cat": "granit",
        "raison": "Pour les escaliers, le granit et le marbre offrent durabilité et élégance à l'usage quotidien.",
    },
}


def _tenter_recommandation(store, texte):
    for usage, cfg in USAGES.items():
        if any(m in texte for m in cfg["mots"]):
            produits = store.list_produits_par_categorie(cfg["cat"])
            if not produits:
                produits = [p for p in store.list_produits() if cfg["cat"] in _normaliser(p.nom)]

            if not produits:
                return (
                    f"🏠 Pour *{usage}*, nous recommandons le {cfg['cat']}.\n"
                    f"{cfg['raison']}\nContactez-nous pour un conseil personnalisé."
                )

            lignes = "\n".join(
                f"  • {p.nom} — {p.prix:.0f} MAD/m² ({p.stock} m² en stock)"
                for p in produits[:3]
            )
            return (
                f"🏠 *Pour {usage}*, nous recommandons :\n\n"
                f"{lignes}\n\n"
                f"💡 {cfg['raison']}\n\n"
                f"Souhaitez-vous un devis ? Précisez la surface (ex. « 15m² »)."
            )
    return None


# ---------- Intent : Budget ----------

def _tenter_budget(store, texte):
    # Budget avec montant explicite
    match = re.search(
        r"(?:budget|moins de|max|sous|jusqu[a-z]*)\s*(\d[\d\s.,]*)\s*(?:mad|dh)?",
        texte
    )
    if match:
        budget_max = float(match.group(1).replace(" ", "").replace(",", "."))
        produits = [p for p in store.list_produits() if p.prix <= budget_max and p.stock > 0]
        if not produits:
            min_prix = min((p.prix for p in store.list_produits()), default=0)
            return (
                f"💰 Aucun matériau disponible sous {budget_max:.0f} MAD/m².\n"
                f"Notre gamme commence à {min_prix:.0f} MAD/m²."
            )
        lignes = "\n".join(
            f"  • {p.nom} — {p.prix:.0f} MAD/m²"
            for p in sorted(produits, key=lambda p: p.prix)
        )
        return (
            f"💰 *Matériaux disponibles sous {budget_max:.0f} MAD/m²* ({len(produits)}) :\n\n"
            f"{lignes}\n\nPour un devis, précisez la surface souhaitée."
        )

    # Budget qualitatif
    if any(m in texte for m in ("pas cher", "economique", "abordable", "moins cher", "petit budget", "accessible")):
        produits = sorted(store.list_produits(), key=lambda p: p.prix)[:4]
        lignes = "\n".join(f"  • {p.nom} — {p.prix:.0f} MAD/m²" for p in produits)
        return f"💚 *Nos matériaux les plus accessibles* :\n\n{lignes}\n\nTous les prix sont au m²."

    if any(m in texte for m in ("luxe", "premium", "haut de gamme", "meilleur", "exclusif")):
        produits = sorted(store.list_produits(), key=lambda p: p.prix, reverse=True)[:4]
        lignes = "\n".join(f"  • {p.nom} — {p.prix:.0f} MAD/m²" for p in produits)
        return f"✨ *Nos matériaux premium* :\n\n{lignes}\n\nL'excellence au service de vos projets."

    return None


# ---------- Intent : Actions (commander, réserver, contacter) ----------

def _tenter_action(texte):
    # Commander
    if any(m in texte for m in ("commander", "passer commande", "acheter", "achat", "je veux commander")):
        return (
            "🛒 *Passer une commande*\n\n"
            "Vous pouvez commander directement en ligne sur notre site :\n"
            "👉 /commander\n\n"
            "Ou contactez-nous pour une commande sur mesure :\n"
            "📞 +212 5 22 XX XX XX\n"
            "✉️ contact@ascale.ma"
        )

    # Réserver une visite
    if any(m in texte for m in ("reserver", "reservation", "visite", "rendez-vous", "rdv", "venir", "showroom")):
        return (
            "📅 *Réserver une visite showroom*\n\n"
            "Choisissez un créneau directement en ligne :\n"
            "👉 /reservation\n\n"
            "Nos créneaux sont disponibles du lundi au vendredi,\n"
            "matin (9h–13h) et après-midi (14h–18h).\n"
            "Confirmation immédiate par email."
        )

    # Devis par humain
    if any(m in texte for m in ("parler", "humain", "conseiller", "vendeur", "agent", "quelqu un")):
        return (
            "👤 *Parler à un conseiller*\n\n"
            "Notre équipe est disponible :\n"
            "📞 +212 5 22 XX XX XX\n"
            "✉️ contact@ascale.ma\n"
            f"🕘 {INFO_ASCALE['horaires']}"
        )

    return None


# ---------- Intent : Remerciements / Au revoir ----------

def _tenter_politesse(texte):
    mots = _mots(texte)

    if mots & REMERCIEMENTS:
        return (
            "😊 De rien, c'est avec plaisir !\n"
            "N'hésitez pas si vous avez d'autres questions sur nos matériaux."
        )

    for formule in AU_REVOIR:
        if formule in texte:
            return "Au revoir ! À très bientôt chez *Ascale Marbre*. 🏛️"

    return None


# ---------- Fonction principale ----------

def repondre(store, message: str, expediteur: str = "") -> str:
    """Calcule la réponse du chatbot à `message` pour un `store` donné.

    `expediteur` (numéro WhatsApp) est conservé pour la future identification
    du client par son numéro une fois le vrai webhook branché.
    """
    texte = _normaliser(message)
    if not texte:
        return MESSAGE_AIDE

    # Salutations → message d'aide
    if texte in SALUTATIONS or any(texte.startswith(mot) for mot in SALUTATIONS):
        return MESSAGE_AIDE

    # Politesse rapide (merci, au revoir) — avant tout le reste
    reponse_politesse = _tenter_politesse(texte)
    if reponse_politesse:
        return reponse_politesse

    # Actions (commander, réserver, contacter) — avant statut commande
    # pour éviter que "je veux commander" soit capturé par statut commande
    reponse_action = _tenter_action(texte)
    if reponse_action:
        return reponse_action

    # Intents par ordre de priorité
    for tentative in (
        _tenter_devis,
        _tenter_statut_commande,
        _tenter_budget,
        _tenter_recommandation,
        _tenter_faq,
        _tenter_catalogue,
        _tenter_info_produit,
        _tenter_categorie,
    ):
        reponse = tentative(store, texte)
        if reponse:
            return reponse

    # Fallback enrichi
    return (
        "🤔 Je n'ai pas compris votre demande.\n\n"
        + MESSAGE_AIDE
    )
