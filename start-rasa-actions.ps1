# start-rasa-actions.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "=== Demarrage du serveur d'actions Rasa ===" -ForegroundColor Cyan

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
Write-Host "Répertoire de travail: $rasaDir" -ForegroundColor Gray

# Démarrer le serveur d'actions
Write-Host "`nLancement du serveur d'actions sur le port 5055..." -ForegroundColor Green
Write-Host "URL: http://localhost:5055" -ForegroundColor Cyan
Write-Host "`nNe fermez pas cette fenêtre pour garder le serveur actif." -ForegroundColor Yellow
Write-Host "Appuyez sur Ctrl+C pour arrêter le serveur." -ForegroundColor Yellow
Write-Host "----------------------------------------`n" -ForegroundColor Gray

# Lancer le serveur d'actions avec gestion d'erreur
try {
    rasa run actions --port 5055
} catch {
    Write-Host "`nERREUR lors du démarrage du serveur d'actions:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Write-Host "`nServeur d'actions arrêté." -ForegroundColor Yellow
    Read-Host "Appuyez sur Entrée pour fermer cette fenêtre"
}