# Ascale — Site vitrine

Application Flask : vitrine haut de gamme (accueil, matériaux, commande en ligne,
réservation showroom, chatbot), accessible sans connexion.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration de l'envoi d'email (réservations, factures, contact)

Les emails sont envoyés via l'API HTTPS de [Brevo](https://www.brevo.com) (pas de SMTP
direct — beaucoup d'hébergeurs, dont le plan gratuit de Render, bloquent ou dégradent
silencieusement les connexions SMTP sortantes). Il faut renseigner un compte Brevo dans
un fichier `.env` (non commité) :

```powershell
copy .env.example .env
```

Puis éditer `.env` et renseigner :
- `BREVO_API_KEY` — générée dans Brevo → Réglages → Clés API
- `BREVO_SENDER_EMAIL` — adresse d'envoi, **doit être vérifiée** dans Brevo au préalable
- `BREVO_SENDER_NAME` — optionnel, nom affiché dans le champ "De :"

Tant que `BREVO_API_KEY`/`BREVO_SENDER_EMAIL` ne sont pas renseignés, l'application fonctionne
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
- Commande en ligne (`/commander`) : sélection de produits, coordonnées, paiement (simulé), facture PDF générée et envoyée par email
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
app.py                          # Application Flask : routes du site public
models.py                       # Modèles de données + stockage en mémoire (Store)
chatbot.py                      # Logique métier du chatbot (indépendante de Flask)
whatsapp_config.py              # Préparation du branchement à la vraie API WhatsApp Business
email_service.py                # Envoi des emails (réservation, facture, contact) — API Brevo
facture_service.py              # Génération de la facture PDF (fpdf2)
templates/
    base_public.html             # Layout du site public (nav, footer, animations au scroll)
    accueil.html                 # Page d'accueil publique
    nos_materiaux.html           # Catalogue public des matériaux
    commander.html               # Commande en ligne — sélection produits
    paiement.html                # Commande en ligne — adresse + paiement
    recu.html                    # Reçu de commande + téléchargement facture
    commande_confirmee.html      # Confirmation de commande
    reservation.html             # Réservation publique de créneaux
    reservation_confirmee.html   # Confirmation + animation de succès + statut email/SMS
    email_confirmation_reservation.html  # Gabarit HTML de l'email de confirmation
    chatbot.html                 # Expérience de chat publique (effet de frappe)
    contact.html                 # Formulaire de contact
static/
    public.css                   # Styles du site public (palette et identité propres)
    public.js                    # Apparition au scroll (IntersectionObserver)
```

## À venir

- Activation du vrai compte WhatsApp Business (API Meta)
- Persistance en base de données réelle
