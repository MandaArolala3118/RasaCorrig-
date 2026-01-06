"""
Script de test pour diagnostiquer le problème de recherche de flux
Teste le comportement de FluxSearchService sans Rasa
"""

import sys
from pathlib import Path

# Ajouter le répertoire racine du projet au PYTHONPATH
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # Ajuster selon votre structure
sys.path.insert(0, str(project_root))

from .Flux_calcul import FluxSearchService


def print_separator(title=""):
    """Affiche un séparateur visuel"""
    print("\n" + "="*80)
    if title:
        print(f"  {title}")
        print("="*80)
    print()


def test_1_recherche_tous_flux_manda():
    """Test 1: Afficher tous les flux contenant 'Manda Arolala'"""
    print_separator("TEST 1: Recherche tous les flux contenant 'Manda Arolala'")
    
    flux_service = FluxSearchService()
    all_flux = flux_service.get_all_flux()
    
    found_flux = []
    search_term = "Manda Arolala"
    
    print(f"🔍 Recherche de '{search_term}' dans tous les flux...")
    print(f"📊 Total flux dans la base: {len(all_flux)}\n")
    
    for flux in all_flux:
        flux_id = flux.get('IdFlux')
        flux_nom = flux.get('NomFluxMouvement')
        flux_type = flux.get('TypeFlux', 'N/A')
        
        # Chercher dans tous les validateurs (V1 à V5)
        for i in range(1, 6):
            username = flux.get(f'V{i}', '')
            full_name = flux.get(f'V{i}UserName', '')
            
            if search_term.lower() in full_name.lower():
                found_flux.append({
                    'flux': flux,
                    'position': f'V{i}',
                    'username': username,
                    'full_name': full_name
                })
                break  # Un seul match par flux suffit
    
    if found_flux:
        print(f"✅ {len(found_flux)} flux trouvé(s) contenant '{search_term}':\n")
        for idx, item in enumerate(found_flux, 1):
            flux = item['flux']
            print(f"{idx}. Flux: {flux.get('NomFluxMouvement')}")
            print(f"   ID: {flux.get('IdFlux')}")
            print(f"   Type: {flux.get('TypeFlux', 'N/A')}")
            print(f"   Position: {item['position']}")
            print(f"   Username: {item['username']}")
            print(f"   Full Name: {item['full_name']}")
            print(f"\n   Tous les validateurs de ce flux:")
            for i in range(1, 6):
                v_username = flux.get(f'V{i}')
                v_fullname = flux.get(f'V{i}UserName')
                if v_username and v_username != 'None':
                    print(f"      V{i}: {v_fullname} ({v_username})")
            print()
    else:
        print(f"❌ Aucun flux trouvé contenant '{search_term}'")
    
    return found_flux


def test_2_recherche_ordered_threshold_100():
    """Test 2: Recherche avec search_by_ordered_validators, threshold=100, typeflux='AUTRE'"""
    print_separator("TEST 2: Recherche avec threshold=100 et typeflux='AUTRE'")
    
    flux_service = FluxSearchService(default_threshold=100)
    validators = ["Manda Arolala ANDRIANINA"]
    
    print(f"🔍 Recherche ordonnée avec:")
    print(f"   Validateurs: {validators}")
    print(f"   Threshold: 100")
    print(f"   Search type: full_name")
    print(f"   TypeFlux: AUTRE\n")
    
    result = flux_service.search_by_ordered_validators(
        validators=validators,
        threshold=100,
        limit=5,
        search_type='full_name',
        typeflux='AUTRE'
    )
    
    if result:
        if isinstance(result, dict):
            flux = result.get('flux', result)
            print(f"✅ Flux trouvé:")
            print(f"   Nom: {flux.get('NomFluxMouvement')}")
            print(f"   ID: {flux.get('IdFlux')}")
            print(f"   Type: {flux.get('TypeFlux', 'N/A')}")
        elif isinstance(result, list):
            print(f"📋 {len(result)} flux trouvés:")
            for idx, item in enumerate(result, 1):
                flux = item.get('flux', item)
                score = item.get('match_score', 'N/A')
                print(f"   {idx}. {flux.get('NomFluxMouvement')} (Score: {score}%, Type: {flux.get('TypeFlux', 'N/A')})")
    else:
        print("❌ Aucun flux trouvé avec ces paramètres")
    
    return result


def test_3_recherche_ordered_threshold_80():
    """Test 3: Recherche avec threshold=80, sans filtrage typeflux"""
    print_separator("TEST 3: Recherche avec threshold=80 et typeflux=None")
    
    flux_service = FluxSearchService(default_threshold=80)
    validators = ["Manda Arolala ANDRIANINA"]
    
    print(f"🔍 Recherche ordonnée avec:")
    print(f"   Validateurs: {validators}")
    print(f"   Threshold: 80")
    print(f"   Search type: full_name")
    print(f"   TypeFlux: None (tous les types)\n")
    
    result = flux_service.search_by_ordered_validators(
        validators=validators,
        threshold=80,
        limit=5,
        search_type='full_name',
        typeflux=None
    )
    
    if result:
        if isinstance(result, dict):
            flux = result.get('flux', result)
            print(f"✅ Flux trouvé:")
            print(f"   Nom: {flux.get('NomFluxMouvement')}")
            print(f"   ID: {flux.get('IdFlux')}")
            print(f"   Type: {flux.get('TypeFlux', 'N/A')}")
        elif isinstance(result, list):
            print(f"📋 {len(result)} flux trouvés:")
            for idx, item in enumerate(result, 1):
                flux = item.get('flux', item)
                score = item.get('match_score', 'N/A')
                print(f"   {idx}. {flux.get('NomFluxMouvement')} (Score: {score}%, Type: {flux.get('TypeFlux', 'N/A')})")
    else:
        print("❌ Aucun flux trouvé avec ces paramètres")
    
    return result


