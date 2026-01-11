#!/usr/bin/env python3
"""
Script de test pour vérifier la correction de la recherche de flux
Teste la conversion de nom complet → username dans search_by_strict_validator_sequence
"""

import sys
from pathlib import Path

# Ajouter le répertoire racine du projet au PYTHONPATH
current_file = Path(__file__).resolve()
project_root = current_file.parent
sys.path.insert(0, str(project_root))

from actions.services.Calculate.Flux_calcul import FluxSearchService
from actions.services.Calculate.RechercheNom import UserSearchService

def test_user_search():
    """Test la recherche d'utilisateurs"""
    print("=" * 80)
    print("TEST 1: Recherche d'utilisateurs")
    print("=" * 80)
    
    user_service = UserSearchService()
    
    # Test avec le nom complet
    print("\n🔍 Recherche de 'Manda Arolala'...")
    results = user_service.search_user_by_name("Manda Arolala", max_results=5)
    
    if results:
        for user in results[:3]:
            print(f"   ✅ Trouvé: {user.get('FullName')} (UserName: {user.get('UserName')}, Matricule: {user.get('Matricule')})")
    else:
        print("   ❌ Aucun utilisateur trouvé")
    
    return results

def test_flux_search():
    """Test la recherche stricte de flux"""
    print("\n" + "=" * 80)
    print("TEST 2: Recherche stricte de flux avec nom complet")
    print("=" * 80)
    
    flux_service = FluxSearchService(default_threshold=85, default_limit=5)
    
    # Test avec le nom complet (ce qui était le problème)
    print("\n🔍 Recherche stricte avec le nom complet 'Manda Arolala'...")
    result = flux_service.search_by_strict_validator_sequence(
        validators=["Manda Arolala"],
        threshold=85,
        limit=5,
        search_type='full_name',
        typeflux='AUTRE'
    )
    
    if result:
        if isinstance(result, dict):
            print(f"\n✅ Flux trouvé (unique):")
            print(f"   - Nom: {result.get('flux', result).get('NomFluxMouvement')}")
            print(f"   - ID: {result.get('flux', result).get('IdFlux')}")
        elif isinstance(result, list):
            print(f"\n✅ {len(result)} flux trouvé(s):")
            for r in result:
                flux = r.get('flux', r)
                print(f"   - {flux.get('NomFluxMouvement')} (ID: {flux.get('IdFlux')})")
    else:
        print("   ❌ Aucun flux trouvé")
    
    return result

def test_flux_search_username():
    """Test la recherche stricte de flux avec username"""
    print("\n" + "=" * 80)
    print("TEST 3: Recherche stricte de flux avec username")
    print("=" * 80)
    
    flux_service = FluxSearchService(default_threshold=85, default_limit=5)
    
    # Test avec le username (pour comparaison)
    print("\n🔍 Recherche stricte avec le username 'administrateur'...")
    result = flux_service.search_by_strict_validator_sequence(
        validators=["administrateur"],
        threshold=85,
        limit=5,
        search_type='username',
        typeflux='AUTRE'
    )
    
    if result:
        if isinstance(result, dict):
            print(f"\n✅ Flux trouvé (unique):")
            print(f"   - Nom: {result.get('flux', result).get('NomFluxMouvement')}")
            print(f"   - ID: {result.get('flux', result).get('IdFlux')}")
        elif isinstance(result, list):
            print(f"\n✅ {len(result)} flux trouvé(s):")
            for r in result:
                flux = r.get('flux', r)
                print(f"   - {flux.get('NomFluxMouvement')} (ID: {flux.get('IdFlux')})")
    else:
        print("   ❌ Aucun flux trouvé")
    
    return result

def main():
    print("\n" + "=" * 80)
    print("🧪 TESTS DE CORRECTION DE RECHERCHE DE FLUX")
    print("=" * 80)
    
    try:
        # Test 1: Recherche d'utilisateurs
        user_results = test_user_search()
        
        # Test 2: Recherche stricte avec nom complet (CE QUI ÉTAIT CASSÉ)
        flux_results_fullname = test_flux_search()
        
        # Test 3: Recherche stricte avec username (ce qui devrait fonctionner)
        flux_results_username = test_flux_search_username()
        
        # Résumé
        print("\n" + "=" * 80)
        print("📊 RÉSUMÉ")
        print("=" * 80)
        
        print(f"\n1. Utilisateurs trouvés: {'✅ OUI' if user_results else '❌ NON'}")
        print(f"2. Flux trouvé avec nom complet: {'✅ OUI' if flux_results_fullname else '❌ NON'}")
        print(f"3. Flux trouvé avec username: {'✅ OUI' if flux_results_username else '❌ NON'}")
        
        if flux_results_fullname and flux_results_username:
            print("\n✅ ✅ ✅ CORRECTION RÉUSSIE! Les deux approches trouvent maintenant le flux!")
        elif flux_results_fullname or flux_results_username:
            print("\n⚠️  Au moins une des deux approches fonctionne")
        else:
            print("\n❌ Aucune approche ne fonctionne - vérifier la base de données")
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
