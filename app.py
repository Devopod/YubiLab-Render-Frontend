"""
YubiLab Frontend - Flask Application
VS Code Style IDE with Fully Autonomous AI Agent
Deployed on Render.com with gunicorn + eventlet
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.groq_service import groq_service
from services.worker_client import worker_client
from services.auth_service import (
    init_db, register_user, login_user, get_user, verify_jwt,
    generate_jwt, check_ai_limit, increment_ai_usage,
    verify_bkash_payment, get_user_stats, get_all_users
)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.getenv("SECRET_KEY", "yubilab-flask-secret-2024-production")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_timeout=60)

# Initialize database
init_db()


# ============================================================
# HELPERS
# ============================================================

def get_current_user():
    """Get current user from session."""
    token = session.get("token")
    if not token:
        return None
    payload = verify_jwt(token)
    if not payload:
        session.pop("token", None)
        return None
    return payload


def require_login(f):
    """Decorator to require login for page routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def require_admin_page(f):
    """Decorator to require admin for page routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get("plan") != "admin":
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def api_require_auth(f):
    """Decorator for API routes requiring auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = session.get("token", "")
        if not token:
            return jsonify({"error": "Authentication required"}), 401
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.user = payload
        request.jwt_token = token
        return f(*args, **kwargs)
    return decorated


# ============================================================
# PAGE ROUTES
# ============================================================

