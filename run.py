"""Point d'entrée — MedDeck v2

HTTPS automatique si un certificat est présent dans instance/certs/
(nécessaire pour le scan caméra en direct sur téléphone/tablette).
Sinon, démarrage en HTTP classique.
"""
import os
from app import app, init_db

init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT = os.path.join(BASE_DIR, 'instance', 'certs', 'cert.pem')
KEY = os.path.join(BASE_DIR, 'instance', 'certs', 'key.pem')

if os.path.exists(CERT) and os.path.exists(KEY):
    print(' MedDeck demarre en HTTPS (scan camera en direct active)')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, ssl_context=(CERT, KEY))
else:
    print(' MedDeck demarre en HTTP (certificat absent — scan par photo uniquement)')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
