# Solution 1: Désactiver les warnings SSL (DEV SEULEMENT!)
# Ajouter au début de votre actions.py ou endpoints.yml

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Solution 2: Ou configurer les requests pour ignorer SSL
import requests
requests.packages.urllib3.disable_warnings()

# Solution 3: Dans endpoints.yml, ajoutez verify_ssl: false
"""
action_endpoint:
  url: "http://localhost:5055/webhook"
  verify_ssl: false  # DEV SEULEMENT!
"""

# Solution 4: Pour production, installer le certificat
"""
# Windows
pip install certifi
python -m certifi

# Ou pointer vers le certificat
import os
os.environ['REQUESTS_CA_BUNDLE'] = '/path/to/certificate.pem'
"""

# Solution 5: Configurer Sentry (le service qui génère les warnings)
# Dans votre code Rasa, avant l'import:
import os
os.environ['SENTRY_DSN'] = ''  # Désactive Sentry en dev

# OU créer un fichier .sentryclirc à la racine:
"""
[auth]
token=

[defaults]
url=
org=
project=
"""