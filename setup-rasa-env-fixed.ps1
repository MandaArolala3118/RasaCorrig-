# setup-rasa-env-fixed.ps1
# Exécuter en tant qu'administrateur: PowerShell > Clic droit > "Exécuter en tant qu'administrateur"

Write-Host "=== Configuration environnement Rasa ===" -ForegroundColor Cyan

$rasaDir = $PSScriptRoot
$venvPath = Join-Path $rasaDir "venv"
$requirementsPath = Join-Path $rasaDir "requirements.txt"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

# Fonction pour vérifier les privilèges administrateur
function Test-Admin {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-Not (Test-Admin)) {
    Write-Host "ATTENTION: Script non exécuté en tant qu'administrateur" -ForegroundColor Yellow
    Write-Host "Certaines opérations peuvent échouer. Relancez PowerShell en administrateur si nécessaire." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}

# Vérifier si l'environnement virtuel existe déjà
if (Test-Path $venvPath) {
    Write-Host "Environnement virtuel détecté: $venvPath" -ForegroundColor Green
    
    # Vérifier si l'environnement est fonctionnel
    if (Test-Path $activateScript) {
        Write-Host "Vérification de l'environnement existant..." -ForegroundColor Yellow
        
        # Tester si Rasa est installé
        & $activateScript
        $rasaCheck = python -m rasa --version 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host " Environnement virtuel fonctionnel!" -ForegroundColor Green
            Write-Host " Rasa version: $rasaCheck" -ForegroundColor Cyan
            Write-Host "`n=== Environnement Rasa prêt (existant) ===" -ForegroundColor Green
            return 0
        } else {
            Write-Host "L'environnement existe mais Rasa n'est pas installé correctement" -ForegroundColor Yellow
            Write-Host "Reconstruction de l'environnement..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "L'environnement virtuel est corrompu (pas de script d'activation)" -ForegroundColor Yellow
        Write-Host "Reconstruction de l'environnement..." -ForegroundColor Yellow
    }
    
    # Si on arrive ici, l'environnement doit être reconstruit
    Write-Host "Suppression de l'environnement virtuel corrompu..." -ForegroundColor Yellow
    
    # Arrêter tous les processus Python qui pourraient utiliser le venv
    Get-Process | Where-Object {$_.Path -like "*$venvPath*"} | Stop-Process -Force -ErrorAction SilentlyContinue
    
    # Attendre un peu
    Start-Sleep -Seconds 2
    
    # Supprimer avec gestion d'erreur
    try {
        Remove-Item -Path $venvPath -Recurse -Force -ErrorAction Stop
        Write-Host "Environnement virtuel supprimé" -ForegroundColor Green
    }
    catch {
        Write-Host "Impossible de supprimer complètement le dossier venv" -ForegroundColor Red
        Write-Host "Fermez tous les programmes utilisant Python et réessayez" -ForegroundColor Yellow
        Write-Host "Ou supprimez manuellement: $venvPath" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Aucun environnement virtuel détecté. Création d'un nouveau..." -ForegroundColor Yellow
}

# Créer un nouvel environnement virtuel
Write-Host "Création d'un nouvel environnement virtuel..." -ForegroundColor Yellow
python -m venv $venvPath --clear

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR: Impossible de créer l'environnement virtuel" -ForegroundColor Red
    Write-Host "Vérifiez que Python est correctement installé: python --version" -ForegroundColor Yellow
    exit 1
}
Write-Host "Environnement virtuel créé!" -ForegroundColor Green

# Activer l'environnement virtuel
if (-Not (Test-Path $activateScript)) {
    Write-Host "ERREUR: Script d'activation non trouvé" -ForegroundColor Red
    exit 1
}

Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Yellow
& $activateScript

# Mettre à jour pip en premier
Write-Host "Mise à jour de pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR: Échec de la mise à jour de pip" -ForegroundColor Red
    exit 1
}

# Installer setuptools et wheel
Write-Host "Installation de setuptools et wheel..." -ForegroundColor Yellow
python -m pip install --upgrade setuptools wheel --trusted-host pypi.org --trusted-host files.pythonhosted.org

# Installer les dépendances depuis requirements.txt
if (Test-Path $requirementsPath) {
    Write-Host "Installation des dépendances depuis requirements.txt..." -ForegroundColor Yellow
    python -m pip install -r $requirementsPath --trusted-host pypi.org --trusted-host files.pythonhosted.org
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERREUR: Installation des dépendances échouée" -ForegroundColor Red
        Write-Host "Vérifiez le contenu de requirements.txt" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Dépendances installées!" -ForegroundColor Green
} else {
    Write-Host "ATTENTION: requirements.txt non trouvé dans: $requirementsPath" -ForegroundColor Yellow
    Write-Host "Installation manuelle de Rasa..." -ForegroundColor Yellow
    python -m pip install rasa --trusted-host pypi.org --trusted-host files.pythonhosted.org
}

# Vérifier l'installation de Rasa
Write-Host "`nVérification de l'installation de Rasa..." -ForegroundColor Yellow
$rasaCheck = python -m rasa --version 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host " Rasa installé avec succès!" -ForegroundColor Green
    Write-Host $rasaCheck -ForegroundColor Cyan
} else {
    Write-Host "ERREUR: Rasa n'est pas installé correctement" -ForegroundColor Red
    Write-Host "Sortie: $rasaCheck" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n=== Environnement Rasa prêt ===" -ForegroundColor Green
Write-Host "Pour activer l'environnement dans une nouvelle session:" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White