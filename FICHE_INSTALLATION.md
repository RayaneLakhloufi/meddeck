# Fiche d'installation — MedDeck v2 (essai terrain)

**Projet :** application de gestion des dispositifs médicaux — Service Biomédical (SEBM), CHU Mohammed VI
**Destinataire :** service informatique / responsable SEBM
**Type :** essai pilote sur réseau local, sans accès internet requis

---

## 1. Matériel nécessaire

| Élément | Détail |
|---|---|
| PC serveur | Un poste Windows allumé pendant les heures d'essai |
| Réseau | Le PC et les téléphones/tablettes sur le **même réseau** (Wi-Fi ou Ethernet du service) |
| IP fixe | **Recommandée** pour le PC serveur (à attribuer par l'informatique) afin que l'adresse d'accès ne change pas |
| Téléphones/tablettes | Navigateur récent (Chrome, Safari, Brave) — aucune application à installer |

> MedDeck ne nécessite **aucune connexion internet** ni serveur externe. Toutes les données restent sur le PC serveur, à l'intérieur du réseau du CHU.

---

## 2. Installation sur le PC serveur

1. Installer **Python 3.9+** depuis https://python.org (cocher « Add Python to PATH »)
2. Récupérer le dossier `meddeck` (clé USB ou `git clone https://github.com/RayaneLakhloufi/meddeck.git`)
3. Ouvrir un terminal dans le dossier et installer les dépendances :
   ```
   pip install -r requirements.txt
   ```

---

## 3. Ouvrir le port sur le pare-feu (une seule fois)

Dans **PowerShell en administrateur** :
```
New-NetFirewallRule -DisplayName "MedDeck" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

---

## 4. Démarrage

Double-cliquer sur **`lancer_meddeck.bat`**.
La fenêtre affiche les adresses d'accès :
- Sur ce PC : `http://localhost:5000`
- Depuis un téléphone/tablette : `http://<IP-du-PC>:5000`

Le serveur utilise **Waitress** (serveur stable, adapté à un usage continu).

### Première connexion
Au tout premier démarrage, un **compte administrateur** est créé avec un **PIN aléatoire affiché dans la fenêtre** (ligne `COMPTE ADMINISTRATEUR SEBM CREE`). **Noter ce PIN.**
Se connecter avec le nom `Administrateur SEBM`, puis créer les vrais comptes du personnel et changer/supprimer les comptes de démonstration.

---

## 5. Démarrage automatique au boot (optionnel)

Pour que MedDeck redémarre seul si le PC est redémarré :
1. Appuyer sur `Win + R`, taper `shell:startup`, valider
2. Y placer un **raccourci** vers `lancer_meddeck.bat`

Le serveur se relancera à chaque ouverture de session. (Pour le désactiver : supprimer le raccourci de ce dossier.)

---

## 6. Sauvegardes

- Une **sauvegarde automatique** (base + fichiers) est créée à chaque démarrage, dans `instance/backups/`.
- Les 30 dernières copies sont conservées (rotation automatique).
- En fin d'essai : **copier le dossier `instance/`** sur une clé USB pour conserver les données.

---

## 7. Données et confidentialité

- MedDeck enregistre : équipements, checklists, incidents, comptes du personnel (nom + PIN haché en SHA-256).
- **Aucune donnée patient** n'est traitée.
- Toutes les données restent **locales** sur le PC serveur du service.
- Accès protégé par authentification (rôle + nom + PIN), sessions expirables (30 min), journal d'audit.

---

## Contact

Rayane Lakhloufi — projet MedDeck v2 — https://github.com/RayaneLakhloufi/meddeck
