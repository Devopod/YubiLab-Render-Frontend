"""
YubiLab Frontend — root app.py
Re-exports the Flask app from flask_backend for compatibility with
both `gunicorn app:app` and `gunicorn flask_backend.app:app`.
"""
from flask_backend.app import app  # noqa: F401

if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
