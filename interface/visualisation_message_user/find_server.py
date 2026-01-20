"""
Script pour trouver le nom correct de votre serveur SQL Server
"""

import pyodbc
import socket

print("="*60)
print("🔍 RECHERCHE DU SERVEUR SQL SERVER")
print("="*60)

print("\n1️⃣ INFORMATIONS SYSTÈME")
print("-"*60)
hostname = socket.gethostname()
print(f"Nom de la machine: {hostname}")

print("\n2️⃣ DRIVERS ODBC DISPONIBLES")
print("-"*60)
drivers = pyodbc.drivers()
for driver in drivers:
    print(f"   - {driver}")

print("\n3️⃣ TENTATIVES DE CONNEXION")
print("-"*60)

# Liste des serveurs possibles à tester
servers_to_test = [
    'localhost',
    '127.0.0.1',
    f'{hostname}',
    f'{hostname}\\SQLEXPRESS',
    'localhost\\SQLEXPRESS',
    '(local)',
    '(local)\\SQLEXPRESS',
    '.\\SQLEXPRESS',
    'DESKTOP-\\SQLEXPRESS',  # Sera complété
]

# Essayer d'ajouter des variantes avec le nom de la machine
if hostname:
    servers_to_test.extend([
        f'{hostname}\\MSSQLSERVER',
        f'.\\{hostname}',
    ])

database = 'MouvPersoDatabase'

print(f"\nTest de connexion à la base '{database}'...\n")

successful_connections = []

for server in servers_to_test:
    try:
        print(f"Test: {server:40} ", end='')
        
        conn_str = (
            f"DRIVER={{SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
        )
        
        conn = pyodbc.connect(conn_str, timeout=3)
        print("✅ SUCCÈS!")
        successful_connections.append(server)
        conn.close()
        
    except pyodbc.Error as e:
        if "n'existe pas" in str(e) or "does not exist" in str(e):
            print("❌ Serveur introuvable")
        elif "refusé" in str(e) or "denied" in str(e):
            print("⚠️ Accès refusé")
        elif "n'a pas pu être trouvée" in str(e):
            print("⚠️ Base de données introuvable")
        else:
            print(f"❌ {str(e)[:50]}...")
    except Exception as e:
        print(f"❌ Erreur: {str(e)[:30]}...")

print("\n" + "="*60)
print("📊 RÉSULTATS")
print("="*60)

if successful_connections:
    print("\n✅ CONNEXIONS RÉUSSIES:")
    for server in successful_connections:
        print(f"\n   Server: {server}")
        print(f"   Utilisez cette configuration dans app.py:")
        print(f"   ")
        print(f"   DB_CONFIG = {{")
        print(f"       'server': '{server}',")
        print(f"       'database': '{database}',")
        print(f"       'driver': '{{SQL Server}}',")
        print(f"       'trusted_connection': 'yes'")
        print(f"   }}")
else:
    print("\n❌ AUCUNE CONNEXION RÉUSSIE")
    print("\n💡 SOLUTIONS POSSIBLES:")
    print("-"*60)
    print("1. Vérifiez que SQL Server est démarré:")
    print("   - Ouvrez 'Services' (services.msc)")
    print("   - Cherchez 'SQL Server (SQLEXPRESS)' ou 'SQL Server (MSSQLSERVER)'")
    print("   - Vérifiez qu'il est 'En cours d'exécution'")
    
    print("\n2. Trouvez le nom de votre instance SQL Server:")
    print("   - Ouvrez SQL Server Management Studio (SSMS)")
    print("   - Le nom du serveur affiché est celui à utiliser")
    print("   - Exemples courants:")
    print(f"     • {hostname}\\SQLEXPRESS")
    print("     • localhost\\SQLEXPRESS")
    print("     • (local)\\SQLEXPRESS")
    
    print("\n3. Vérifiez que la base 'MouvPerso' existe:")
    print("   - Dans SSMS, vérifiez dans 'Databases'")
    print("   - Si elle n'existe pas, créez-la ou changez le nom dans DB_CONFIG")
    
    print("\n4. Activez TCP/IP pour SQL Server:")
    print("   - Ouvrez 'SQL Server Configuration Manager'")
    print("   - Allez dans 'SQL Server Network Configuration'")
    print("   - Activez 'TCP/IP'")
    print("   - Redémarrez SQL Server")

print("\n" + "="*60)
print("✅ DIAGNOSTIC TERMINÉ")
print("="*60)