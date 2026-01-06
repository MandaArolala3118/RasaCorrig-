import sys
from pathlib import Path
from typing import Optional, Dict

# Ajouter le répertoire racine du projet au PYTHONPATH
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent  # Remonte à Rasa4/
sys.path.insert(0, str(project_root))

from actions.services.ddr_service import get_backend_service


class DemandeSearchService:
    """
    Service de recherche de demandes DDR
    
    Cette classe fournit des méthodes pour rechercher et récupérer
    des demandes DDR depuis le backend.
    """
    
    def __init__(self):
        """Initialise le service de recherche avec l'instance du backend"""
        self.service = get_backend_service()
    
    def search_by_id(self, demande_id: int) -> Optional[Dict]:
        """
        Recherche une demande DDR par son ID
        
        Args:
            demande_id (int): L'identifiant de la demande à rechercher
            
        Returns:
            Optional[Dict]: Les données de la demande si elle existe, None sinon
            
        Example:
            >>> searcher = DemandeSearchService()
            >>> result = searcher.search_by_id(123)
            >>> if result:
            >>>     print(f"Demande trouvée: {result.get('NumeroDemande')}")
            >>> else:
            >>>     print("Demande introuvable")
        """
        try:
            # Appeler la méthode pour récupérer la demande
            demande = self.service.get_demande_by_id(demande_id)
            
            # Retourner le résultat (sera None si la demande n'existe pas)
            return demande
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche de la demande {demande_id}: {e}")
            return None
    
    def search_with_details(self, demande_id: int) -> Optional[Dict]:
        """
        Recherche une demande DDR par son ID avec tous les détails associés
        (objectifs, dotations, compléments, etc.)
        
        Args:
            demande_id (int): L'identifiant de la demande à rechercher
            
        Returns:
            Optional[Dict]: Les données complètes de la demande si elle existe, None sinon
            
        Example:
            >>> searcher = DemandeSearchService()
            >>> result = searcher.search_with_details(123)
            >>> if result:
            >>>     print(f"Nombre d'objectifs: {len(result.get('objectifs', []))}")
            >>> else:
            >>>     print("Demande introuvable")
        """
        try:
            # Appeler la méthode pour récupérer la demande avec détails
            demande = self.service.get_demande_with_details(demande_id)
            
            # Retourner le résultat enrichi
            return demande
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche détaillée de la demande {demande_id}: {e}")
            return None
    
    def display_basic_info(self, demande_id: int) -> None:
        """
        Affiche les informations de base d'une demande
        
        Args:
            demande_id (int): L'identifiant de la demande à afficher
        """
        print(f"\n🔍 Recherche de la demande ID: {demande_id}")
        result = self.search_by_id(demande_id)
        
        if result:
            print(f"✅ Demande trouvée!")
            print(f"   Numéro: {result.get('NumeroDemande', 'N/A')}")
            print(f"   Date création: {result.get('DateCreation', 'N/A')}")
            print(f"   Statut: {result.get('IdStatut', 'N/A')}")
        else:
            print(f"❌ Aucune demande trouvée avec l'ID {demande_id}")
    
    def display_detailed_info(self, demande_id: int) -> None:
        """
        Affiche les informations détaillées d'une demande
        
        Args:
            demande_id (int): L'identifiant de la demande à afficher
        """
        print(f"\n🔍 Recherche détaillée de la demande ID: {demande_id}")
        detailed_result = self.search_with_details(demande_id)
        if detailed_result:
            print(f"✅ Demande trouvée avec détails!")
            print(f"   Status: {detailed_result.get('StatutId', 'N/A')}")
        else:
            print(f"❌ Aucune demande trouvée avec l'ID {demande_id}")


# ==================== EXEMPLE D'UTILISATION ====================
if __name__ == "__main__":
    print("=" * 60)
    print("Test de recherche de demande DDR")
    print("=" * 60)
    
    # Créer une instance du service
    searcher = DemandeSearchService()
    
    # Test avec un ID de demande
    test_id = 1313
    
    # Afficher les informations de base
    searcher.display_basic_info(test_id)
    
    print("\n" + "=" * 60)
    
    # Afficher les informations détaillées
    searcher.display_detailed_info(test_id)