#!/bin/bash
# YubiLab Frontend Start Script (Render.com compatible)

export $(cat .env | grep -v '^#' | xargs)

echo "========================================="
echo "  YubiLab AI Agent Frontend v2.0"
echo "========================================="

# CRITICAL: Read PORT from environment (Render.com sets this)
PORT=${PORT:-5000}

echo "Starting on port: $PORT"

gunicorn app:app \
    --bind 0.0.0.0:$PORT \
    --worker-class eventlet \
    --workers 1 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
