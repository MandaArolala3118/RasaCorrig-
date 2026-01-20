@echo off
echo ========================================
echo MouvPerso - Visualiseur de Conversations
echo ========================================
echo.

REM Vérifier si Python est installé
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installé ou n'est pas dans le PATH
    echo Téléchargez Python depuis https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Vérification de Python... OK
echo.

REM Vérifier si les dépendances sont installées
pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo [2/3] Installation des dépendances...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERREUR: Impossible d'installer les dépendances
        pause
        exit /b 1
    )
) else (
    echo [2/3] Dépendances déjà installées... OK
)
echo.

echo [3/3] Démarrage de l'application...
echo.
echo ========================================
echo L'application est accessible sur:
echo http://localhost:5002
echo ========================================
echo.
echo Appuyez sur Ctrl+C pour arrêter
echo.

python app.py

pause