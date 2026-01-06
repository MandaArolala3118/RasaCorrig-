# start-rasa-server.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "=== Demarrage du serveur Rasa ===" -ForegroundColor Cyan

$rasaDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $rasaDir "venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# Vérifier l'existence de l'environnement virtuel
if (-Not (Test-Path $pythonExe)) {
    Write-Host "ERREUR: Environnement virtuel non trouve a: $venvPath" -ForegroundColor Red
    Write-Host "Executez d'abord setup-rasa-env-fixed.ps1" -ForegroundColor Yellow
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}

Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Yellow
Write-Host "Python exe: $pythonExe" -ForegroundColor Gray

# Changer de répertoire
Set-Location $rasaDir
Write-Host "Repertoire de travail: $rasaDir" -ForegroundColor Gray

# Démarrer le serveur Rasa directement avec python.exe du venv
Write-Host "`nLancement de Rasa sur le port 5005..." -ForegroundColor Green
Write-Host "URL: http://localhost:5005" -ForegroundColor Cyan
Write-Host "CORS active pour tous les domaines (*)" -ForegroundColor Cyan
Write-Host "`nNe fermez pas cette fenetre pour garder le serveur actif." -ForegroundColor Yellow
Write-Host "Appuyez sur Ctrl+C pour arreter le serveur." -ForegroundColor Yellow
Write-Host "----------------------------------------`n" -ForegroundColor Gray

# Lancer Rasa avec gestion d'erreur
try {
    & $pythonExe -m rasa run --enable-api --cors "*" --port 5005
} catch {
    Write-Host "`nERREUR lors du demarrage de Rasa:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Write-Host "`nServeur Rasa arrete." -ForegroundColor Yellow
    Read-Host "Appuyez sur Entree pour fermer cette fenetre"
}