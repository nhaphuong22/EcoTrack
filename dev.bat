@echo off
title EcoTrack Unified Dev Server
echo ================================================================
echo   EcoTrack - Khoi dong toan bo he thong trong 1 cua so
echo ================================================================
echo [1/3] Khoi dong CSDL PostgreSQL trong Docker...
docker compose up -d db

echo.
echo [2/3] Khoi dong song song Backend (Express), AI Engine (FastAPI), va Frontend (Vite)...
echo - Frontend:    http://localhost:3000 (Hot-Reload khi sua code)
echo - Backend API: http://localhost:5000 (Express.js Gateway)
echo - AI Service:  http://localhost:8000 (FastAPI ML & Copilot Engine)
echo - AI Docs:     http://localhost:8000/docs
echo.
echo Nhan Ctrl+C de dung toan bo ung dung.
echo ================================================================

npx concurrently -n "AI,BACKEND,FRONTEND" -c "magenta,green,cyan" "python -m uvicorn src.main:app --app-dir ai-service --reload --port 8000" "npm run dev --prefix backend" "npm run dev --prefix frontend"