def test_4_recherche_ordered_nom_partiel():
    """Test 4: Recherche avec seulement 'Manda Arolala' (nom partiel)"""
    print_separator("TEST 4: Recherche avec nom partiel 'Manda Arolala'")
    
    flux_service = FluxSearchService(default_threshold=80)
    validators = ["Manda Arolala"]  # Sans le nom de famille
    
    print(f"🔍 Recherche ordonnée avec:")
    print(f"   Validateurs: {validators}")
    print(f"   Threshold: 80")
    print(f"   Search type: full_name")
    print(f"   TypeFlux: None\n")
    
    result = flux_service.search_by_ordered_validators(
        validators=validators,
        threshold=80,
        limit=5,
        search_type='full_name',
        typeflux=None
    )
    
    if result:
        if isinstance(result, dict):
            flux = result.get('flux', result)
            print(f"✅ Flux trouvé:")
            print(f"   Nom: {flux.get('NomFluxMouvement')}")
            print(f"   ID: {flux.get('IdFlux')}")
            print(f"   Type: {flux.get('TypeFlux', 'N/A')}")
        elif isinstance(result, list):
            print(f"📋 {len(result)} flux trouvés:")
            for idx, item in enumerate(result, 1):
                flux = item.get('flux', item)
                score = item.get('match_score', 'N/A')
                print(f"   {idx}. {flux.get('NomFluxMouvement')} (Score: {score}%, Type: {flux.get('TypeFlux', 'N/A')})")
    else:
        print("❌ Aucun flux trouvé avec ces paramètres")
    
    return result


def test_5_comparaison_normalisation():
    """Test 5: Vérifier la normalisation des noms"""
    print_separator("TEST 5: Comparaison de normalisation")
    
    flux_service = FluxSearchService()
    
    test_cases = [
        ("Manda Arolala", "Manda Arolala ANDRIANINA"),
        ("Manda Arolala", "manda arolala andrianina"),
        ("Manda Arolala ANDRIANINA", "Manda Arolala ANDRIANINA"),
    ]
    
    print("🔍 Test de normalisation des noms:\n")
    
    for search_term, db_value in test_cases:
        normalized_search = flux_service.normalize_text(search_term)
        normalized_db = flux_service.normalize_text(db_value)
        
        print(f"Recherche: '{search_term}'")
        print(f"  → Normalisé: '{normalized_search}'")
        print(f"Base de données: '{db_value}'")
        print(f"  → Normalisé: '{normalized_db}'")
        print(f"  → Match exact: {normalized_search == normalized_db}")
        print(f"  → Contenu dans: {normalized_search in normalized_db}")
        
        # Calcul du score fuzzy
        from rapidfuzz import fuzz
        ratio_score = fuzz.ratio(normalized_search, normalized_db)
        partial_score = fuzz.partial_ratio(normalized_search, normalized_db)
        
        print(f"  → Score ratio: {ratio_score}%")
        print(f"  → Score partial: {partial_score}%")
        print()


def main():
    """Fonction principale pour exécuter tous les tests"""
    print("\n" + "🧪 DIAGNOSTIC COMPLET DE LA RECHERCHE DE FLUX 🧪".center(80))
    
    try:
        # Test 1: Voir tous les flux contenant Manda Arolala
        found_flux = test_1_recherche_tous_flux_manda()
        
        # Test 2: Recherche avec les paramètres actuels du code
        result_2 = test_2_recherche_ordered_threshold_100()
        
        # Test 3: Recherche avec threshold plus permissif
        result_3 = test_3_recherche_ordered_threshold_80()
        
        # Test 4: Recherche avec nom partiel
        result_4 = test_4_recherche_ordered_nom_partiel()
        
        # Test 5: Vérifier la normalisation
        test_5_comparaison_normalisation()
        
        # Résumé final
        print_separator("RÉSUMÉ DES TESTS")
        print(f"Test 1 (Recherche manuelle): {len(found_flux)} flux trouvé(s)")
        print(f"Test 2 (threshold=100, typeflux='AUTRE'): {'✅ Trouvé' if result_2 else '❌ Non trouvé'}")
        print(f"Test 3 (threshold=80, typeflux=None): {'✅ Trouvé' if result_3 else '❌ Non trouvé'}")
        print(f"Test 4 (nom partiel, threshold=80): {'✅ Trouvé' if result_4 else '❌ Non trouvé'}")
        
        print("\n💡 CONCLUSION:")
        if found_flux and not result_2:
            flux = found_flux[0]['flux']
            flux_type = flux.get('TypeFlux', 'N/A')
            print(f"   • Le flux existe dans la base (Type: {flux_type})")
            if flux_type != 'AUTRE':
                print(f"   ⚠️  PROBLÈME: TypeFlux est '{flux_type}', pas 'AUTRE'")
                print(f"   → Solution: Utiliser typeflux=None ou typeflux='{flux_type}'")
            if not result_3:
                print(f"   ⚠️  PROBLÈME: Même sans filtrage TypeFlux, le flux n'est pas trouvé")
                print(f"   → Vérifier la logique de matching dans search_by_ordered_validators")
        
    except Exception as e:
        print(f"\n❌ ERREUR lors de l'exécution des tests: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()