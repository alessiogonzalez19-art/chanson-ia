#!/bin/bash

echo "Starting Studio IA Local et Autonome..."
echo ""

source venv/bin/activate

if ! pgrep -x "redis-server" > /dev/null; then
    echo "Starting Redis..."
    redis-server --daemonize yes
fi

echo "Starting FastAPI backend..."
uvicorn api.routes:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Starting Celery worker..."
celery -A workers.celery_app worker --loglevel=info --concurrency=1 &
CELERY_PID=$!

if [ -f "frontend/package.json" ]; then
    echo "Starting optional Vue frontend..."
    cd frontend && npm run dev &
    FRONTEND_PID=$!
fi

echo ""
echo "All services started."
echo ""
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
if [ ! -z "$FRONTEND_PID" ]; then
    echo "Frontend: http://localhost:3000"
else
    echo "Interface: http://localhost:8000"
fi
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $BACKEND_PID $CELERY_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

wait
