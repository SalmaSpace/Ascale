# Ascale — Site vitrine &amp; gestion des ventes

Application Flask avec deux espaces distincts :
- **Site public** (`/`) : vitrine haut de gamme (accueil, matériaux, réservation, chatbot), accessible sans connexion.
- **Espace de gestion interne** (`/gestion`) : clients, produits/stock, commandes, réservations — protégé par connexion pour la partie réservations.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration de l'envoi d'email (réservations)

L'email de confirmation de réservation est réellement envoyé (pas une simulation). Il faut
renseigner un compte SMTP dans un fichier `.env` (non commité) :

```powershell
copy .env.example .env
```

Puis éditer `.env` et renseigner :
- `MAIL_USERNAME` — l'adresse email d'envoi (ex. Gmail)
- `MAIL_PASSWORD` — un **mot de passe d'application** (pas le mot de passe du compte),
  généré sur https://myaccount.google.com/apppasswords une fois la validation en deux
  étapes activée sur le compte
- `MAIL_DEFAULT_SENDER` — optionnel, reprend `MAIL_USERNAME` si laissé vide

Tant que `MAIL_USERNAME`/`MAIL_PASSWORD` ne sont pas renseignés, l'application fonctionne
normalement mais n'envoie pas l'email (la page de confirmation l'indique clairement).

## Lancement

```powershell
python app.py
```

L'application est accessible sur http://127.0.0.1:5000

## Fonctionnalités

### Site public

- Accueil (`/`) : présentation de la maison, matériaux phares, appels à l'action
- Catalogue (`/nos-materiaux`) : tous les matériaux avec prix indicatif au m²
- Réservation de créneaux de visite showroom (`/reservation`), sans connexion requise — email de confirmation réellement envoyé (voir "Configuration de l'envoi d'email"), SMS encore en simulation
- Chatbot WhatsApp (simulation, `/chatbot`) : questions produits, devis automatique, suivi de commande, effet de frappe — en attendant l'activation du vrai compte WhatsApp Business

### Espace de gestion interne (`/gestion`)

- Tableau de bord (nombre de produits, clients, chiffre d'affaires, dernières commandes)
- Gestion des clients : liste, ajout, modification, suppression
- Gestion des produits : liste, ajout, modification, suppression, suivi du stock
- Création de commandes multi-articles liées à un client, avec calcul automatique du total
- Décrémentation du stock en temps réel à la création d'une commande, et recréditation en cas de suppression
- Widget chatbot flottant accessible sur tout l'espace de gestion
- Gestion des réservations (liste, annulation), protégée par connexion (`/admin/reservations`)
- Interface web responsive, pensée mobile d'abord

### Connexion à l'espace de gestion (réservations)

Accès protégé par connexion sur `/connexion`. Identifiants de démo :
- Email : `nasser@ascale.ma`
- Mot de passe : `Marbre2026!`

## Stockage des données

Il n'y a pas encore de base de données réelle : toutes les données (clients, produits,
commandes) vivent en mémoire dans l'objet `Store` (`models.py`), pré-rempli avec quelques
exemples au démarrage (`seed()`). Elles sont donc réinitialisées à chaque redémarrage de
l'application — c'est volontaire pour cette étape du projet. `Store` est conçu comme un
point d'entrée unique vers les données, pour pouvoir être remplacé plus tard par une
vraie base de données sans toucher aux routes.

## Structure du projet

```
app.py                          # Application Flask : routes des deux espaces, login_required
models.py                       # Modèles de données + stockage en mémoire (Store)
chatbot.py                      # Logique métier du chatbot (indépendante de Flask)
whatsapp_config.py              # Préparation du branchement à la vraie API WhatsApp Business
email_service.py                # Envoi de l'email de confirmation de réservation (SMTP réel)
templates/
    base_public.html             # Layout du site public (nav, footer, animations au scroll)
    accueil.html                 # Page d'accueil publique
    nos_materiaux.html           # Catalogue public des matériaux
    reservation.html             # Réservation publique de créneaux
    reservation_confirmee.html   # Confirmation + animation de succès + statut email/SMS
    email_confirmation_reservation.html  # Gabarit HTML de l'email de confirmation
    chatbot.html                 # Expérience de chat publique (effet de frappe)
    base.html                    # Layout de l'espace de gestion interne (nav, widget chatbot)
    index.html                   # Tableau de bord interne
    clients.html                 # Liste + ajout des clients
    modifier_client.html         # Modification d'un client
    produits.html                 # Liste + ajout des produits
    modifier_produit.html        # Modification d'un produit
    commandes.html               # Liste des commandes
    nouvelle_commande.html       # Création d'une commande multi-articles
    connexion.html               # Connexion à l'espace de gestion
    admin_reservations.html      # Gestion des réservations (protégée)
static/
    public.css                   # Styles du site public (palette et identité propres)
    public.js                    # Apparition au scroll (IntersectionObserver)
    style.css                    # Styles de l'espace de gestion interne (mobile-first)
```

## À venir

- Activation du vrai compte WhatsApp Business (API Meta)
- Extension de l'authentification à l'ensemble de la gestion interne
- Persistance en base de données réelle
