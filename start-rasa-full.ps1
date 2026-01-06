# start-rasa-full.ps1
Write-Host "=== Démarrage complet de Rasa (Serveur + Actions) ===" -ForegroundColor Cyan

$rasaDir = $PSScriptRoot

# 1. Setup de l'environnement
Write-Host "`n[1/3] Vérification de l'environnement..." -ForegroundColor Yellow
& "$rasaDir\setup-rasa-env-fixed.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR: La configuration de l'environnement a échoué" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée pour fermer"
    exit 1
}

# 2. Lancer le serveur d'actions dans une nouvelle fenêtre
Write-Host "`n[2/3] Démarrage du serveur d'actions..." -ForegroundColor Yellow
$actionsScript = Join-Path $rasaDir "start-rasa-actions.ps1"
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "& '$actionsScript'" -WindowStyle Normal

# Attendre que le serveur d'actions démarre
Write-Host "Attente du démarrage du serveur d'actions (10 secondes)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 3. Lancer le serveur Rasa dans une nouvelle fenêtre
Write-Host "`n[3/3] Démarrage du serveur Rasa..." -ForegroundColor Yellow
$serverScript = Join-Path $rasaDir "start-rasa-server.ps1"
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "& '$serverScript'" -WindowStyle Normal

Write-Host "`n=== Rasa démarré avec succès ===" -ForegroundColor Green
Write-Host "- Serveur d'actions: http://localhost:5055" -ForegroundColor Cyan
Write-Host "- Serveur Rasa: http://localhost:5005" -ForegroundColor Cyan
Write-Host "`nDeux nouvelles fenêtres PowerShell ont été ouvertes." -ForegroundColor Yellow
Write-Host "Ne fermez pas ces fenêtres pour garder les serveurs actifs." -ForegroundColor Yellow
Write-Host "`nAppuyez sur Entrée pour fermer cette fenêtre..." -ForegroundColor Gray
Read-Host