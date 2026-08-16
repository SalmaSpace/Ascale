# Skills.md

Ce fichier sert de mémoire technique du projet **Ascale** pour Claude Code, et regroupe aussi les points à retenir pour le rapport et la présentation. Il doit rester à jour : à chaque changement notable, compléter les sections concernées plutôt que les réécrire de zéro.

## Commandes

```powershell
# Installation
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Configuration email (facultatif, voir section "Envoi d'email réel" plus bas)
copy .env.example .env
# puis renseigner MAIL_USERNAME / MAIL_PASSWORD / MAIL_DEFAULT_SENDER dans .env

# Lancement (mode debug, auto-reload) — http://127.0.0.1:5000
python app.py
```

Aucun test automatisé, linter ou build n'est configuré dans ce dépôt à ce stade.

## ⚠️ Deux espaces séparés depuis la refonte du site public

Depuis la refonte de l'espace public (accueil / matériaux / réservation / chatbot), l'app a **deux layouts totalement indépendants** :
- **Espace public** (`base_public.html` + `static/public.css` + `static/public.js`) : `/`, `/nos-materiaux`, `/reservation`, `/chatbot`. Design "maison de luxe", voir section dédiée ci-dessous.
- **Espace de gestion interne** (`base.html` + `static/style.css`), **volontairement non touché** lors de cette refonte : `/gestion` (ex-`/`, tableau de bord), `/produits`, `/clients`, `/commandes`, `/connexion`, `/admin/reservations`.

Les deux feuilles de style sont indépendantes par design (aucune règle partagée) pour garantir que retoucher l'une ne casse jamais l'autre. Si une future demande porte sur l'un des deux espaces, ne pas modifier l'autre sans qu'on le demande explicitement.

## Architecture

Application Flask pour gérer clients, produits/stock et commandes d'un négoce de marbre de luxe (données de démo). Tout tient en deux fichiers Python :

- **`models.py`** — modélisation des données et logique métier. `Store` est un dépôt en mémoire (dicts indexés par id auto-incrémenté) qui sert de seul point d'accès aux données `Client`, `Produit`, `Commande`/`LigneCommande` (dataclasses). Ce choix est volontaire : `Store` peut plus tard être remplacé par une vraie base de données sans toucher aux routes. `seed()` peuple des données de démo au démarrage. Les données sont réinitialisées à chaque redémarrage (voir "Travaux prévus" ci-dessous).
- **`app.py`** — `create_app()` construit l'app Flask, attache `app.store = Store()`, l'alimente via `seed()`, puis appelle `register_routes(app)` qui déclare toutes les routes en closures sur `store`. Toutes les routes sont dans une seule fonction (pas de blueprints).

Logique métier importante (commandes) :
- `Store.creer_commande()` valide chaque ligne demandée (produit existant, quantité > 0, stock suffisant) **avant** de modifier le moindre stock, pour éviter une décrémentation partielle en cas d'erreur. Stock insuffisant → `StockInsuffisantError` ; autre erreur de validation → `ValueError`. Les deux sont interceptées dans `app.py` et affichées via `flash()`.
- `Store.supprimer_commande()` recrédite le stock de chaque ligne de la commande supprimée.
- Le stock et les prix sont exprimés au m² (dalles), cohérent avec le domaine marbre/pierre.

Les templates (`templates/`) héritent de `base.html` (nav + messages flash) et sont stylés mobile-first via `static/style.css`. Les noms de routes et de templates sont en français et se correspondent (ex. `modifier_client` ↔ `modifier_client.html`).

### Chatbot WhatsApp (Semaine 6 du planning de stage)

Livrable attendu selon `Stage/Planning Stage.pdf` : configuration API WhatsApp Business, scénarios de réponses automatiques, génération de devis, suivi de commande. Le vrai compte WhatsApp Business n'est pas encore activé (à faire avec Nasser) — la logique métier est donc développée et testable dès maintenant via une page de simulation, prête à être branchée sur l'API réelle sans réécriture.

