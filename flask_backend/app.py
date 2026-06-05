"""
YubiLab Frontend — Flask application with bKash, Admin Panel, and Worker proxy.
Deployed on Render.com.
"""
import os
import uuid
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from functools import wraps
import jwt
from datetime import datetime, timedelta
import sqlite3
import bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='../frontend', static_url_path='')

# Config from .env
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'yubilab-flask-secret-2024-production')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'yubilab-secure-jwt-2024-production')
app.config['WORKER_URL'] = os.getenv('WORKER_URL', 'http://localhost:8000')
app.config['WORKER_API_KEY'] = os.getenv('WORKER_API_KEY', 'yubilab-worker-api-key-2024')
app.config['BKASH_NUMBER'] = os.getenv('BKASH_NUMBER', '01849691859')
app.config['BKASH_AMOUNT'] = int(os.getenv('BKASH_AMOUNT', '1200'))
app.config['BKASH_ENTERPRISE_AMOUNT'] = int(os.getenv('BKASH_ENTERPRISE_AMOUNT', '5000'))
app.config['FREE_AI_PROMPTS_DAILY'] = int(os.getenv('FREE_AI_PROMPTS_DAILY', '3'))
app.config['FREE_APK_BUILDS_DAILY'] = int(os.getenv('FREE_APK_BUILDS_DAILY', '1'))

CORS(app, origins="*")

DB_PATH = os.path.join(os.path.dirname(__file__), 'yubilab_frontend.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            tier INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ai_prompts_used_today INTEGER DEFAULT 0,
            apk_builds_used_today INTEGER DEFAULT 0,
            last_reset_date TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            trx_id TEXT NOT NULL,
            screenshot_path TEXT NOT NULL,
            target_tier INTEGER DEFAULT 2,
            status TEXT DEFAULT 'pending',
            admin_note TEXT DEFAULT '',
            reviewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create default admin
    existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        pw_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (username, email, password_hash, tier, is_admin) VALUES (?, ?, ?, 3, 1)",
            ('admin', 'admin@yubilab.com', pw_hash)
        )

    conn.commit()
    conn.close()


init_db()


# ─── Auth Helpers ───
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE id = ?", [data['user_id']]).fetchone()
            conn.close()
            if not user:
                return jsonify({'error': 'User not found'}), 401
            if user['is_banned']:
                return jsonify({'error': 'Account banned'}), 403
            request.current_user = dict(user)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE id = ?", [data['user_id']]).fetchone()
            conn.close()
            if not user or not user['is_admin']:
                return jsonify({'error': 'Admin access required'}), 403
            request.current_user = dict(user)
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


def proxy_to_worker(path, method='GET', data=None, files=None):
    """Proxy request to macOS worker backend"""
    url = f"{app.config['WORKER_URL']}{path}"
    headers = {
        'X-API-Key': app.config['WORKER_API_KEY'],
    }

    # Forward auth token
    auth = request.headers.get('Authorization')
    if auth:
        headers['Authorization'] = auth

    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, params=data, timeout=60)
        elif method == 'POST':
            if files:
                resp = requests.post(url, headers=headers, data=data,
                                     files=files, timeout=120)
            else:
                resp = requests.post(url, headers=headers, json=data, timeout=120)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return jsonify({'error': 'Method not supported'}), 400

        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Worker offline. Start the macOS worker.'}), 502
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Worker request timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password min 6 chars'}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, pw_hash)
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username or email already exists'}), 400
    conn.close()

    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['JWT_SECRET'], algorithm='HS256')

    return jsonify({'token': token, 'user': {'id': user_id, 'username': username, 'tier': 1}})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?",
        [username, username]
    ).fetchone()
    conn.close()

    if not user or not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'error': 'Invalid credentials'}), 401

    if user['is_banned']:
        return jsonify({'error': 'Account banned'}), 403

    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['JWT_SECRET'], algorithm='HS256')

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'tier': user['tier'],
            'is_admin': bool(user['is_admin'])
        }
    })