@app.route("/")
def index():
    """Root route - redirect to IDE or login."""
    user = get_current_user()
    if user:
        return redirect(url_for("ide_page"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    """Login page."""
    return render_template("login.html")


@app.route("/register")
def register_page():
    """Registration page."""
    return render_template("register.html")


@app.route("/ide")
@require_login
def ide_page():
    """Main IDE page - VS Code style."""
    user = get_current_user()
    return render_template("ide.html", user=user)


@app.route("/dashboard")
@require_login
def dashboard_page():
    """User dashboard."""
    user = get_current_user()
    stats = get_user_stats(user["user_id"])
    return render_template("dashboard.html", user=user, stats=stats)


@app.route("/pricing")
def pricing_page():
    """Pricing page."""
    user = get_current_user()
    return render_template("pricing.html", user=user)


@app.route("/payment")
@require_login
def payment_page():
    """bKash payment page."""
    user = get_current_user()
    return render_template("payment.html", user=user)


@app.route("/admin")
@require_admin_page
def admin_page():
    """Admin panel."""
    users = get_all_users()
    return render_template("admin.html", users=users)


@app.route("/docs")
def docs_page():
    """Documentation page."""
    user = get_current_user()
    return render_template("docs.html", user=user)


@app.route("/logout")
def logout_page():
    """Logout and redirect to login."""
    session.pop("token", None)
    return redirect(url_for("login_page"))


# ============================================================
# AUTH API ROUTES
# ============================================================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    """Register a new user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    success, result = register_user(
        username=data.get("username", "").strip(),
        password=data.get("password", "").strip(),
        email=data.get("email", "").strip(),
    )

    if success:
        session["token"] = result["token"]
        return jsonify({"success": True, **result}), 201
    return jsonify({"success": False, **result}), 400


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """Login a user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    success, result = login_user(
        username=data.get("username", "").strip(),
        password=data.get("password", "").strip(),
    )

    if success:
        session["token"] = result["token"]
        return jsonify({"success": True, **result})
    return jsonify({"success": False, **result}), 401


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    """Logout."""
    session.pop("token", None)
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
@api_require_auth
def api_me():
    """Get current user."""
    user = request.user
    db_user = get_user(user["user_id"])
    return jsonify({
        "user_id": user["user_id"],
        "username": user["username"],
        "plan": user.get("plan", "free"),
        "email": db_user.get("email", "") if db_user else "",
    })


# ============================================================
# AI AGENT API ROUTES
# ============================================================

@app.route("/api/agent/sessions", methods=["POST"])
@api_require_auth
def create_agent_session():
    """Create an AI agent session."""
    data = request.get_json() or {}
    task = data.get("task", "")

    if not task:
        return jsonify({"error": "Task description required"}), 400

    user = request.user
    result = worker_client.create_agent_session(task, request.jwt_token)
    return jsonify(result), 201


@app.route("/api/agent/sessions", methods=["GET"])
@api_require_auth
def list_agent_sessions():
    """List agent sessions."""
    user = request.user
    result = worker_client.list_agent_sessions(request.jwt_token)
    return jsonify(result)


@app.route("/api/agent/sessions/<session_id>/chat", methods=["POST"])
@api_require_auth
def agent_chat(session_id):
    """Chat with the AI agent."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user = request.user

    # Check AI limit
    allowed, remaining = check_ai_limit(user["user_id"])
    if not allowed:
        return jsonify({"error": "AI prompt limit reached. Upgrade to Pro for unlimited access.", "remaining": remaining}), 429

    # Increment usage
    increment_ai_usage(user["user_id"])

    # Try worker first, fall back to direct Groq
    result = worker_client.agent_chat(session_id, data["message"], request.jwt_token)

    if "error" in result and "Cannot connect" in result.get("error", ""):
        # Fall back to direct Groq API
        messages = [
            {"role": "system", "content": "You are YubiLab AI Agent, an autonomous software engineer. Help the user with their coding task. Be concise and provide code."},
            {"role": "user", "content": data["message"]},
        ]
        response = groq_service.chat_completion(messages)
        result = {"status": "completed", "response": response, "source": "direct_groq"}

    return jsonify(result)


@app.route("/api/agent/sessions/<session_id>/activity", methods=["GET"])
@api_require_auth
def agent_activity(session_id):
    """Get agent activity log."""
    result = worker_client.get_agent_activity(session_id, request.jwt_token)
    return jsonify(result)


# ============================================================
# AI CHAT (Direct Groq) - No agent, just chat
# ============================================================

@app.route("/api/ai/chat", methods=["POST"])
@api_require_auth
def ai_chat():
    """Direct AI chat using Groq API."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user = request.user

    # Check limit
    allowed, remaining = check_ai_limit(user["user_id"])
    if not allowed:
        return jsonify({"error": "AI prompt limit reached. Upgrade to Pro.", "remaining": remaining}), 429

    increment_ai_usage(user["user_id"])

    messages = data.get("messages", [
        {"role": "system", "content": "You are YubiLab AI, an expert coding assistant. Provide clear, concise answers with code examples when helpful."},
    ])
    messages.append({"role": "user", "content": data["message"]})

    response = groq_service.chat_completion(
        messages=messages,
        temperature=data.get("temperature", 0.3),
        max_tokens=data.get("max_tokens", 4096),
    )

    return jsonify({"success": True, "response": response, "remaining": remaining - 1})


# ============================================================
# WORKSPACE API ROUTES
# ============================================================

@app.route("/api/workspace/files", methods=["GET"])
@api_require_auth
def list_files():
    """List files in workspace."""
    workspace_id = request.args.get("workspace_id", "default")
    path = request.args.get("path", "")
    result = worker_client.list_files(workspace_id, path, request.jwt_token)
    return jsonify(result)


@app.route("/api/workspace/files/<path:file_path>", methods=["GET"])
@api_require_auth
def read_file(file_path):
    """Read a file."""
    workspace_id = request.args.get("workspace_id", "default")
    result = worker_client.read_file(workspace_id, file_path, request.jwt_token)
    return jsonify(result)


@app.route("/api/workspace/files/<path:file_path>", methods=["PUT"])
@api_require_auth
def write_file(file_path):
    """Write a file."""
    data = request.get_json()
    workspace_id = data.get("workspace_id", "default") if data else "default"
    result = worker_client.write_file(workspace_id, file_path, data.get("content", ""), request.jwt_token)
    return jsonify(result)


# ============================================================
# TERMINAL API ROUTES
# ============================================================

@app.route("/api/terminal/sessions", methods=["POST"])
@api_require_auth
def create_terminal():
    """Create terminal session."""
    data = request.get_json() or {}
    result = worker_client.create_terminal(data.get("workspace_id", "default"), request.jwt_token)
    return jsonify(result), 201


@app.route("/api/terminal/sessions/<session_id>/execute", methods=["POST"])
@api_require_auth
def execute_command(session_id):
    """Execute terminal command."""
    data = request.get_json()
    if not data or not data.get("command"):
        return jsonify({"error": "Command required"}), 400
    result = worker_client.execute_command(session_id, data["command"], request.jwt_token)
    return jsonify(result)


# ============================================================
# PAYMENT API ROUTES
# ============================================================

@app.route("/api/payment/verify", methods=["POST"])
@api_require_auth
def verify_payment():
    """Verify bKash payment."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    trxid = data.get("trxid", "").strip()
    bkash_number = data.get("bkash_number", "").strip()

    if not trxid:
        return jsonify({"error": "Transaction ID required"}), 400

    user = request.user
    success, message = verify_bkash_payment(user["user_id"], trxid, bkash_number)

    if success:
        # Generate new token with pro plan
        new_token = generate_jwt(user["user_id"], user["username"], "pro")
        session["token"] = new_token

    return jsonify({"success": success, "message": message})


# ============================================================
# FILE UPLOAD
# ============================================================

@app.route("/api/upload", methods=["POST"])
@api_require_auth
def upload_file():
    """Upload a project file or archive."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    session_id = request.form.get("session_id", "")

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    upload_dir = "/tmp/yubilab_uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    return jsonify({
        "success": True,
        "filename": filename,
        "path": file_path,
        "session_id": session_id,
    })


# ============================================================
# ADMIN API ROUTES
# ============================================================

@app.route("/api/admin/users", methods=["GET"])
@api_require_auth
def admin_users():
    """List all users (admin)."""
    user = request.user
    if user.get("plan") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    users = get_all_users()
    return jsonify({"users": users})


@app.route("/api/admin/stats", methods=["GET"])
@api_require_auth
def admin_stats():
    """Get admin stats."""
    user = request.user
    if user.get("plan") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    users = get_all_users()
    return jsonify({
        "total_users": len(users),
        "pro_users": sum(1 for u in users if u["plan"] == "pro"),
        "free_users": sum(1 for u in users if u["plan"] == "free"),
    })


# ============================================================
# WEBSOCKET EVENTS
# ============================================================

@socketio.on("connect")
def ws_connect():
    logger.info(f"WS Connected: {request.sid}")
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def ws_disconnect():
    logger.info(f"WS Disconnected: {request.sid}")


@socketio.on("join_session")
def ws_join(data):
    session_id = data.get("session_id")
    if session_id:
        join_room(session_id)
        emit("joined", {"session_id": session_id})


@socketio.on("agent_chat")
def ws_agent_chat(data):
    """Real-time agent chat via WebSocket."""
    session_id = data.get("session_id")
    message = data.get("message")

    if not session_id or not message:
        emit("error", {"message": "session_id and message required"})
        return

    # Stream AI response
    emit("agent_thinking", {"thinking": "Processing your request..."})

    messages = [
        {"role": "system", "content": "You are YubiLab AI Agent - an autonomous software engineer. Help the user accomplish their coding tasks. Provide code, explanations, and step-by-step guidance."},
        {"role": "user", "content": message},
    ]

    full_response = ""
    for chunk in groq_service.stream_completion(messages):
        full_response += chunk
        emit("agent_stream", {"chunk": chunk})

    emit("agent_complete", {"response": full_response, "session_id": session_id})


@socketio.on("terminal_input")
def ws_terminal_input(data):
    """Terminal input via WebSocket."""
    session_id = data.get("session_id")
    command = data.get("command")

    if not session_id or not command:
        return

    result = worker_client.execute_command(session_id, command, session.get("token", ""))
    emit("terminal_output", result)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "yubilab-frontend",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting YubiLab Frontend on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=False)