- **`chatbot.py`** — toute la logique métier du bot, indépendante de Flask (prend un `Store` + un message texte, retourne une réponse texte). Fonction d'entrée : `repondre(store, message, expediteur="")`. Trois intentions traitées dans cet ordre de priorité : devis (`_tenter_devis`, déclenché par une quantité en m²), statut de commande (`_tenter_statut_commande`, par numéro de commande ou nom de client), puis question produit (`_tenter_info_produit`). Reconnaissance par mots-clés + comparaison de **mots entiers** (pas de sous-chaînes, pour éviter les faux positifs type "vert" détecté dans "travertin") — pas de dépendance NLP externe.
- **`whatsapp_config.py`** — prépare le branchement à la vraie API WhatsApp Business Cloud (Meta) : lit les identifiants (`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN`) depuis des variables d'environnement, inactif tant qu'ils ne sont pas renseignés (`api_configuree()`).
- **`app.py`** — routes `/chatbot` (page de simulation façon WhatsApp, historique conservé en session Flask, plafonné à 30 messages), `/chatbot/envoyer` (POST, appelle `chatbot.repondre`), `/chatbot/reinitialiser`. Webhook `/webhook/whatsapp` (GET = vérification Meta, POST = réception des messages) déjà présent mais inerte tant que `whatsapp_config.api_configuree()` est faux — c'est le point où brancher le vrai compte plus tard.
- **`templates/chatbot.html`** — interface de simulation (bulles de conversation, style WhatsApp mais palette et typographie du reste du site), avec suggestions de messages d'exemple pour faciliter la démo.
- **`models.py`** — ajout de `Commande.statut` (propriété calculée à partir de l'ancienneté de la commande : Enregistrée / En préparation / Expédiée / Livrée). C'est un **placeholder assumé** en l'absence de vrai module de suivi logistique — à mentionner explicitement comme limitation connue si la question est posée en soutenance.

### Design : accent doré + animations (`static/style.css`)

À la demande de l'utilisateur, ajout d'une touche de couleur et de micro-animations sur l'ensemble de l'app, sans casser la charte "sobre" existante :
- Nouvelle palette accent doré (`--accent-50` à `--accent-700`), inspirée des veines dorées des marbres/onyx haut de gamme — cohérent avec le positionnement "négoce de marbre de luxe". Utilisé sur : icône stat "Clients", bordure du CTA "Nouvelle commande", indicateur "Simulation" du chatbot, bordure des bulles du bot, survol des lignes de tableau.
- Animations discrètes : entrée en cascade des cartes du tableau de bord et des lignes de tableau (`riseIn`/`fadeInSoft` avec délais échelonnés), effet de brillance au survol du bouton "Nouvelle commande", pastille de statut du chatbot pulsante, icônes de stat qui pivotent légèrement au survol, bouton burger de nav qui tourne à l'ouverture, boutons avec léger effet de "lift" + press.
- Respecte `prefers-reduced-motion` (déjà géré globalement dans le CSS existant, applicable aux nouvelles animations).

### Widget flottant WhatsApp (`templates/base.html`, toutes les pages)

Bouton rond vert (`#25d366`, couleur de marque WhatsApp — volontairement hors palette du site pour rester immédiatement identifiable) fixé en bas à droite, présent sur toutes les pages sauf `/chatbot` elle-même (évite la redondance). Au chargement de chaque page, une bulle de bienvenue *« Bonjour ! En quoi puis-je vous aider ? »* apparaît automatiquement après un court délai (animation CSS). Un petit script inline dans `base.html` gère la fermeture (bouton ×) et mémorise le choix via `sessionStorage` pour ne pas la réafficher à chaque navigation au sein de la même session navigateur.

**La discussion se déroule directement dans le widget, sans changer de page** (demande explicite de l'utilisateur : ne pas rediriger vers `/chatbot`) :
- Ouverture/fermeture du panneau de chat en **CSS pur** via une case à cocher cachée (`#wa-toggle`) — même technique que le menu burger mobile, pas de JS nécessaire pour l'état ouvert/fermé.
- L'envoi d'un message dans le panneau utilise `fetch()` vers `POST /chatbot/widget/envoyer` (nouvelle route JSON dans `app.py`, factorisée avec `/chatbot/envoyer` via `_chatbot_repondre_et_stocker()`) : la réponse du bot est injectée dans le DOM (`textContent`, jamais `innerHTML`, pour éviter toute injection) sans recharger la page.
- L'historique de conversation reste stocké dans la même clé de session Flask (`chatbot_conversation`) que la page `/chatbot` complète : les deux vues restent synchronisées. Un context processor (`injecter_widget_chatbot`) rend cet historique disponible dans `base.html` sur toutes les pages sans le passer explicitement depuis chaque route.
- Le lien "Chatbot" a été retiré du menu de navigation **interne** à la demande de l'utilisateur (le widget flottant y reste le seul accès). **Mise à jour depuis la refonte de l'espace public** : `/chatbot` a maintenant sa propre expérience dédiée sur le site public (nav "Contact" + CTA un peu partout) — voir section suivante. Le widget flottant décrit ci-dessus continue d'exister tel quel sur l'espace de gestion interne (non touché), les deux expériences partagent le même historique de session.

### Système de réservation de créneaux (Semaine 7 du planning de stage)

Basé sur le MCD (`Stage/MCD.png` / `MLD.png`) : entité `CRENEAU` (id_creneau, date_creneau, heure_debut, heure_fin, disponible) et association `RESERVER` (date_reservation, statut), avec côté CRENEAU une cardinalité **0,1** — un créneau ne peut être réservé qu'une seule fois, ce qui impose nativement la règle « pas de double réservation ». Réservations pour des visites showroom, par demi-journée (9h–13h / 14h–18h).

- **`models.py`** — dataclasses `Creneau`, `Reservation`, `Utilisateur` + `CreneauIndisponibleError`. `Store.reserver_creneau(creneau_id, nom, telephone)` vérifie `disponible` avant toute création (même pattern défensif que `creer_commande` : tout valider avant de muter l'état) ; `Store.annuler_reservation()` recrédite le créneau (même pattern que `supprimer_commande` pour le stock). **Écart assumé par rapport au MCD strict** : `Reservation` stocke `client_nom`/`client_telephone` directement plutôt qu'une FK vers `CLIENT` — la réservation est publique et ne doit pas forcer la création d'une fiche client dans le CRM interne pour un simple visiteur.
- **`app.py`** — routes publiques `/reservation` (liste des créneaux groupés par jour via `itertools.groupby`) et `/reservation/confirmer` → `/reservation/confirmee/<id>` (POST-redirect-GET, comme le reste de l'app). Filtre Jinja `date_fr` (dans `app.py`, pas de dépendance à la locale système pour rester portable).
- **Espace de gestion interne protégé par connexion** (entité `UTILISATEUR` du MCD) : `/connexion` (email + mot de passe, hashés via `werkzeug.security`, déjà une dépendance de Flask — aucun package ajouté), décorateur `login_required` (session Flask `utilisateur_id`), `/admin/reservations` (liste + annulation) et `/deconnexion`. **Identifiants de démo** : `nasser@ascale.ma` / `Marbre2026!` (créés dans `seed()`).
- **Portée volontairement limitée** : seule la nouvelle page `/admin/reservations` est protégée par connexion. Les pages Produits/Clients/Commandes existantes restent en accès libre (non demandé dans cette itération) — prochaine étape logique : étendre `login_required` à l'ensemble de la gestion interne pour rester cohérent avec l'entité `UTILISATEUR` du MCD (qui gère aussi les commandes via l'association `Gérer`).
- **Notification de confirmation simulée** : la page `reservation_confirmee.html` affiche un encart « Notification envoyée (simulation) », même logique que le chatbot WhatsApp en attendant une vraie intégration SMS/e-mail.
- Lien "Connexion"/"Gérer réservations"/"Déconnexion" adapté dynamiquement selon `session.get('utilisateur_id')` dans `base.html` (nav interne). **Mise à jour depuis la refonte de l'espace public** : `/reservation` a quitté la nav interne pour rejoindre la nav du site public — voir section suivante.

### Refonte de l'espace public (accueil, matériaux, réservation, chatbot)

Demande explicite : faire de l'espace public (Accueil / Nos matériaux / Réservation / Chatbot) une expérience "maison de luxe" — bijouterie/galerie d'art plutôt que site e-commerce — avec une identité visuelle et des animations propres, **sans toucher à l'espace de gestion interne**.

**Séparation totale des deux espaces** (voir avertissement en haut de ce fichier) :
- `templates/base_public.html` + `static/public.css` + `static/public.js` = layout, palette et JS du site public. Aucune règle CSS partagée avec `style.css` (l'espace interne charge uniquement `style.css`, l'espace public uniquement `public.css` — zéro risque de collision dans un sens comme dans l'autre).
- Palette dédiée dans `public.css` (`--pub-*`) : ivoire/blanc cassé (`--pub-ivory`), anthracite profond (`--pub-ink`, `--pub-anthracite`), doré (`--pub-gold-500/600/700`, **mêmes valeurs hexadécimales** que l'accent doré de l'espace interne, pour une cohérence de marque globale malgré la séparation technique des feuilles de style). Typographie Playfair Display (titres) + Inter (texte), déjà chargées via Google Fonts.
- **Restructuration des routes** (`app.py`) : `/` sert désormais l'accueil public (`accueil()`) au lieu de l'ancien tableau de bord. Le tableau de bord interne a été déplacé sur `/gestion` (même endpoint Flask `index`, donc **zéro modification** de `templates/base.html` ou `templates/index.html` — tous les `url_for('index')` internes continuent de fonctionner sans changement). Nouvelle route `/nos-materiaux` (catalogue public en lecture seule, distinct de `/produits` qui reste l'écran de gestion CRUD interne).
- **Pages** :
  - `accueil.html` — hero plein écran (texture de veinage en CSS pur, pas de vraie photo produit disponible dans l'app), présentation courte, 3 arguments (sourcing / exigence / accompagnement), 4 produits phares (sélection par nom dans `accueil()`, repli sur les 4 premiers produits si les noms ne correspondent pas), CTA final.
  - `nos_materiaux.html` — même style de carte produit, catalogue complet (`store.list_produits()`).
  - `reservation.html` / `reservation_confirmee.html` — **logique métier identique** (mêmes routes, mêmes champs de formulaire `creneau_id`/`nom`/`telephone`), seul l'habillage change : sélecteur de créneaux en pastilles dorées (`:has(input:checked)`), champs "floating label" en CSS pur (`:not(:placeholder-shown)`), animation de succès (coche SVG dessinée via `stroke-dashoffset`) sur la confirmation.
  - `chatbot.html` — passe d'un simple formulaire POST-redirect à un envoi **`fetch()`** vers `/chatbot/widget/envoyer` (route JSON déjà existante, réutilisée) avec un indicateur de frappe (3 points qui rebondissent, délai minimum simulé de 650 ms même si la réponse serveur est quasi instantanée) avant l'apparition douce de la bulle de réponse. Historique de conversation toujours dans la session Flask (`chatbot_conversation`), donc synchronisé avec le widget flottant de l'espace interne.
- **Vignettes produit sans photo** : pas de gestion d'images dans l'app, donc chaque carte matériau affiche un dégradé CSS abstrait évoquant le veinage (7 variantes selon des mots-clés du nom : noir/onyx/vert/rose/beige-travertin-crema/granit/blanc par défaut), via le filtre Jinja `swatch` (`app.py`). Point à assumer clairement en soutenance si la question est posée : c'est un choix design pour combler l'absence de vraies photos, pas un oubli.
- **Animations** (toutes dans `public.css`/`public.js`, respectent `prefers-reduced-motion`) :
  - Apparition au scroll (`.reveal` + `IntersectionObserver` dans `public.js`) sur quasiment tous les blocs, avec délais échelonnés sur les grilles de cartes.
  - Survol des cartes produit : légère élévation + zoom doux du dégradé de fond.
  - Transition de page en CSS pur via `@view-transition { navigation: auto; }` (API récente, ignorée silencieusement sur les navigateurs qui ne la supportent pas encore — amélioration progressive, pas de JS de routing).
  - Menu mobile plein écran avec hamburger → croix animé en CSS pur (3 barres, pas de dépendance à une icône externe pour cet élément précis).
- **Aucune dépendance ajoutée** : CSS pur + `IntersectionObserver` natif, comme demandé (pas de librairie d'animation).

### Widget de chat flottant premium (site public uniquement)

Ajouté sur toutes les pages publiques (sauf `/chatbot` elle-même, pour éviter la redondance), inspiré du niveau de finition Intercom/Crisp, en plus de la page `/chatbot` dédiée — les deux partagent le même historique de session (`chatbot_conversation`) et les mêmes routes JSON (`/chatbot/widget/envoyer`, `/chatbot/reinitialiser`). **N'existe que dans `base_public.html` + `public.css`** : l'ancien widget flottant de l'espace de gestion interne (`base.html`/`style.css`, thème WhatsApp vert) n'a pas été touché, à la demande explicite de l'utilisateur.

- **Bulle flottante** : dégradé doré (`gold-300 → gold-500 → gold-700`, identique au dégradé du logo "A") avec icône anthracite foncé pour le contraste — **mise à jour** après retour utilisateur (la version initiale en dégradé anthracite était jugée trop discrète). Ombre portée profonde en plusieurs couches teintée dorée (pas une ombre plate), halo doré qui respire doucement en continu (`pubWidgetHalo`, opacité 0.16→0.55, jamais un clignotement franc), icône de bulle de discussion dessinée à la main en SVG fin (`stroke-width: 1.6`, pas d'icône épaisse).
- Lien "Contact" retiré du menu de navigation du haut à la demande de l'utilisateur (jugé redondant avec le chatbot) — laissé tel quel dans le pied de page.
- **Bulle "Besoin d'aide ?"** : effet verre dépoli réel (`backdrop-filter: blur(18px) saturate(160%)` sur fond blanc cassé semi-transparent), typographie Playfair Display pour le titre, petite pointe triangulaire (`::after` tourné à 45°) qui la relie visuellement à la bulle flottante. Se ferme via un bouton × (mémorisé en `sessionStorage`, comme l'ancien widget interne) et se referme aussi automatiquement dès qu'on ouvre la conversation.
- **Fenêtre de conversation** : coins très arrondis (24px) + ombre large et diffuse pour l'effet de profondeur, en-tête anthracite avec liseré doré en dégradé, avatar "A" doré, statut "En ligne" avec pastille verte discrète. Fond de la fenêtre en ivoire (pas blanc pur). Bulles à coins asymétriques façon vraie messagerie (`border-radius: 4px 18px 18px 18px` pour le bot, inversé pour le client), bulles client en dégradé doré, bulles bot blanches à bordure fine. Champ de saisie arrondi + bouton d'envoi circulaire doré, cohérents avec le reste du site.
- Ouverture/fermeture toujours en **CSS pur** (case à cocher cachée, même technique que le reste du site), envoi de message en `fetch()` avec indicateur de frappe, comme la page `/chatbot` dédiée.

### Envoi d'email réel de confirmation de réservation

Contrairement au chatbot WhatsApp (simulation en attendant l'API) et au SMS (toujours en simulation, pas d'API SMS branchée), **l'email de confirmation est réellement envoyé** via SMTP (Flask-Mail).

- **`email_service.py`** — module dédié (même esprit que `whatsapp_config.py`) : lit `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS`/`MAIL_USERNAME`/`MAIL_PASSWORD`/`MAIL_DEFAULT_SENDER` depuis l'environnement (chargées depuis `.env` via `python-dotenv`, appelé tout en haut de `app.py` avant les autres imports). `mail_configuree()` retourne False tant que `MAIL_USERNAME`/`MAIL_PASSWORD` sont vides — l'envoi est alors silencieusement ignoré (pas d'exception, ne bloque jamais la réservation). `envoyer_confirmation_reservation()` catche toute erreur SMTP et retourne False plutôt que de laisser planter la requête — la réservation est déjà enregistrée avant l'appel, un souci d'envoi ne doit jamais faire perdre le créneau au client.
- **`.env`** (non commité, voir `.gitignore`) / **`.env.example`** (commité, sert de documentation) : c'est ici que renseigner les vrais identifiants SMTP. **Le fichier `.env` du dépôt est actuellement vide** (MAIL_USERNAME/MAIL_PASSWORD à blanc) — l'utilisateur doit les fournir.
- **`models.py`** — `Reservation` a deux nouveaux champs : `client_email` (obligatoire, désormais demandé dans le formulaire à côté du téléphone) et `email_envoye: bool` (mis à jour après coup dans `app.py`, une fois le résultat de l'envoi connu — mutation directe sur l'objet en mémoire, même style que `produit.stock -= quantite` ailleurs dans le code).
- **`templates/email_confirmation_reservation.html`** — gabarit HTML de l'email, volontairement en styles inline (pas de CSS externe : les clients mail ne le supportent pas de façon fiable), reprenant la palette doré/anthracite et le bloc "A" du logo.
- **Page de confirmation** (`reservation_confirmee.html`) : deux blocs de statut bien séparés visuellement — email (vert si envoyé, neutre si non configuré) et SMS (doré, toujours étiqueté "à venir"/simulation) — pour ne jamais laisser croire qu'un SMS a été envoyé.
- **Statut confirmé en production locale** : email réellement envoyé et reçu (testé par l'utilisateur), `.env` rempli avec un compte Gmail + mot de passe d'application. Le bloc "SMS (à venir)" a été retiré de `reservation_confirmee.html` à la demande de l'utilisateur (pas de canal SMS prévu) — seul le statut email reste affiché (`.pub-notif-reelle` si envoyé, `.pub-notif-attente` sinon).
- **Piège rencontré en debug** : après avoir rempli `.env`, un test montrait encore "Email non envoyé" malgré des identifiants valides. Cause réelle : plusieurs processus `python app.py` s'étaient accumulés sur le port 5000 au fil des relances successives dans la session (le `taskkill` via Git Bash sur un PID lu par `netstat` ne suffit pas toujours à tout nettoyer, et Git Bash peut afficher des entrées `netstat` obsolètes/dupliquées). Le navigateur tapait sur un ancien processus qui avait chargé un `.env` vide/cassé à son propre démarrage. **Pour relancer proprement le serveur** : utiliser PowerShell (`Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"` pour lister, `Stop-Process -Id ... -Force` pour tuer), plus fiable que `netstat`/`taskkill` via Git Bash sur cet environnement — puis vérifier qu'un seul processus tourne avant de retester.
- **Variables d'environnement à donner à l'utilisateur pour activer l'envoi réel** (voir `.env.example`) :
  - `MAIL_USERNAME` — adresse Gmail d'envoi
  - `MAIL_PASSWORD` — un **mot de passe d'application** Gmail (pas le mot de passe du compte), à générer sur https://myaccount.google.com/apppasswords une fois la validation en deux étapes activée
  - `MAIL_DEFAULT_SENDER` — optionnel, reprend `MAIL_USERNAME` si vide
  - `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS` — déjà préremplis pour Gmail (`smtp.gmail.com`, `587`, `true`), à ne changer que pour un autre fournisseur SMTP.

## Choix de conception (pour le rapport)

- **Persistance en mémoire volontaire** : à ce stade, `Store` remplace une base de données. C'est un choix assumé pour avancer vite sur les fonctionnalités avant de brancher une vraie persistance — à mentionner comme décision d'architecture réfléchie (séparation claire entre logique métier et accès aux données), pas comme une limitation subie.
- **Validation atomique des commandes** : toute la commande est vérifiée avant toute modification de stock, ce qui évite les incohérences (ex. stock décrémenté pour certains articles mais pas d'autres si une erreur survient en cours de route). Bon exemple concret de robustesse métier à citer dans un rapport.
- **Gestion du stock en temps réel** : décrémentation à la création d'une commande, recréditation automatique à la suppression — traçabilité et cohérence des données.
- **Design** : refonte visuelle avec palette sobre, typographie soignée et icônes Feather, interface pensée mobile-first (voir commit "Refonte du design") — pour l'espace de gestion interne. L'espace public a sa propre identité "maison de luxe" (ivoire/anthracite/doré, Playfair Display) volontairement distincte, sur une feuille de style totalement séparée.
- **Données de démonstration** : jeu de données réaliste (négoce de marbre de luxe : clients, produits, commandes) pour rendre les démos et captures d'écran parlantes en présentation.
- **Chatbot découplé de Flask** : `chatbot.repondre(store, message)` ne dépend que de `Store`, pas du framework web — bon exemple d'architecture pensée pour être branchée sur un autre transport (webhook WhatsApp réel) sans réécrire la logique. Le webhook `/webhook/whatsapp` existe déjà mais reste inerte tant que les identifiants ne sont pas configurés : à présenter comme "logique métier et architecture prêtes, il ne manque que l'activation du compte" plutôt que comme une fonctionnalité inachevée.
- **Statut de commande simulé** : `Commande.statut` est calculé à partir de l'ancienneté de la commande, faute d'un vrai système de suivi logistique. Assumé comme limitation connue, à présenter comme prochaine étape (statut stocké et mis à jour par l'équipe plutôt que déduit).

## Travaux prévus (non implémentés)

D'après le README et le planning de stage : persistance en base de données réelle (remplacement de `Store`), et l'extension de l'authentification à l'ensemble de la gestion interne (Produits/Clients/Commandes, aujourd'hui en accès libre). Le chatbot WhatsApp (Semaine 6) a une logique métier et une interface de simulation fonctionnelles ; il reste à activer le vrai compte WhatsApp Business (API Meta) pour le rendre pleinement opérationnel. Le système de réservation (Semaine 7) est fonctionnel de bout en bout (créneaux, réservation publique, gestion interne protégée). Vraies photos produit à intégrer un jour à la place des vignettes CSS abstraites, si des visuels professionnels deviennent disponibles.

## Notes pour le rapport / la présentation

- Stack : Python + Flask, rendu côté serveur (Jinja2), pas de framework JS lourd — seulement de petits scripts ciblés en JS natif (widget chatbot interne, chat public avec effet de frappe, apparition au scroll via `IntersectionObserver`). Aucune librairie d'animation ou de framework front ajoutée.
- Points forts à mettre en avant : architecture simple et claire (séparation modèles/routes), logique métier robuste (validation avant mutation, même pattern réutilisé pour commandes ET réservations), séparation nette entre espace public (vitrine, sans connexion) et espace de gestion interne (protégé), chatbot testable indépendamment de l'API WhatsApp grâce au découplage logique métier / transport, mots de passe hashés même en environnement de démo, identité visuelle différenciée et cohérente sur l'espace public (palette + typographie + micro-animations pensées comme un tout).
- Pour la soutenance, bon fil conducteur de démo : parcourir l'espace public comme un vrai visiteur (accueil → nos matériaux → réserver une visite → discuter avec le chatbot), puis basculer côté "Ascale" en se connectant sur `/connexion` pour montrer la gestion des réservations — illustre concrètement la séparation public/interne.
- Limites actuelles à assumer clairement (et à présenter comme roadmap, pas comme oubli) : pas de base de données persistante, pas de tests automatisés, authentification limitée à la page réservations (pas encore étendue à Produits/Clients/Commandes), compte WhatsApp Business pas encore activé, statut de commande simulé (pas de vrai suivi logistique), notification de réservation simulée (pas de vrai SMS/e-mail).
- Roadmap pour la suite du projet à mentionner en conclusion : activation de l'API WhatsApp Business avec Nasser, extension de l'authentification à toute la gestion interne, vraie base de données.
- Identifiants de démo pour la soutenance : espace de gestion → `nasser@ascale.ma` / `Marbre2026!` (page `/connexion`).
- Pour la démo en soutenance : page `/chatbot`, boutons de suggestions pré-remplis pour montrer les 3 scénarios clés (question produit, devis, suivi de commande) sans avoir à improviser une formulation. Pour les réservations : réserver un créneau depuis `/reservation` (public), puis se connecter pour l'annuler depuis `/admin/reservations` — bon enchaînement pour montrer le cycle complet public → interne.
