"""MedDeck v2 — Backend Flask | CHU Mohammed VI SEBM"""

import os, json, hashlib, secrets, sqlite3, logging, unicodedata, shutil
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g, send_from_directory

import sys
# Séparation des chemins pour fonctionner aussi en exécutable PyInstaller :
#  - RESOURCE_DIR : fichiers embarqués en lecture seule (HTML, static)
#  - DATA_DIR / BASE_DIR : données persistantes (base, sauvegardes, uploads) à côté de l'exe
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = sys._MEIPASS
    DATA_DIR     = os.path.dirname(sys.executable)
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR     = RESOURCE_DIR

BASE_DIR    = DATA_DIR
DB_PATH     = os.path.join(BASE_DIR, 'instance', 'meddeck.db')
LOG_PATH    = os.path.join(BASE_DIR, 'instance', 'meddeck.log')
UPLOAD_DIR  = os.path.join(BASE_DIR, 'instance', 'uploads')
BACKUP_DIR  = os.path.join(BASE_DIR, 'instance', 'backups')

def _load_secret():
    """Clé secrète pour le hachage des PIN.
    Priorité : variable d'environnement MEDDECK_SECRET, sinon fichier
    instance/secret.key (généré une seule fois et non versionné).
    Une nouvelle installation reçoit une clé unique et imprévisible ;
    une installation existante conserve la clé historique pour ne pas
    invalider les PIN déjà enregistrés."""
    env = os.environ.get('MEDDECK_SECRET')
    if env:
        return env
    key_path = os.path.join(BASE_DIR, 'instance', 'secret.key')
    if os.path.exists(key_path):
        with open(key_path, encoding='utf-8') as f:
            return f.read().strip()
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    value = 'meddeck_chusm_2026_secret' if os.path.exists(DB_PATH) else secrets.token_hex(32)
    with open(key_path, 'w', encoding='utf-8') as f:
        f.write(value)
    return value

SECRET      = _load_secret()
TOKEN_TTL   = 30 * 60
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png'}
MAX_UPLOAD  = 10 * 1024 * 1024  # 10 MB

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])
log = logging.getLogger('meddeck')

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET

