# Script pour programmer l'extinction automatique à 18h
# Ce script doit être exécuté en tant qu'administrateur

# Vérifier si le script est exécuté en tant qu'administrateur
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERREUR: Ce script doit être exécuté en tant qu'administrateur!" -ForegroundColor Red
    Write-Host "Faites un clic droit sur le fichier et sélectionnez 'Exécuter en tant qu'administrateur'" -ForegroundColor Yellow
    pause
    exit
}

Write-Host "=== Configuration de l'extinction automatique à 18h ===" -ForegroundColor Cyan
Write-Host ""

# Supprimer la tâche si elle existe déjà
$taskExists = Get-ScheduledTask -TaskName "ExtinctionAuto18h" -ErrorAction SilentlyContinue
if ($taskExists) {
    Write-Host "Suppression de l'ancienne tâche..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName "ExtinctionAuto18h" -Confirm:$false
}

# Créer l'action (extinction)
$action = New-ScheduledTaskAction -Execute "shutdown.exe" -Argument "/s /f /t 0"

# Créer le déclencheur (tous les jours à 18h)
$trigger = New-ScheduledTaskTrigger -Daily -At 18:00

# Configurer les paramètres (important: réveiller l'ordinateur)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -StartWhenAvailable

# Créer le principal (exécuter avec les privilèges système)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Enregistrer la tâche planifiée
Register-ScheduledTask -TaskName "ExtinctionAuto18h" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Éteint automatiquement l'ordinateur à 18h chaque jour, même en veille"

Write-Host ""
Write-Host "Tâche créée avec succès!" -ForegroundColor Green
Write-Host ""
Write-Host "Votre ordinateur s'éteindra automatiquement à 18h00 chaque jour." -ForegroundColor White
Write-Host "L'ordinateur sera réveillé de la veille si nécessaire." -ForegroundColor White
Write-Host ""
Write-Host "Pour supprimer cette tâche, exécutez la commande suivante:" -ForegroundColor Gray
Write-Host "  schtasks /delete /tn ExtinctionAuto18h /f" -ForegroundColor Gray
Write-Host ""

pause