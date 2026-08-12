# Ascale — Gestion des ventes

Application Flask pour gérer clients, produits/stock et commandes.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Lancement

```powershell
python app.py
```

L'application est accessible sur http://127.0.0.1:5000

## Fonctionnalités

- Tableau de bord (nombre de produits, clients, chiffre d'affaires, dernières commandes)
- Gestion des clients : liste, ajout, modification, suppression
- Gestion des produits : liste, ajout, modification, suppression, suivi du stock
- Création de commandes multi-articles liées à un client, avec calcul automatique du total
- Décrémentation du stock en temps réel à la création d'une commande, et recréditation en cas de suppression
- Interface web responsive, pensée mobile d'abord

## Stockage des données

Il n'y a pas encore de base de données réelle : toutes les données (clients, produits,
commandes) vivent en mémoire dans l'objet `Store` (`models.py`), pré-rempli avec quelques
exemples au démarrage (`seed()`). Elles sont donc réinitialisées à chaque redémarrage de
l'application — c'est volontaire pour cette étape du projet. `Store` est conçu comme un
point d'entrée unique vers les données, pour pouvoir être remplacé plus tard par une
vraie base de données sans toucher aux routes.

## Structure du projet

```
app.py                        # Application Flask et routes
models.py                     # Modèles de données + stockage en mémoire (Store)
templates/
    base.html                  # Layout commun (nav, messages flash)
    index.html                 # Tableau de bord
    clients.html               # Liste + ajout des clients
    modifier_client.html       # Modification d'un client
    produits.html               # Liste + ajout des produits
    modifier_produit.html      # Modification d'un produit
    commandes.html             # Liste des commandes
    nouvelle_commande.html     # Création d'une commande multi-articles
static/
    style.css                  # Styles (mobile-first)
```

## À venir

- Chatbot WhatsApp
- Système de réservation
- Persistance en base de données réelle