@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    u = request.current_user
    tier_names = {1: 'Free', 2: 'Pro', 3: 'Enterprise'}
    return jsonify({
        'id': u['id'],
        'username': u['username'],
        'email': u['email'],
        'tier': u['tier'],
        'tier_name': tier_names.get(u['tier'], 'Free'),
        'is_admin': bool(u['is_admin'])
    })


# ═══════════════════════════════════════════════════════════
#  BKASH DEPOSIT ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/api/deposits/bkash-info', methods=['GET'])
def bkash_info():
    return jsonify({
        'number': app.config['BKASH_NUMBER'],
        'pro_amount': app.config['BKASH_AMOUNT'],
        'enterprise_amount': app.config['BKASH_ENTERPRISE_AMOUNT']
    })


@app.route('/api/deposits/submit', methods=['POST'])
@token_required
def submit_deposit():
    user = request.current_user

    trx_id = request.form.get('trx_id', '').strip()
    amount = int(request.form.get('amount', 0))
    target_tier = int(request.form.get('target_tier', 2))
    screenshot = request.files.get('screenshot')

    # Validate TrxID (mandatory)
    if not trx_id or len(trx_id) < 5:
        return jsonify({'error': 'TrxID is required (min 5 characters)'}), 400

    # Validate screenshot (mandatory)
    if not screenshot or not screenshot.filename:
        return jsonify({'error': 'Screenshot is required'}), 400

    allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp']
    if screenshot.content_type not in allowed:
        return jsonify({'error': 'Screenshot must be PNG, JPG, or WEBP'}), 400

    # Validate amount
    expected = app.config['BKASH_AMOUNT'] if target_tier == 2 else app.config['BKASH_ENTERPRISE_AMOUNT']
    if amount != expected:
        return jsonify({'error': f'Amount must be ৳{expected} for tier {target_tier}'}), 400

    # Save screenshot
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'bkash_screenshots')
    os.makedirs(upload_dir, exist_ok=True)

    ext = screenshot.filename.rsplit('.', 1)[-1] if '.' in screenshot.filename else 'png'
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    screenshot.save(filepath)

    # Save to DB
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO deposits (user_id, amount, trx_id, screenshot_path, target_tier)
            VALUES (?, ?, ?, ?, ?)
        """, (user['id'], amount, trx_id, filename, target_tier))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()

    return jsonify({'message': 'Deposit submitted! Admin will review shortly.', 'status': 'pending'})


@app.route('/api/deposits/my', methods=['GET'])
@token_required
def my_deposits():
    user = request.current_user
    conn = get_db()
    deposits = conn.execute(
        "SELECT * FROM deposits WHERE user_id = ? ORDER BY created_at DESC",
        [user['id']]
    ).fetchall()
    conn.close()
    return jsonify({'deposits': [dict(d) for d in deposits]})


# ═══════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    pro_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE tier = 2").fetchone()['c']
    ent_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE tier = 3").fetchone()['c']
    pending = conn.execute("SELECT COUNT(*) as c FROM deposits WHERE status = 'pending'").fetchone()['c']
    revenue = conn.execute("SELECT COALESCE(SUM(amount),0) as t FROM deposits WHERE status = 'approved'").fetchone()['t']
    conn.close()

    return jsonify({
        'total_users': total_users,
        'pro_users': pro_users,
        'enterprise_users': ent_users,
        'pending_deposits': pending,
        'total_revenue_bdt': revenue
    })


@app.route('/api/admin/deposits', methods=['GET'])
@admin_required
def admin_deposits():
    status = request.args.get('status', 'pending')
    conn = get_db()
    if status == 'all':
        rows = conn.execute("""
            SELECT d.*, u.username, u.email
            FROM deposits d JOIN users u ON d.user_id = u.id
            ORDER BY d.created_at DESC LIMIT 200
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT d.*, u.username, u.email
            FROM deposits d JOIN users u ON d.user_id = u.id
            WHERE d.status = ? ORDER BY d.created_at DESC LIMIT 200
        """, [status]).fetchall()
    conn.close()
    return jsonify({'deposits': [dict(r) for r in rows]})


@app.route('/api/admin/deposit/screenshot/<filename>')
@admin_required
def admin_screenshot(filename):
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'bkash_screenshots')
    return send_from_directory(upload_dir, filename)


@app.route('/api/admin/deposits/approve', methods=['POST'])
@admin_required
def admin_approve():
    data = request.json
    deposit_id = data.get('deposit_id')
    note = data.get('admin_note', '')

    conn = get_db()
    deposit = conn.execute("SELECT * FROM deposits WHERE id = ?", [deposit_id]).fetchone()
    if not deposit:
        conn.close()
        return jsonify({'error': 'Deposit not found'}), 404
    if deposit['status'] != 'pending':
        conn.close()
        return jsonify({'error': f"Already {deposit['status']}"}), 400

    conn.execute("""
        UPDATE deposits SET status = 'approved', admin_note = ?, reviewed_at = datetime('now')
        WHERE id = ?
    """, [note, deposit_id])

    conn.execute("UPDATE users SET tier = ? WHERE id = ?", [deposit['target_tier'], deposit['user_id']])
    conn.commit()
    conn.close()

    return jsonify({'message': f'Approved! User upgraded to tier {deposit["target_tier"]}'})


@app.route('/api/admin/deposits/reject', methods=['POST'])
@admin_required
def admin_reject():
    data = request.json
    deposit_id = data.get('deposit_id')
    note = data.get('admin_note', 'Rejected by admin')

    conn = get_db()
    conn.execute("""
        UPDATE deposits SET status = 'rejected', admin_note = ?, reviewed_at = datetime('now')
        WHERE id = ?
    """, [note, deposit_id])
    conn.commit()
    conn.close()

    return jsonify({'message': 'Deposit rejected'})


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_users():
    search = request.args.get('search', '')
    conn = get_db()
    if search:
        users = conn.execute(
            "SELECT id, username, email, tier, is_banned, created_at FROM users WHERE username LIKE ? OR email LIKE ?",
            [f'%{search}%', f'%{search}%']
        ).fetchall()
    else:
        users = conn.execute(
            "SELECT id, username, email, tier, is_banned, created_at FROM users ORDER BY id DESC LIMIT 200"
        ).fetchall()
    conn.close()
    return jsonify({'users': [dict(u) for u in users]})


@app.route('/api/admin/users/tier', methods=['POST'])
@admin_required
def admin_change_tier():
    data = request.json
    user_id = data.get('user_id')
    tier = data.get('tier')
    if tier not in [1, 2, 3]:
        return jsonify({'error': 'Invalid tier'}), 400
    conn = get_db()
    conn.execute("UPDATE users SET tier = ? WHERE id = ?", [tier, user_id])
    conn.commit()
    conn.close()
    return jsonify({'message': f'User tier changed to {tier}'})


@app.route('/api/admin/users/ban', methods=['POST'])
@admin_required
def admin_ban():
    data = request.json
    user_id = data.get('user_id')
    ban = data.get('ban', True)
    conn = get_db()
    conn.execute("UPDATE users SET is_banned = ? WHERE id = ?", [1 if ban else 0, user_id])
    conn.commit()
    conn.close()
    return jsonify({'message': 'User banned' if ban else 'User unbanned'})


# ═══════════════════════════════════════════════════════════
#  WORKER PROXY ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/api/worker/execute', methods=['POST'])
@token_required
def proxy_execute():
    return proxy_to_worker('/execute/run', 'POST', data=request.json)


@app.route('/api/worker/languages', methods=['GET'])
@token_required
def proxy_languages():
    return proxy_to_worker('/execute/languages')


@app.route('/api/worker/terminal/create', methods=['POST'])
@token_required
def proxy_terminal_create():
    return proxy_to_worker('/terminal/create', 'POST', data=request.json)


@app.route('/api/worker/terminal/<sid>/write', methods=['POST'])
@token_required
def proxy_terminal_write(sid):
    return proxy_to_worker(f'/terminal/{sid}/write', 'POST', data=request.json)


@app.route('/api/worker/terminal/<sid>/read', methods=['GET'])
@token_required
def proxy_terminal_read(sid):
    return proxy_to_worker(f'/terminal/{sid}/read')


@app.route('/api/worker/terminal/<sid>', methods=['DELETE'])
@token_required
def proxy_terminal_delete(sid):
    return proxy_to_worker(f'/terminal/{sid}', 'DELETE')


@app.route('/api/worker/health', methods=['GET'])
@token_required
def proxy_health():
    return proxy_to_worker('/health')


# ─── Agent Proxy ───
@app.route('/api/worker/agent/run', methods=['POST'])
@token_required
def proxy_agent_run():
    data = request.json
    data['user_id'] = request.current_user['id']
    return proxy_to_worker('/agent/run', 'POST', data=data)


@app.route('/api/worker/agent/status/<run_id>', methods=['GET'])
@token_required
def proxy_agent_status(run_id):
    return proxy_to_worker(f'/agent/status/{run_id}')


@app.route('/api/worker/agent/stop/<run_id>', methods=['POST'])
@token_required
def proxy_agent_stop(run_id):
    return proxy_to_worker(f'/agent/stop/{run_id}')


@app.route('/api/worker/agent/runs', methods=['GET'])
@token_required
def proxy_agent_runs():
    return proxy_to_worker('/agent/runs', 'GET', data=dict(request.args))


@app.route('/api/worker/agent/run/<run_id>/logs', methods=['GET'])
@token_required
def proxy_agent_logs(run_id):
    return proxy_to_worker(f'/agent/run/{run_id}/logs')


# ─── Solve Log Proxy ───
@app.route('/api/worker/solve-log/<workspace_id>', methods=['GET'])
@token_required
def proxy_solve_log(workspace_id):
    return proxy_to_worker(f'/solve-log/{workspace_id}')


# ─── RAG Proxy ───
@app.route('/api/worker/rag/upload', methods=['POST'])
@token_required
def proxy_rag_upload():
    files = {'file': (request.files['file'].filename, request.files['file'].read(), request.files['file'].content_type)}
    data = {
        'user_id': request.current_user['id'],
        'workspace_id': request.form.get('workspace_id', '')
    }
    return proxy_to_worker('/rag/upload', 'POST', data=data, files=files)


@app.route('/api/worker/rag/query', methods=['POST'])
@token_required
def proxy_rag_query():
    return proxy_to_worker('/rag/query', 'POST', data=request.json)


# ─── Deposit Proxy to Worker ───
@app.route('/api/worker/deposits/bkash-info', methods=['GET'])
def proxy_bkash_info():
    return proxy_to_worker('/deposits/bkash-info')


# ─── Flutter Proxy ───
@app.route('/api/worker/flutter/build', methods=['POST'])
@token_required
def proxy_flutter_build():
    return proxy_to_worker('/flutter/build', 'POST', data=request.json)


@app.route('/api/worker/flutter/status/<job_id>', methods=['GET'])
@token_required
def proxy_flutter_status(job_id):
    return proxy_to_worker(f'/flutter/status/{job_id}')


# ═══════════════════════════════════════════════════════════
#  STATIC PAGES
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/login')
def login_page():
    return send_from_directory('../frontend', 'login.html')


@app.route('/register')
def register_page():
    return send_from_directory('../frontend', 'register.html')


@app.route('/editor')
def editor_page():
    return send_from_directory('../frontend', 'editor.html')


@app.route('/bkash')
def bkash_page():
    return send_from_directory('../frontend', 'bkash.html')


@app.route('/admin')
def admin_page():
    return send_from_directory('../frontend', 'admin.html')


@app.route('/pricing')
def pricing_page():
    return send_from_directory('../frontend', 'pricing.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('../frontend', path)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
