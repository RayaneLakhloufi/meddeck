# MedDeck v2 — CHU Mohammed VI

Application web de gestion des dispositifs médicaux du bloc opératoire pour le **Service de Biomédical (SEBM)** du CHU Mohammed VI (Maroc).

---

## Fonctionnalités

### Pour tout le personnel (IADE, IBODE, Chirurgien)
- **Checklists de vérification** des équipements avant intervention (anesthésie, bistouri, moniteur) avec calcul automatique du taux de conformité
- **Déclaration d'incidents** (gravité 1–5, impact patient, action immédiate) avec suivi en temps réel
- **Tableau de bord** : statistiques globales, activité récente, alertes de maintenance
- **Scan QR** des équipements pour accéder rapidement à leur fiche

### Pour le SEBM (administration)
- **Gestion du parc** : ajout, modification, archivage des équipements avec IPR, numéro de série, bloc, responsable
- **Calendrier de maintenance** : alertes pour les maintenances dépassées ou imminentes, enregistrement des interventions
- **Module Contrats & Paiements** : suivi des marchés de maintenance, interventions planifiées et dossiers de paiement (PV de réception, factures HT/TVA/TTC, rapports d'intervention, bordereaux d'envoi) avec upload de fichiers PDF/JPG
- **Rapports mensuels** : synthèse checklists / incidents / maintenances avec calcul MTBF/MTTR
- **Administration** : gestion des comptes, sessions actives, journal d'audit, sauvegarde / réinitialisation des données

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3 · Flask · SQLite (WAL mode) |
| Frontend | SPA HTML monofichier · JavaScript vanilla |
| Auth | PIN 4 chiffres · SHA-256 · Token 30 min · 3 facteurs (rôle + nom + PIN) |
| Fichiers | Upload multipart · stockage serveur · noms aléatoires |
| PWA | Service Worker · manifest.json · installable |

---

## Installation

### Prérequis
- Python 3.9+
- pip

### Étapes

```bash
git clone https://github.com/RayaneLakhloufi/meddeck.git
cd meddeck
pip install -r requirements.txt
python run.py
```

Ouvrez ensuite [http://localhost:5000](http://localhost:5000) dans votre navigateur.

**Sous Windows**, double-cliquez sur `lancer_meddeck.bat` pour démarrer automatiquement.

Le serveur démarre avec **Waitress** (serveur stable adapté à un usage continu) ; à défaut, il bascule sur le serveur de développement Flask.

> Pour un déploiement d'essai sur site (hôpital), voir **[FICHE_INSTALLATION.md](FICHE_INSTALLATION.md)**.

### Première connexion

Au premier démarrage, un compte **administrateur SEBM** est créé avec un **PIN aléatoire affiché une seule fois dans la console** (cherchez la ligne `COMPTE ADMINISTRATEUR SEBM CREE`). Notez-le, connectez-vous avec le nom `Administrateur SEBM`, puis changez le PIN depuis l'administration.

Pour imposer vos propres identifiants, définissez avant le premier lancement :
- `MEDDECK_SECRET` : clé de hachage des PIN (sinon générée automatiquement)
- `MEDDECK_ADMIN_PIN` : PIN admin à 4 chiffres (sinon aléatoire)

Des comptes de démonstration (IADE, IBODE, Chirurgien) sont aussi créés pour tester rapidement.

### Accès depuis un téléphone ou une tablette

L'interface est **responsive** et le **scan des QR codes** se fait directement depuis l'appareil mobile — pratique au bloc opératoire.

1. Le téléphone/tablette et le PC serveur doivent être sur le **même réseau Wi-Fi**.
2. Récupérer l'**adresse IP locale** du PC serveur (affichée au lancement de `lancer_meddeck.bat`, ou via `ipconfig` → ligne *Adresse IPv4*, ex. `192.168.1.11`).
3. Sur le mobile, ouvrir le navigateur à l'adresse **`http://<IP-du-PC>:5000`** (ex. `http://192.168.1.11:5000`).

> **Pare-feu Windows** : autoriser le port 5000 une seule fois, dans PowerShell **administrateur** :
> ```powershell
> New-NetFirewallRule -DisplayName "MedDeck" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
> ```

---


## Structure du projet

```
meddeck/
├── app.py                    # Backend Flask (API REST + auth + DB)
├── run.py                    # Point d'entrée
├── MedDeck_v2_Terrain.html   # Frontend SPA (interface complète)
├── lancer_meddeck.bat        # Script de lancement Windows
└── instance/                 # Créé automatiquement (non versionné)
    ├── meddeck.db            # Base de données SQLite
    ├── uploads/              # Fichiers uploadés (PV, factures...)
    └── backups/              # Sauvegardes automatiques
```

---

## Sécurité

- Authentification à 3 facteurs : rôle + nom (insensible accents/casse) + PIN hashé SHA-256
- Rate limiting : blocage IP après 5 tentatives échouées (5 min)
- Tokens de session expirables (30 min, renouvellement automatique)
- Upload sécurisé : noms de fichiers générés aléatoirement, extensions filtrées
- En-têtes de sécurité HTTP : `X-Frame-Options`, `X-Content-Type-Options`
- Journal d'audit complet de toutes les actions

---

## Sauvegarde

Une sauvegarde automatique de la base de données et des fichiers uploadés est créée à chaque démarrage (dans `instance/backups/`). Les 30 dernières copies sont conservées avec rotation automatique. Une sauvegarde préventive est également déclenchée avant toute réinitialisation.

---

## Licence

Projet interne — CHU Mohammed VI, Service de Biomédical (SEBM). Usage hospitalier.
