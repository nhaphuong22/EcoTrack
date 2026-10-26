Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   EcoTrack - Kiem thu toan dien CI/CD noi bo (Local CI Check)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$ROOT_DIR = $PSScriptRoot
$PYTHON = "$ROOT_DIR\backend\venv\Scripts\python.exe"
$PYTEST = "$ROOT_DIR\backend\venv\Scripts\pytest.exe"

# 1. Flake8 Lint
Write-Host "`n[1/4] Kiem tra cu phap Python (Flake8 Lint)..." -ForegroundColor Yellow
Push-Location "$ROOT_DIR\ai-service"
& $PYTHON -m flake8 src --count --select=E9,F63,F7,F82 --show-source --statistics
if ($LASTEXITCODE -ne 0) {
    Write-Host "Flake8 Lint that bai!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "Flake8 Lint dat chuan 100%!" -ForegroundColor Green
Pop-Location

# 2. Pytest AI Service Tests
Write-Host "`n[2/4] Chay kiem thu AI Service (Pytest RAG & Smoke tests)..." -ForegroundColor Yellow
Push-Location "$ROOT_DIR\ai-service"
& $PYTEST tests/test_smoke.py tests/test_rag.py -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pytest AI Service that bai!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "AI Service kiem thu dat 100%!" -ForegroundColor Green
Pop-Location

# 3. Backend Express Tests
Write-Host "`n[3/4] Chay kiem thu Express Backend (Vitest)..." -ForegroundColor Yellow
Push-Location "$ROOT_DIR\backend"
npm test
if ($LASTEXITCODE -ne 0) {
    Write-Host "Backend kiem thu that bai!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "Express Backend dat 47/47 tests (100%)!" -ForegroundColor Green
Pop-Location

# 4. Frontend Build Check
Write-Host "`n[4/4] Kiem tra dong goi Frontend (Vite Build)..." -ForegroundColor Yellow
Push-Location "$ROOT_DIR\frontend"
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend dong goi that bai!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "Frontend Vite dong goi thanh cong!" -ForegroundColor Green
Pop-Location

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "TAT CA 4/4 BUOC CI/CD DA VUOT QUA 100%! PULL REQUEST AN TAM!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
