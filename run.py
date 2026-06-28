"""Point d'entrée — MedDeck v2

Démarre l'application :
 - en production avec Waitress (serveur stable, recommandé pour l'essai terrain) ;
 - sinon avec le serveur de développement Flask (repli automatique).

Si un certificat est présent dans instance/certs/, démarre en HTTPS via Flask
(Waitress ne gère pas le SSL).
"""
import os
from app import app, init_db, migrate_db, auto_backup

PORT = 5000

# Initialisation : base de données, migrations de schéma, sauvegarde du jour
init_db()
migrate_db()
auto_backup()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT = os.path.join(BASE_DIR, 'instance', 'certs', 'cert.pem')
KEY = os.path.join(BASE_DIR, 'instance', 'certs', 'key.pem')

if os.path.exists(CERT) and os.path.exists(KEY):
    print(f' MedDeck — HTTPS (Flask) sur le port {PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True, ssl_context=(CERT, KEY))
else:
    try:
        from waitress import serve
        print('=' * 54)
        print(f'  MedDeck v2 demarre (Waitress) — serveur stable')
        print(f'  Acces sur ce PC : http://localhost:{PORT}')
        print(f'  Acces reseau    : http://<IP-du-PC>:{PORT}')
        print('  Pour arreter : Ctrl+C')
        print('=' * 54)
        serve(app, host='0.0.0.0', port=PORT, threads=8)
    except ImportError:
        print(f' Waitress absent — serveur de developpement Flask sur le port {PORT}')
        print(' (Pour un essai stable : pip install waitress)')
        app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