@app.after_request
def add_headers(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Token'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['X-Content-Type-Options']       = 'nosniff'
    r.headers['X-Frame-Options']              = 'DENY'
    return r

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, role TEXT NOT NULL,
        pin_hash TEXT NOT NULL, room TEXT,
        active INTEGER DEFAULT 1,
        created TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        expires TEXT NOT NULL, ip TEXT,
        created TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS checklists (
        id TEXT PRIMARY KEY, device TEXT NOT NULL,
        device_label TEXT NOT NULL, room TEXT NOT NULL,
        signed_by TEXT NOT NULL, user_id INTEGER,
        total INTEGER NOT NULL, ok_count INTEGER NOT NULL,
        nok_count INTEGER NOT NULL, notes TEXT DEFAULT '[]',
        created TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY, device TEXT NOT NULL,
        room TEXT NOT NULL, type TEXT NOT NULL,
        severity INTEGER NOT NULL, impact TEXT NOT NULL,
        description TEXT NOT NULL, action TEXT DEFAULT '',
        reported_by TEXT NOT NULL, user_id INTEGER,
        status TEXT DEFAULT 'open',
        created TEXT DEFAULT (datetime('now')),
        updated TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, action TEXT NOT NULL,
        detail TEXT, ip TEXT,
        ts TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS login_attempts (
        ip TEXT PRIMARY KEY, count INTEGER DEFAULT 0,
        last TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS equipment (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        model TEXT NOT NULL,
        category TEXT NOT NULL,
        icon TEXT DEFAULT '🔬',
        qty INTEGER DEFAULT 1,
        ipr INTEGER DEFAULT 0,
        ipr_level TEXT DEFAULT 'low',
        last_maint TEXT,
        next_maint TEXT,
        responsible TEXT,
        serial TEXT,
        block TEXT,
        active INTEGER DEFAULT 1,
        created TEXT DEFAULT (datetime('now')),
        updated TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS maintenance_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id TEXT NOT NULL,
        type TEXT NOT NULL,
        performed_by TEXT NOT NULL,
        user_id INTEGER,
        notes TEXT DEFAULT '',
        date TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS contracts (
        id TEXT PRIMARY KEY,
        contract_number TEXT NOT NULL,
        provider TEXT NOT NULL,
        object TEXT DEFAULT '',
        equipment_ids TEXT DEFAULT '[]',
        start_date TEXT,
        end_date TEXT,
        periodicity TEXT DEFAULT 'trimestrielle',
        total_amount REAL DEFAULT 0,
        status TEXT DEFAULT 'active',
        notes TEXT DEFAULT '',
        created TEXT DEFAULT (datetime('now')),
        updated TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS contract_interventions (
        id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        period_label TEXT DEFAULT '',
        planned_date TEXT,
        actual_date TEXT,
        status TEXT DEFAULT 'planned',
        observations TEXT DEFAULT '',
        created TEXT DEFAULT (datetime('now')),
        updated TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS payment_files (
        id TEXT PRIMARY KEY,
        intervention_id TEXT NOT NULL,
        pv_number TEXT DEFAULT '', pv_date TEXT, pv_file TEXT,
        invoice_number TEXT DEFAULT '', invoice_date TEXT,
        amount_ht REAL DEFAULT 0, amount_tva REAL DEFAULT 0, amount_ttc REAL DEFAULT 0,
        invoice_file TEXT,
        report_number TEXT DEFAULT '', report_file TEXT,
        user_training INTEGER DEFAULT 0, user_training_file TEXT,
        tech_training INTEGER DEFAULT 0, tech_training_file TEXT,
        bordereau_number TEXT DEFAULT '', bordereau_date TEXT, bordereau_file TEXT,
        status TEXT DEFAULT 'preparation',
        created TEXT DEFAULT (datetime('now')),
        updated TEXT DEFAULT (datetime('now'))
    );
    """)
    cur = db.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        seed_default_users(db)
    cur2 = db.execute('SELECT COUNT(*) FROM equipment')
    if cur2.fetchone()[0] == 0:
        equip_defaults = [
            ('drager',  'DRÄGER Perseus A500',   'Station d\'anesthésie',     'anesthesie', '🫁', 25, 108, 'high',   '2026-03-15','2026-06-15','Service Biomédical','DRG-A500-xxx','A'),
            ('atlan',   'DRÄGER Atlan A350',      'Station d\'anesthésie',     'anesthesie', '🫁', 31, 63,  'medium', '2026-03-15','2026-06-15','Service Biomédical','DRG-A350-xxx','B'),
            ('erbe',    'ERBE VIO 300S',           'Bistouri électrique',       'bistouri',   '⚡', 18, 81,  'medium', '2026-03-20','2026-06-20','Service Biomédical','ERB-V300-xxx','A,B'),
            ('erbe3',   'ERBE VIO 3',             'Bistouri électrique',       'bistouri',   '⚡', 6,  45,  'low',    '2026-03-20','2026-06-20','Service Biomédical','ERB-V3-xxx',  'C'),
            ('philips', 'PHILIPS EFFECIA CM150',  'Moniteur multiparamétrique','moniteur',   '💓',258, 126, 'high',   '2026-04-10','2026-07-10','Service Biomédical','PHI-CM150-xxx','A,B,C'),
            ('revo',    'REVO-I MSR-5100',        'Robot chirurgical',         'autre',      '🤖', 2,  0,   'low',    '2026-04-01','2026-07-01','Service Biomédical','REV-5100-xxx', 'B'),
            ('maquet',  'MAQUET SERVO U',         'Respirateur de réanimation','autre',      '🌬️',57,  0,   'low',    '2026-02-28','2026-05-28','Service Biomédical','MAQ-SERVU-xxx','Réa'),
            ('nihon',   'NIHON KOHDEN TEC-5621',  'Défibrillateur',            'autre',      '⚡', 65, 0,   'low',    '2026-03-01','2026-06-01','Service Biomédical','NIH-5621-xxx', 'A,B,C'),
        ]
        for row in equip_defaults:
            db.execute('INSERT INTO equipment(id,name,model,category,icon,qty,ipr,ipr_level,last_maint,next_maint,responsible,serial,block) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', row)
        log.info('Equipements par defaut crees')
    db.commit(); db.close()

def seed_default_users(db):
    """Crée les comptes par défaut.
    Le PIN administrateur SEBM est aléatoire (ou défini via MEDDECK_ADMIN_PIN)
    et affiché une seule fois dans la console au démarrage : aucun PIN
    administrateur n'est codé en dur dans le code source."""
    admin_pin = os.environ.get('MEDDECK_ADMIN_PIN', '')
    if not (admin_pin.isdigit() and len(admin_pin) == 4):
        admin_pin = f"{secrets.randbelow(10000):04d}"
    db.execute('INSERT INTO users (name,role,pin_hash,room) VALUES (?,?,?,?)',
               ('Administrateur SEBM', 'sebm', hash_pin(admin_pin, 'sebm'), 'SEBM'))
    banner = (
        '\n' + '=' * 52 + '\n'
        '  COMPTE ADMINISTRATEUR SEBM CREE\n'
        '  Nom : Administrateur SEBM     Role : sebm\n'
        f'  PIN : {admin_pin}   (notez-le, changez-le apres connexion)\n'
        + '=' * 52 + '\n'
    )
    log.info(banner)
    # Affichage console (fenetre de l'exe) pour que l'utilisateur voie le PIN
    try: print(banner, flush=True)
    except Exception: pass
    # Fichier texte lisible a cote de l'application (utile en version .exe)
    try:
        with open(os.path.join(BASE_DIR, 'IDENTIFIANTS_ADMIN.txt'), 'w', encoding='utf-8-sig') as f:
            f.write(
                "MedDeck - compte administrateur\n\n"
                "Nom d'utilisateur : Administrateur SEBM\n"
                "Role              : SEBM (administrateur)\n"
                f"Code PIN          : {admin_pin}\n\n"
                "Connectez-vous avec ces identifiants, puis changez le PIN\n"
                "depuis l'administration. Supprimez ce fichier ensuite.\n"
            )
    except Exception: pass
    demo = [
        ('Utilisateur IADE',       'iade',       '1234', 'Salle A1'),
        ('Utilisateur IBODE',      'ibode',      '1234', 'Salle B1'),
        ('Utilisateur Chirurgien', 'chirurgien', '5678', 'Salle C1'),
    ]
    for name, role, pin, room in demo:
        db.execute('INSERT INTO users (name,role,pin_hash,room) VALUES (?,?,?,?)',
                   (name, role, hash_pin(pin, role), room))
    log.info('Comptes de demonstration crees')

def hash_pin(pin, role):
    data = f"{pin}:{role}:{SECRET}".encode()
    return hashlib.sha256(data).hexdigest()

def sanitize(s, maxlen=500):
    if not isinstance(s, str): return ''
    return s.replace('<','&lt;').replace('>','&gt;').strip()[:maxlen]

def normalize_name(s):
    """Compare names ignoring accents, case, and extra whitespace."""
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii')
    return ' '.join(s.lower().split())

def backup_now():
    """Sauvegarde online de la DB + archive zip des uploads. Rotation à 30 copies."""
    ts = datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')
    dst_db_path = os.path.join(BACKUP_DIR, f'meddeck_{ts}.db')
    # SQLite online backup (safe même si la DB est ouverte)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dst_db_path)
    src.backup(dst)
    dst.close(); src.close()
    # Archive uploads si non vide
    if os.path.exists(UPLOAD_DIR) and os.listdir(UPLOAD_DIR):
        shutil.make_archive(os.path.join(BACKUP_DIR, f'uploads_{ts}'), 'zip', UPLOAD_DIR)
    # Rotation : garder les 30 dernières sauvegardes DB
    db_files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith('meddeck_') and f.endswith('.db'))
    for old in db_files[:-30]:
        os.remove(os.path.join(BACKUP_DIR, old))
    zip_files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith('uploads_') and f.endswith('.zip'))
    for old in zip_files[:-30]:
        os.remove(os.path.join(BACKUP_DIR, old))
    return dst_db_path

def auto_backup():
    """Lance une sauvegarde automatique au démarrage si aucune n'existe pour aujourd'hui."""
    today = datetime.utcnow().strftime('%Y-%m-%d')
    if not any(f.startswith(f'meddeck_{today}') for f in os.listdir(BACKUP_DIR)):
        try:
            backup_now()
            log.info('Sauvegarde automatique du jour effectuée')
        except Exception as e:
            log.error(f'Erreur sauvegarde automatique: {e}')

def migrate_db():
    """Migrations SQL incrémentales sans casser les données existantes."""
    db = sqlite3.connect(DB_PATH)
    # Ajout de equipment_id (FK souple) dans incidents pour remplacer le LIKE fragile
    cols = [r[1] for r in db.execute("PRAGMA table_info(incidents)").fetchall()]
    if 'equipment_id' not in cols:
        db.execute("ALTER TABLE incidents ADD COLUMN equipment_id TEXT")
        db.commit()
        log.info('Migration: equipment_id ajouté à la table incidents')
    db.close()

BRUTE_MAX = 5; BRUTE_WIN = 300

def check_brute(ip):
    db = get_db()
    row = db.execute('SELECT count, last FROM login_attempts WHERE ip=?', (ip,)).fetchone()
    if row:
        last = datetime.fromisoformat(row['last'])
        if (datetime.utcnow() - last).seconds > BRUTE_WIN:
            db.execute('DELETE FROM login_attempts WHERE ip=?',(ip,)); db.commit(); return False
        if row['count'] >= BRUTE_MAX: return True
    return False

def record_attempt(ip, ok):
    db = get_db()
    if ok: db.execute('DELETE FROM login_attempts WHERE ip=?',(ip,))
    else:  db.execute("INSERT INTO login_attempts(ip,count,last) VALUES(?,1,datetime('now')) ON CONFLICT(ip) DO UPDATE SET count=count+1,last=datetime('now')",(ip,))
    db.commit()

def create_token(uid, ip):
    token = secrets.token_hex(32)
    exp   = (datetime.utcnow()+timedelta(seconds=TOKEN_TTL)).isoformat()
    get_db().execute('INSERT INTO sessions(token,user_id,expires,ip) VALUES(?,?,?,?)',(token,uid,exp,ip))
    get_db().commit(); return token

def get_user():
    token = request.headers.get('X-Token','')
    if not token: return None
    db  = get_db()
    row = db.execute("SELECT u.*,s.token,s.expires FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1",(token,)).fetchone()
    if not row: return None
    if datetime.fromisoformat(row['expires']) < datetime.utcnow():
        db.execute('DELETE FROM sessions WHERE token=?',(token,)); db.commit(); return None
    new_exp = (datetime.utcnow()+timedelta(seconds=TOKEN_TTL)).isoformat()
    db.execute('UPDATE sessions SET expires=? WHERE token=?',(new_exp,token)); db.commit()
    return dict(row)

def require_auth(roles=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            u = get_user()
            if not u: return jsonify({'error':'Non authentifie'}), 401
            if roles and u['role'] not in roles: return jsonify({'error':'Acces refuse'}), 403
            g.u = u; return f(*args, **kwargs)
        return wrapper
    return deco

def audit(action, detail=''):
    try:
        u = getattr(g,'u',None)
        get_db().execute('INSERT INTO audit_log(user_id,action,detail,ip) VALUES(?,?,?,?)',
            (u['id'] if u else None, action, detail, request.remote_addr))
        get_db().commit()
        log.info(f"[{u['name'] if u else 'anon'}] {action} | {detail}")
    except: pass

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def login():
    ip = request.remote_addr
    if check_brute(ip):
        return jsonify({'error':'Trop de tentatives. Attendez 5 minutes.'}), 429
    d    = request.get_json(silent=True) or {}
    role = d.get('role',''); pin = str(d.get('pin','')); name = sanitize(d.get('name','')); room = sanitize(d.get('room',''))
    if not all([role,pin,name,room]): return jsonify({'error':'Champs manquants'}), 400
    ph   = hash_pin(pin, role)
    user = get_db().execute('SELECT * FROM users WHERE role=? AND pin_hash=? AND active=1',(role,ph)).fetchone()
    # Le PIN seul ne suffit pas : le nom saisi doit correspondre au compte (anti-usurpation)
    if not user or normalize_name(user['name']) != normalize_name(name):
        record_attempt(ip, False)
        audit('LOGIN_FAIL', f"role={role} name={name}")
        return jsonify({'error':'Nom ou code PIN incorrect'}), 401
    record_attempt(ip, True)
    token = create_token(user['id'], ip)
    g.u   = dict(user)
    audit('LOGIN', f"room={room}")
    return jsonify({'token':token,'user':{'id':user['id'],'name':user['name'],'role':user['role'],'room':room}})

@app.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    get_db().execute('DELETE FROM sessions WHERE token=?',(request.headers.get('X-Token',''),))
    get_db().commit(); audit('LOGOUT')
    return jsonify({'ok':True})

@app.route('/api/auth/me', methods=['GET'])
@require_auth()
def me():
    return jsonify({'user':{k:g.u[k] for k in ('id','name','role')}})

# ── CHECKLISTS ────────────────────────────────────────────────────────────────
@app.route('/api/checklists', methods=['GET'])
@require_auth()
def get_checklists():
    dev   = request.args.get('device')
    limit = min(int(request.args.get('limit',50)),200)
    q = 'SELECT * FROM checklists'; p = []
    if dev: q += ' WHERE device=?'; p.append(dev)
    q += ' ORDER BY created DESC LIMIT ?'; p.append(limit)
    return jsonify([dict(r) for r in get_db().execute(q,p).fetchall()])

@app.route('/api/checklists', methods=['POST'])
@require_auth(['iade','ibode','sebm'])
def create_checklist():
    d = request.get_json(silent=True) or {}
    for k in ['device','device_label','room','total','ok_count','nok_count']:
        if k not in d: return jsonify({'error':f'Champ manquant: {k}'}), 400
    cid = f"CL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"
    get_db().execute('INSERT INTO checklists(id,device,device_label,room,signed_by,user_id,total,ok_count,nok_count,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (cid,sanitize(d['device']),sanitize(d['device_label']),sanitize(d['room']),sanitize(d.get('signed_by',g.u['name'])),g.u['id'],int(d['total']),int(d['ok_count']),int(d['nok_count']),json.dumps(d.get('notes',[]))))
    get_db().commit()
    audit('CHECKLIST', f"id={cid} device={d['device']} nok={d['nok_count']}")
    return jsonify({'id':cid,'ok':True}), 201

@app.route('/api/checklists/stats', methods=['GET'])
@require_auth()
def cl_stats():
    db = get_db(); stats = {}
    for dev in ['anesthesie','bistouri','moniteur']:
        rows = db.execute('SELECT ok_count,total FROM checklists WHERE device=?',(dev,)).fetchall()
        if rows:
            perfect = sum(1 for r in rows if r['ok_count']==r['total'])
            stats[dev] = {'count':len(rows),'compliance':round(perfect/len(rows)*100)}
        else: stats[dev] = {'count':0,'compliance':0}
    return jsonify(stats)

# ── INCIDENTS ─────────────────────────────────────────────────────────────────
@app.route('/api/incidents', methods=['GET'])
@require_auth()
def get_incidents():
    status = request.args.get('status')
    limit  = min(int(request.args.get('limit',100)),500)
    q = 'SELECT * FROM incidents'; p = []
    if status: q += ' WHERE status=?'; p.append(status)
    q += ' ORDER BY created DESC LIMIT ?'; p.append(limit)
    return jsonify([dict(r) for r in get_db().execute(q,p).fetchall()])

@app.route('/api/incidents', methods=['POST'])
@require_auth()
def create_incident():
    d = request.get_json(silent=True) or {}
    for k in ['device','room','type','severity','impact','description']:
        if k not in d: return jsonify({'error':f'Champ manquant: {k}'}), 400
    sev = int(d['severity'])
    if not 1 <= sev <= 5: return jsonify({'error':'Gravite 1-5'}), 400
    db  = get_db()
    cnt = db.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]
    iid = f"INC-{(cnt+1):03d}"
    eid = sanitize(d.get('equipment_id', '')) or None
    db.execute('INSERT INTO incidents(id,device,equipment_id,room,type,severity,impact,description,action,reported_by,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (iid,sanitize(d['device']),eid,sanitize(d['room']),sanitize(d['type']),sev,sanitize(d['impact']),sanitize(d['description']),sanitize(d.get('action','')),g.u['name'],g.u['id']))
    db.commit()
    audit('INCIDENT', f"id={iid} sev={sev}")
    return jsonify({'id':iid,'ok':True}), 201

@app.route('/api/incidents/<iid>', methods=['PUT'])
@require_auth()
def update_incident(iid):
    d   = request.get_json(silent=True) or {}
    st  = d.get('status'); act = sanitize(d.get('action',''))
    if st and st not in ('open','progress','closed'): return jsonify({'error':'Statut invalide'}), 400
    db  = get_db()
    inc = db.execute('SELECT * FROM incidents WHERE id=?',(iid,)).fetchone()
    if not inc: return jsonify({'error':'Introuvable'}), 404
    if g.u['role'] != 'sebm' and inc['user_id'] != g.u['id']:
        return jsonify({'error':'Non autorise'}), 403
    ups, ps = [], []
    if st:  ups.append('status=?'); ps.append(st)
    if act: ups.append('action=?'); ps.append(act)
    if ups:
        ups.append("updated=datetime('now')"); ps.append(iid)
        db.execute(f"UPDATE incidents SET {','.join(ups)} WHERE id=?", ps); db.commit()
    audit('INCIDENT_UPDATE', f"id={iid} status={st}")
    return jsonify({'ok':True})

@app.route('/api/incidents/stats', methods=['GET'])
@require_auth()
def inc_stats():
    db = get_db()
    return jsonify({
        'total':   db.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],
        'open':    db.execute("SELECT COUNT(*) FROM incidents WHERE status='open'").fetchone()[0],
        'progress':db.execute("SELECT COUNT(*) FROM incidents WHERE status='progress'").fetchone()[0],
        'closed':  db.execute("SELECT COUNT(*) FROM incidents WHERE status='closed'").fetchone()[0],
        'by_sev':  {str(i):db.execute('SELECT COUNT(*) FROM incidents WHERE severity=?',(i,)).fetchone()[0] for i in range(1,6)}
    })

# ── USERS (SEBM only) ─────────────────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@require_auth(['sebm'])
def get_users():
    return jsonify([dict(r) for r in get_db().execute('SELECT id,name,role,room,active,created FROM users').fetchall()])

@app.route('/api/users', methods=['POST'])
@require_auth(['sebm'])
def create_user():
    d = request.get_json(silent=True) or {}
    if not all(k in d for k in ['name','role','pin','room']): return jsonify({'error':'Champs manquants'}), 400
    if d['role'] not in ('iade','ibode','chirurgien','sebm'): return jsonify({'error':'Role invalide'}), 400
    pin = str(d['pin'])
    if not pin.isdigit() or len(pin)!=4: return jsonify({'error':'PIN 4 chiffres requis'}), 400
    get_db().execute('INSERT INTO users(name,role,pin_hash,room) VALUES(?,?,?,?)',
        (sanitize(d['name']),d['role'],hash_pin(pin,d['role']),sanitize(d['room'])))
    get_db().commit(); audit('USER_CREATED',f"name={d['name']} role={d['role']}")
    return jsonify({'ok':True}), 201

@app.route('/api/users/<int:uid>/pin', methods=['PUT'])
@require_auth(['sebm'])
def change_pin(uid):
    d   = request.get_json(silent=True) or {}
    pin = str(d.get('pin',''))
    if not pin.isdigit() or len(pin)!=4: return jsonify({'error':'PIN invalide'}), 400
    db  = get_db()
    u   = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not u: return jsonify({'error':'Introuvable'}), 404
    db.execute('UPDATE users SET pin_hash=? WHERE id=?',(hash_pin(pin,u['role']),uid))
    db.execute('DELETE FROM sessions WHERE user_id=?',(uid,)); db.commit()
    audit('PIN_CHANGED',f"uid={uid}")
    return jsonify({'ok':True})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@require_auth(['sebm'])
def delete_user(uid):
    if uid == g.u['id']:
        return jsonify({'error':'Impossible de se supprimer soi-même'}), 400
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not u:
        return jsonify({'error':'Introuvable'}), 404
    # Empêcher la suppression du dernier SEBM actif
    if u['role'] == 'sebm':
        remaining = db.execute("SELECT COUNT(*) FROM users WHERE role='sebm' AND active=1 AND id!=?", (uid,)).fetchone()[0]
        if remaining == 0:
            return jsonify({'error':'Impossible de supprimer le dernier compte SEBM actif'}), 400
    db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
    db.execute('DELETE FROM users WHERE id=?', (uid,))
    db.commit()
    audit('USER_DELETED', f"uid={uid} name={u['name']}")
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>/toggle', methods=['PUT'])
@require_auth(['sebm'])
def toggle_user(uid):
    if uid==g.u['id']: return jsonify({'error':'Impossible de se desactiver'}), 400
    db = get_db()
    db.execute('UPDATE users SET active=NOT active WHERE id=?',(uid,))
    db.execute('DELETE FROM sessions WHERE user_id=?',(uid,)); db.commit()
    audit('USER_TOGGLED',f"uid={uid}")
    return jsonify({'ok':True})

# ── EQUIPMENT CRUD ────────────────────────────────────────────────────────────
@app.route('/api/equipment', methods=['GET'])
@require_auth()
def get_equipment():
    rows = get_db().execute('SELECT * FROM equipment WHERE active=1 ORDER BY name').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/equipment', methods=['POST'])
@require_auth(['sebm'])
def create_equipment():
    d = request.get_json(silent=True) or {}
    for k in ['name','model','category']:
        if not d.get(k): return jsonify({'error':f'Champ manquant: {k}'}), 400
    eid = sanitize(d.get('id','')) or d['name'].lower().replace(' ','_')[:20]
    if get_db().execute('SELECT id FROM equipment WHERE id=?',(eid,)).fetchone():
        eid = eid + '_' + secrets.token_hex(2)
    get_db().execute('''INSERT INTO equipment(id,name,model,category,icon,qty,ipr,ipr_level,last_maint,next_maint,responsible,serial,block)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        eid, sanitize(d['name']), sanitize(d['model']), sanitize(d['category']),
        sanitize(d.get('icon','🔬')), int(d.get('qty',1)), int(d.get('ipr',0)),
        sanitize(d.get('ipr_level','low')), d.get('last_maint'), d.get('next_maint'),
        sanitize(d.get('responsible','')), sanitize(d.get('serial','')), sanitize(d.get('block',''))
    ))
    get_db().commit()
    audit('EQUIPMENT_CREATED', f"id={eid} name={d['name']}")
    return jsonify({'id':eid,'ok':True}), 201

@app.route('/api/equipment/<eid>', methods=['PUT'])
@require_auth(['sebm'])
def update_equipment(eid):
    d   = request.get_json(silent=True) or {}
    db  = get_db()
    eq  = db.execute('SELECT * FROM equipment WHERE id=?',(eid,)).fetchone()
    if not eq: return jsonify({'error':'Introuvable'}), 404
    fields = ['name','model','category','icon','qty','ipr','ipr_level','last_maint','next_maint','responsible','serial','block']
    ups, ps = [], []
    for f in fields:
        if f in d:
            ups.append(f'{f}=?')
            ps.append(int(d[f]) if f in ('qty','ipr') else sanitize(str(d[f])) if f not in ('last_maint','next_maint') else d[f])
    if ups:
        ups.append("updated=datetime('now')")
        ps.append(eid)
        db.execute(f"UPDATE equipment SET {','.join(ups)} WHERE id=?", ps)
        db.commit()
    audit('EQUIPMENT_UPDATED', f"id={eid}")
    return jsonify({'ok':True})

@app.route('/api/equipment/<eid>', methods=['DELETE'])
@require_auth(['sebm'])
def delete_equipment(eid):
    db = get_db()
    if not db.execute('SELECT id FROM equipment WHERE id=?',(eid,)).fetchone():
        return jsonify({'error':'Introuvable'}), 404
    db.execute('UPDATE equipment SET active=0 WHERE id=?',(eid,))
    db.commit()
    audit('EQUIPMENT_DELETED', f"id={eid}")
    return jsonify({'ok':True})

@app.route('/api/equipment/<eid>/maintenance', methods=['POST'])
@require_auth(['sebm'])
def log_maintenance(eid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    if not db.execute('SELECT id FROM equipment WHERE id=?',(eid,)).fetchone():
        return jsonify({'error':'Introuvable'}), 404
    mtype = sanitize(d.get('type','preventive'))
    notes = sanitize(d.get('notes',''))
    date  = d.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    next_d= d.get('next_maint')
    db.execute('INSERT INTO maintenance_log(equipment_id,type,performed_by,user_id,notes,date) VALUES(?,?,?,?,?,?)',
        (eid, mtype, g.u['name'], g.u['id'], notes, date))
    if next_d:
        db.execute("UPDATE equipment SET last_maint=?,next_maint=?,updated=datetime('now') WHERE id=?", (date,next_d,eid))
    db.commit()
    audit('MAINTENANCE_DONE', f"id={eid} type={mtype}")
    return jsonify({'ok':True}), 201

@app.route('/api/equipment/<eid>/history', methods=['GET'])
@require_auth()
def equipment_history(eid):
    db  = get_db()
    cls = db.execute('SELECT * FROM checklists WHERE device=? ORDER BY created DESC LIMIT 20',(eid,)).fetchall()
    # Nouveaux incidents liés par FK, anciens par correspondance de nom (rétro-compatibilité)
    eq  = db.execute('SELECT name FROM equipment WHERE id=?',(eid,)).fetchone()
    name_like = f"%{eq['name'].split()[0]}%" if eq else f"%{eid}%"
    inc = db.execute(
        'SELECT * FROM incidents WHERE equipment_id=? OR (equipment_id IS NULL AND device LIKE ?) ORDER BY created DESC LIMIT 20',
        (eid, name_like)
    ).fetchall()
    mnt = db.execute('SELECT * FROM maintenance_log WHERE equipment_id=? ORDER BY date DESC LIMIT 20',(eid,)).fetchall()
    return jsonify({'checklists':[dict(r) for r in cls],'incidents':[dict(r) for r in inc],'maintenance':[dict(r) for r in mnt]})

# ── FILE UPLOAD (PV, factures, bordereaux...) ──────────────────────────────────
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXT

@app.route('/api/upload', methods=['POST'])
@require_auth(['sebm'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'Type de fichier non autorisé (PDF, JPG, PNG uniquement)'}), 400
    if request.content_length and request.content_length > MAX_UPLOAD:
        return jsonify({'error': 'Fichier trop volumineux (max 10 Mo)'}), 400
    ext = f.filename.rsplit('.', 1)[1].lower()
    fname = f"{secrets.token_hex(8)}.{ext}"
    f.save(os.path.join(UPLOAD_DIR, fname))
    audit('FILE_UPLOAD', f"name={fname} orig={sanitize(f.filename,200)}")
    return jsonify({'ok': True, 'path': f'uploads/{fname}'}), 201

@app.route('/uploads/<fname>')
@require_auth(['sebm'])
def get_upload(fname):
    return send_from_directory(UPLOAD_DIR, fname)

# ── CONTRACTS (SEBM only) ────────────────────────────────────────────────────
@app.route('/api/contracts', methods=['GET'])
@require_auth(['sebm'])
def get_contracts():
    rows = get_db().execute('SELECT * FROM contracts ORDER BY end_date').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/contracts', methods=['POST'])
@require_auth(['sebm'])
def create_contract():
    d = request.get_json(silent=True) or {}
    for k in ['contract_number', 'provider', 'start_date', 'end_date']:
        if not d.get(k): return jsonify({'error': f'Champ manquant: {k}'}), 400
    cid = f"CTR-{secrets.token_hex(4).upper()}"
    get_db().execute('''INSERT INTO contracts(id,contract_number,provider,object,equipment_ids,start_date,end_date,periodicity,total_amount,status,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (
        cid, sanitize(d['contract_number']), sanitize(d['provider']), sanitize(d.get('object', '')),
        json.dumps(d.get('equipment_ids', [])), d['start_date'], d['end_date'],
        sanitize(d.get('periodicity', 'trimestrielle')), float(d.get('total_amount', 0) or 0),
        sanitize(d.get('status', 'active')), sanitize(d.get('notes', ''), 2000)
    ))
    get_db().commit()
    audit('CONTRACT_CREATED', f"id={cid} provider={d['provider']}")
    return jsonify({'id': cid, 'ok': True}), 201

@app.route('/api/contracts/<cid>', methods=['PUT'])
@require_auth(['sebm'])
def update_contract(cid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    if not db.execute('SELECT id FROM contracts WHERE id=?', (cid,)).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    str_fields = ['contract_number', 'provider', 'object', 'start_date', 'end_date', 'periodicity', 'status', 'notes']
    ups, ps = [], []
    for f in str_fields:
        if f in d:
            ups.append(f'{f}=?')
            ps.append(sanitize(str(d[f]), 2000) if f in ('object', 'notes') else sanitize(str(d[f])))
    if 'total_amount' in d:
        ups.append('total_amount=?'); ps.append(float(d['total_amount'] or 0))
    if 'equipment_ids' in d:
        ups.append('equipment_ids=?'); ps.append(json.dumps(d['equipment_ids']))
    if ups:
        ups.append("updated=datetime('now')"); ps.append(cid)
        db.execute(f"UPDATE contracts SET {','.join(ups)} WHERE id=?", ps)
        db.commit()
    audit('CONTRACT_UPDATED', f"id={cid}")
    return jsonify({'ok': True})

@app.route('/api/contracts/<cid>', methods=['DELETE'])
@require_auth(['sebm'])
def delete_contract(cid):
    db = get_db()
    if not db.execute('SELECT id FROM contracts WHERE id=?', (cid,)).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    db.execute("UPDATE contracts SET status='cancelled', updated=datetime('now') WHERE id=?", (cid,))
    db.commit()
    audit('CONTRACT_CANCELLED', f"id={cid}")
    return jsonify({'ok': True})

# ── INTERVENTIONS PLANIFIÉES ─────────────────────────────────────────────────
@app.route('/api/contracts/<cid>/interventions', methods=['GET'])
@require_auth(['sebm'])
def get_interventions(cid):
    rows = get_db().execute('SELECT * FROM contract_interventions WHERE contract_id=? ORDER BY planned_date', (cid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/contracts/<cid>/interventions', methods=['POST'])
@require_auth(['sebm'])
def create_intervention(cid):
    d = request.get_json(silent=True) or {}
    if not d.get('planned_date'): return jsonify({'error': 'Date prévue requise'}), 400
    db = get_db()
    if not db.execute('SELECT id FROM contracts WHERE id=?', (cid,)).fetchone():
        return jsonify({'error': 'Contrat introuvable'}), 404
    iid = f"INT-{secrets.token_hex(4).upper()}"
    db.execute('''INSERT INTO contract_interventions(id,contract_id,period_label,planned_date,actual_date,status,observations)
        VALUES(?,?,?,?,?,?,?)''', (
        iid, cid, sanitize(d.get('period_label', '')), d['planned_date'], d.get('actual_date') or None,
        sanitize(d.get('status', 'planned')), sanitize(d.get('observations', ''), 2000)
    ))
    db.commit()
    audit('INTERVENTION_CREATED', f"id={iid} contract={cid}")
    return jsonify({'id': iid, 'ok': True}), 201

@app.route('/api/contracts/<cid>/interventions/<iid>', methods=['PUT'])
@require_auth(['sebm'])
def update_intervention(cid, iid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    if not db.execute('SELECT id FROM contract_interventions WHERE id=? AND contract_id=?', (iid, cid)).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    str_fields = ['period_label', 'status', 'observations']
    date_fields = ['planned_date', 'actual_date']
    ups, ps = [], []
    for f in str_fields:
        if f in d:
            ups.append(f'{f}=?'); ps.append(sanitize(str(d[f]), 2000) if f == 'observations' else sanitize(str(d[f])))
    for f in date_fields:
        if f in d:
            ups.append(f'{f}=?'); ps.append(d[f] or None)
    if ups:
        ups.append("updated=datetime('now')"); ps.append(iid)
        db.execute(f"UPDATE contract_interventions SET {','.join(ups)} WHERE id=?", ps)
        db.commit()
    audit('INTERVENTION_UPDATED', f"id={iid}")
    return jsonify({'ok': True})

# ── DOSSIERS DE PAIEMENT ──────────────────────────────────────────────────────
@app.route('/api/interventions/<iid>/payment-file', methods=['GET'])
@require_auth(['sebm'])
def get_payment_file(iid):
    row = get_db().execute('SELECT * FROM payment_files WHERE intervention_id=?', (iid,)).fetchone()
    return jsonify(dict(row) if row else None)

@app.route('/api/interventions/<iid>/payment-file', methods=['POST'])
@require_auth(['sebm'])
def create_payment_file(iid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    if not db.execute('SELECT id FROM contract_interventions WHERE id=?', (iid,)).fetchone():
        return jsonify({'error': 'Intervention introuvable'}), 404
    if db.execute('SELECT id FROM payment_files WHERE intervention_id=?', (iid,)).fetchone():
        return jsonify({'error': 'Un dossier existe déjà pour cette intervention'}), 400
    pid = f"PAY-{secrets.token_hex(4).upper()}"
    db.execute('''INSERT INTO payment_files(id,intervention_id,pv_number,pv_date,pv_file,invoice_number,invoice_date,invoice_file,
        amount_ht,amount_tva,amount_ttc,report_number,report_file,user_training,user_training_file,tech_training,tech_training_file,
        bordereau_number,bordereau_date,bordereau_file,status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        pid, iid, sanitize(d.get('pv_number', '')), d.get('pv_date') or None, d.get('pv_file'),
        sanitize(d.get('invoice_number', '')), d.get('invoice_date') or None, d.get('invoice_file'),
        float(d.get('amount_ht', 0) or 0), float(d.get('amount_tva', 0) or 0), float(d.get('amount_ttc', 0) or 0),
        sanitize(d.get('report_number', '')), d.get('report_file'),
        int(bool(d.get('user_training'))), d.get('user_training_file'),
        int(bool(d.get('tech_training'))), d.get('tech_training_file'),
        sanitize(d.get('bordereau_number', '')), d.get('bordereau_date') or None, d.get('bordereau_file'),
        sanitize(d.get('status', 'preparation'))
    ))
    db.commit()
    audit('PAYMENT_FILE_CREATED', f"id={pid} intervention={iid}")
    return jsonify({'id': pid, 'ok': True}), 201

@app.route('/api/payment-files/<pid>', methods=['PUT'])
@require_auth(['sebm'])
def update_payment_file(pid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    if not db.execute('SELECT id FROM payment_files WHERE id=?', (pid,)).fetchone():
        return jsonify({'error': 'Introuvable'}), 404
    str_fields = ['pv_number', 'pv_file', 'invoice_number', 'invoice_file', 'report_number', 'report_file',
                  'user_training_file', 'tech_training_file', 'bordereau_number', 'bordereau_file', 'status']
    date_fields = ['pv_date', 'invoice_date', 'bordereau_date']
    num_fields = ['amount_ht', 'amount_tva', 'amount_ttc']
    bool_fields = ['user_training', 'tech_training']
    ups, ps = [], []
    for f in str_fields:
        if f in d: ups.append(f'{f}=?'); ps.append(sanitize(str(d[f])) if d[f] else d[f])
    for f in date_fields:
        if f in d: ups.append(f'{f}=?'); ps.append(d[f] or None)
    for f in num_fields:
        if f in d: ups.append(f'{f}=?'); ps.append(float(d[f] or 0))
    for f in bool_fields:
        if f in d: ups.append(f'{f}=?'); ps.append(int(bool(d[f])))
    if ups:
        ups.append("updated=datetime('now')"); ps.append(pid)
        db.execute(f"UPDATE payment_files SET {','.join(ups)} WHERE id=?", ps)
        db.commit()
    audit('PAYMENT_FILE_UPDATED', f"id={pid}")
    return jsonify({'ok': True})

# ── ALERTES CONTRATS / PAIEMENTS ────────────────────────────────────────────────
@app.route('/api/contracts/alerts', methods=['GET'])
@require_auth(['sebm'])
def contract_alerts():
    db = get_db()
    today = datetime.utcnow().date()
    alerts = []
    for c in db.execute("SELECT * FROM contracts WHERE status='active'").fetchall():
        c = dict(c)
        try:
            end = datetime.fromisoformat(c['end_date']).date()
            days = (end - today).days
            if days < 0:
                alerts.append({'type': 'contract_expired', 'severity': 'danger',
                    'text': f"Contrat {c['contract_number']} ({c['provider']}) expiré depuis {abs(days)}j",
                    'ref_id': c['id']})
            elif days <= 60:
                alerts.append({'type': 'contract_expiring', 'severity': 'warn' if days > 15 else 'danger',
                    'text': f"Contrat {c['contract_number']} ({c['provider']}) expire dans {days}j",
                    'ref_id': c['id']})
        except (ValueError, TypeError): pass

    rows = db.execute("""SELECT ci.*, c.contract_number, c.provider FROM contract_interventions ci
        JOIN contracts c ON c.id=ci.contract_id WHERE ci.status!='done'""").fetchall()
    for i in rows:
        i = dict(i)
        try:
            planned = datetime.fromisoformat(i['planned_date']).date()
            days = (planned - today).days
            if days < 0:
                alerts.append({'type': 'intervention_late', 'severity': 'danger',
                    'text': f"Intervention {i['provider']} en retard de {abs(days)}j ({i['period_label'] or i['contract_number']})",
                    'ref_id': i['id']})
            elif days <= 15:
                alerts.append({'type': 'intervention_upcoming', 'severity': 'warn',
                    'text': f"Intervention {i['provider']} prévue dans {days}j ({i['period_label'] or i['contract_number']})",
                    'ref_id': i['id']})
        except (ValueError, TypeError): pass

    rows = db.execute("""SELECT pf.*, ci.period_label, c.provider, c.contract_number FROM payment_files pf
        JOIN contract_interventions ci ON ci.id=pf.intervention_id
        JOIN contracts c ON c.id=ci.contract_id
        WHERE pf.status='preparation'""").fetchall()
    for pf in rows:
        pf = dict(pf)
        try:
            created = datetime.fromisoformat(pf['created'])
            days = (datetime.utcnow() - created).days
            if days >= 15:
                alerts.append({'type': 'payment_not_sent', 'severity': 'warn',
                    'text': f"Dossier paiement {pf['provider']} ({pf['period_label'] or pf['contract_number']}) non transmis depuis {days}j",
                    'ref_id': pf['id']})
        except (ValueError, TypeError): pass
    return jsonify(alerts)

# ── RESET (SEBM only) ────────────────────────────────────────────────────────
@app.route('/api/admin/reset', methods=['POST'])
@require_auth(['sebm'])
def reset_data():
    d = request.get_json(silent=True) or {}
    scope = d.get('scope', 'data')  # 'data' | 'data_equipment' | 'full'
    if scope not in ('data', 'data_equipment', 'full'):
        return jsonify({'error': 'Scope invalide'}), 400

    # Sauvegarde obligatoire avant toute réinitialisation
    try:
        bk = backup_now()
        log.info(f'Sauvegarde pré-reset: {os.path.basename(bk)}')
    except Exception as e:
        return jsonify({'error': f'Échec de la sauvegarde préventive: {e}'}), 500

    db = get_db()

    # Toujours supprimé (données opérationnelles)
    db.executescript("""
        DELETE FROM checklists;
        DELETE FROM incidents;
        DELETE FROM maintenance_log;
        DELETE FROM contracts;
        DELETE FROM contract_interventions;
        DELETE FROM payment_files;
        DELETE FROM audit_log;
        DELETE FROM sessions;
        DELETE FROM login_attempts;
    """)

    if scope in ('data_equipment', 'full'):
        db.execute('DELETE FROM equipment')

    if scope == 'full':
        db.execute('DELETE FROM users')
        # Recréer les comptes par défaut pour ne pas se retrouver bloqué
        # (PIN administrateur aléatoire, affiché dans la console)
        seed_default_users(db)

    db.commit()

    # Supprimer les fichiers uploadés
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            try: os.remove(os.path.join(UPLOAD_DIR, f))
            except: pass

    audit('RESET', f"scope={scope} by={g.u['name']}")
    return jsonify({'ok': True, 'scope': scope, 'backup': os.path.basename(bk)})

# ── BACKUP (SEBM only) ───────────────────────────────────────────────────────
@app.route('/api/backup', methods=['GET'])
@require_auth(['sebm'])
def list_backups():
    files = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith('meddeck_') and f.endswith('.db')),
        reverse=True
    )
    result = []
    for f in files[:20]:
        size = os.path.getsize(os.path.join(BACKUP_DIR, f))
        zip_name = f.replace('meddeck_', 'uploads_').replace('.db', '.zip')
        has_uploads = os.path.exists(os.path.join(BACKUP_DIR, zip_name))
        result.append({'name': f, 'size_kb': round(size / 1024, 1), 'has_uploads': has_uploads})
    return jsonify(result)

@app.route('/api/backup', methods=['POST'])
@require_auth(['sebm'])
def trigger_backup():
    try:
        path = backup_now()
        name = os.path.basename(path)
        size_kb = round(os.path.getsize(path) / 1024, 1)
        audit('BACKUP_MANUAL', f"file={name}")
        return jsonify({'ok': True, 'name': name, 'size_kb': size_kb})
    except Exception as e:
        log.error(f'Erreur sauvegarde manuelle: {e}')
        return jsonify({'error': str(e)}), 500

# ── REPORTS ───────────────────────────────────────────────────────────────────
@app.route('/api/reports/monthly', methods=['GET'])
@require_auth(['sebm'])
def monthly_report():
    db   = get_db()
    month= request.args.get('month', datetime.utcnow().strftime('%Y-%m'))
    like = f"{month}%"
    cls  = db.execute('SELECT * FROM checklists WHERE created LIKE ?',(like,)).fetchall()
    inc  = db.execute('SELECT * FROM incidents  WHERE created LIKE ?',(like,)).fetchall()
    mnt  = db.execute('SELECT * FROM maintenance_log WHERE date LIKE ?',(like,)).fetchall()
    eq   = db.execute('SELECT * FROM equipment WHERE active=1').fetchall()
    # MTBF / MTTR approximation from incidents
    closed = [i for i in inc if dict(i)['status']=='closed']
    mttr_avg = 0
    if closed:
        diffs = []
        for i in closed:
            r = dict(i)
            try:
                c = datetime.fromisoformat(r['created']); u = datetime.fromisoformat(r['updated'])
                diffs.append((u-c).total_seconds()/3600)
            except: pass
        if diffs: mttr_avg = round(sum(diffs)/len(diffs), 1)
    return jsonify({
        'month': month,
        'checklists': {'total':len(cls), 'perfect':sum(1 for c in cls if dict(c)['ok_count']==dict(c)['total'])},
        'incidents':  {'total':len(inc), 'open':sum(1 for i in inc if dict(i)['status']=='open'),
                       'closed':len(closed), 'mttr_h':mttr_avg},
        'maintenance':{'total':len(mnt)},
        'equipment':  {'total':len(eq)},
        'details':    {'checklists':[dict(r) for r in cls], 'incidents':[dict(r) for r in inc],
                       'maintenance':[dict(r) for r in mnt]},
    })

@app.route('/api/stats/mtbf', methods=['GET'])
@require_auth()
def mtbf_stats():
    db  = get_db()
    eq  = db.execute('SELECT * FROM equipment WHERE active=1').fetchall()
    result = []
    for e in eq:
        r    = dict(e)
        name_like = f"%{r['name'].split()[0]}%"
        incs = db.execute(
            "SELECT * FROM incidents WHERE (equipment_id=? OR (equipment_id IS NULL AND device LIKE ?)) AND status='closed' ORDER BY created",
            (r['id'], name_like)
        ).fetchall()
        mtbf = None
        if len(incs) >= 2:
            dates = [datetime.fromisoformat(dict(i)['created']) for i in incs]
            gaps  = [(dates[i+1]-dates[i]).total_seconds()/3600 for i in range(len(dates)-1)]
            mtbf  = round(sum(gaps)/len(gaps), 1)
        result.append({'id':r['id'],'name':r['name'],'icon':r['icon'],'incidents':len(incs),'mtbf_h':mtbf})
    return jsonify(result)

# ── SESSIONS (SEBM only) ──────────────────────────────────────────────────────
@app.route('/api/sessions', methods=['GET'])
@require_auth(['sebm'])
def get_sessions():
    db = get_db()
    rows = db.execute("""
        SELECT s.token, s.created, s.expires, s.ip,
               u.id user_id, u.name, u.role, u.room
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.expires > datetime('now')
        ORDER BY s.created DESC
    """).fetchall()
    return jsonify([{k: r[k] for k in r.keys()} for r in rows])

# ── AUDIT ─────────────────────────────────────────────────────────────────────
@app.route('/api/audit', methods=['GET'])
@require_auth(['sebm'])
def get_audit():
    limit = min(int(request.args.get('limit',100)),1000)
    rows  = get_db().execute("SELECT a.*,u.name user_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.ts DESC LIMIT ?",(limit,)).fetchall()
    return jsonify([dict(r) for r in rows])

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route('/api/stats/dashboard', methods=['GET'])
@require_auth()
def dashboard():
    db = get_db()
    return jsonify({
        'checklists_total': db.execute('SELECT COUNT(*) FROM checklists').fetchone()[0],
        'incidents_open':   db.execute("SELECT COUNT(*) FROM incidents WHERE status='open'").fetchone()[0],
        'incidents_total':  db.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],
        'users_active':     db.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0],
        'recent_activity':  [dict(r) for r in db.execute("SELECT a.action,a.detail,a.ts,u.name user_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.ts DESC LIMIT 10").fetchall()]
    })

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "MedDeck — CHU Mohammed VI",
        "short_name": "MedDeck",
        "description": "Gestion dispositifs médicaux — Bloc opératoire",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f2744",
        "theme_color": "#1D9E75",
        "icons": [{"src":"/static/icon.png","sizes":"192x192","type":"image/png"},
                  {"src":"/static/icon.png","sizes":"512x512","type":"image/png"}]
    }), 200, {'Content-Type': 'application/manifest+json'}

@app.route('/sw.js')
def service_worker():
    sw = """
const CACHE = 'meddeck-v2';
const OFFLINE = ['/'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE))));
self.addEventListener('fetch', e => {
  if(e.request.url.includes('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request).then(r => r || caches.match('/'))));
});
"""
    return sw, 200, {'Content-Type': 'application/javascript'}

@app.route('/health')
def health():
    return jsonify({'status':'ok','version':'2.0','time':datetime.utcnow().isoformat()})

# ── Certificat HTTPS (installation/confiance sur téléphone) ────────────────────
@app.route('/cert')
def download_cert():
    cert_path = os.path.join(BASE_DIR, 'instance', 'certs', 'cert.pem')
    if not os.path.exists(cert_path):
        return 'Aucun certificat. Lancez : python generate_cert.py', 404
    return send_from_directory(
        os.path.join(BASE_DIR, 'instance', 'certs'), 'cert.pem',
        mimetype='application/x-x509-ca-cert', as_attachment=True,
        download_name='MedDeck.crt'
    )

# ── Serve frontend ────────────────────────────────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and os.path.exists(os.path.join(RESOURCE_DIR, 'static', path)):
        return send_from_directory(os.path.join(RESOURCE_DIR, 'static'), path)
    html = os.path.join(RESOURCE_DIR, 'MedDeck_v2_Terrain.html')
    if os.path.exists(html):
        with open(html, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    return '<h2>MedDeck — placez MedDeck_v2_Terrain.html dans le dossier meddeck/</h2>', 404

if __name__ == '__main__':
    init_db()
    migrate_db()
    auto_backup()
    _cert = os.path.join(BASE_DIR, 'instance', 'certs', 'cert.pem')
    _key = os.path.join(BASE_DIR, 'instance', 'certs', 'key.pem')
    if os.path.exists(_cert) and os.path.exists(_key):
        log.info("MedDeck v2 — https://localhost:5000 (HTTPS)")
        app.run(host='0.0.0.0', port=5000, debug=False, ssl_context=(_cert, _key))
    else:
        log.info("MedDeck v2 — http://localhost:5000")
        app.run(host='0.0.0.0', port=5000, debug=False)
