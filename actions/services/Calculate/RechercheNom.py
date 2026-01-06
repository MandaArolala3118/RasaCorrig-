import sys
from pathlib import Path
from typing import Optional, List, Dict
import unicodedata
import re

# Ajouter le répertoire racine du projet au PYTHONPATH
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent  # Remonte à Rasa4/
sys.path.insert(0, str(project_root))

from actions.services.ddr_service import get_backend_service


class UserSearchService:
    """
    Service de recherche intelligente d'utilisateurs
    
    Cette classe fournit des méthodes pour rechercher des utilisateurs
    dans la base de données avec une recherche flexible (insensible à la casse,
    aux accents, et à l'ordre des mots).
    """
    
    def __init__(self):
        """Initialise le service de recherche avec l'instance du backend"""
        self.service = get_backend_service()
        self._users_cache: Optional[List[Dict]] = None
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalise un texte en supprimant les accents et en convertissant en minuscules
        
        Args:
            text (str): Le texte à normaliser
            
        Returns:
            str: Le texte normalisé
            
        Example:
            >>> UserSearchService.normalize_text("Éléonore")
            'eleonore'
        """
        if not text:
            return ""
        
        # Supprimer les accents
        text = ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
        
        # Convertir en minuscules
        return text.lower()
    
    def get_all_users(self, force_refresh: bool = False) -> List[Dict]:
        """
        Récupère tous les utilisateurs (avec mise en cache)
        
        Args:
            force_refresh (bool): Force le rechargement des données
            
        Returns:
            List[Dict]: Liste de tous les utilisateurs
        """
        if self._users_cache is None or force_refresh:
            try:
                self._users_cache = self.service.get_all_user_details()
            except Exception as e:
                print(f"❌ Erreur lors de la récupération des utilisateurs: {e}")
                return []
        
        return self._users_cache or []
    
    def search_user_by_name(
        self, 
        search_query: str, 
        max_results: int = 10
    ) -> List[Dict]:
        """
        Recherche intelligente d'utilisateurs par nom
        
        La recherche est insensible à:
        - La casse (majuscules/minuscules)
        - Les accents
        - L'ordre des mots
        
        Args:
            search_query (str): Le nom ou partie du nom à rechercher
            max_results (int): Nombre maximum de résultats à retourner
            
        Returns:
            List[Dict]: Liste des utilisateurs correspondants, triés par pertinence
            
        Example:
            >>> searcher = UserSearchService()
            >>> results = searcher.search_user_by_name("abel rakoto")
            >>> for user in results:
            >>>     print(user['FullName'])
        """
        if not search_query or not search_query.strip():
            return []
        
        # Récupérer tous les utilisateurs
        all_users = self.get_all_users()
        
        if not all_users:
            return []
        
        # Normaliser la requête de recherche
        normalized_query = self.normalize_text(search_query)
        query_words = normalized_query.split()
        
        # Résultats avec score de pertinence
        results_with_score = []
        
        for user in all_users:
            full_name = user.get('FullName', '')
            
            if not full_name:
                continue
            
            # Normaliser le nom complet de l'utilisateur
            normalized_name = self.normalize_text(full_name)
            
            # Calculer le score de correspondance
            score = self._calculate_match_score(normalized_name, query_words)
            
            if score > 0:
                results_with_score.append((user, score))
        
        # Trier par score décroissant
        results_with_score.sort(key=lambda x: x[1], reverse=True)
        
        # Retourner uniquement les utilisateurs (sans le score)
        return [user for user, score in results_with_score[:max_results]]
    
    def _calculate_match_score(self, normalized_name: str, query_words: List[str]) -> int:
        """
        Calcule un score de correspondance entre un nom et une requête
        
        Args:
            normalized_name (str): Le nom normalisé de l'utilisateur
            query_words (List[str]): Les mots de la requête
            
        Returns:
            int: Le score de correspondance (0 = aucune correspondance)
        """
        score = 0
        name_words = normalized_name.split()
        
        # Vérifier si tous les mots de la requête sont présents
        for query_word in query_words:
            word_found = False
            
            for name_word in name_words:
                # Correspondance exacte
                if query_word == name_word:
                    score += 10
                    word_found = True
                    break
                # Correspondance partielle (début du mot)
                elif name_word.startswith(query_word):
                    score += 7
                    word_found = True
                    break
                # Correspondance partielle (contient le mot)
                elif query_word in name_word:
                    score += 5
                    word_found = True
                    break
            
            # Si un mot de la requête n'est pas trouvé, score = 0
            if not word_found:
                return 0
        
        # Bonus si la requête correspond au début du nom
        if normalized_name.startswith(' '.join(query_words)):
            score += 15
        
        return score
    
    def search_user_by_matricule(self, matricule: str) -> Optional[Dict]:
        """
        Recherche un utilisateur par matricule
        
        Args:
            matricule (str): Le matricule à rechercher
            
        Returns:
            Optional[Dict]: L'utilisateur trouvé ou None
            
        Example:
            >>> searcher = UserSearchService()
            >>> user = searcher.search_user_by_matricule("650136")
            >>> if user:
            >>>     print(user['FullName'])
        """
        if not matricule:
            return None
        
        all_users = self.get_all_users()
        
        matricule_normalized = matricule.strip()
        
        for user in all_users:
            user_matricule = user.get('Matricule', '')
            if user_matricule and user_matricule.strip() == matricule_normalized:
                return user
        
        return None
    
    def search_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Recherche un utilisateur par email
        
        Args:
            email (str): L'email à rechercher
            
        Returns:
            Optional[Dict]: L'utilisateur trouvé ou None
        """
        if not email:
            return None
        
        all_users = self.get_all_users()
        
        email_normalized = self.normalize_text(email.strip())
        
        for user in all_users:
            user_email = user.get('Email', '')
            if user_email and self.normalize_text(user_email) == email_normalized:
                return user
        
        return None
    
    def display_user_info(self, user: Dict) -> None:
        """
        Affiche les informations d'un utilisateur de manière formatée
        
        Args:
            user (Dict): Les données de l'utilisateur
        """
        print(f"\n✅ Utilisateur trouvé:")
        print(f"   Nom complet : {user.get('FullName', 'N/A')}")
        print(f"   Email       : {user.get('Email', 'N/A')}")
        print(f"   Poste       : {user.get('Poste', 'N/A')}")
        print(f"   Matricule   : {user.get('Matricule', 'N/A')}")
        print(f"   Username    : {user.get('UserName', 'N/A')}")
    
    def display_search_results(self, results: List[Dict]) -> None:
        """
        Affiche les résultats d'une recherche
        
        Args:
            results (List[Dict]): Liste des utilisateurs trouvés
        """
        if not results:
            print("❌ Aucun utilisateur trouvé")
            return
        
        print(f"\n✅ {len(results)} utilisateur(s) trouvé(s):\n")
        
        for i, user in enumerate(results, 1):
            print(f"{i}. {user.get('FullName', 'N/A')}")
            print(f"   📧 {user.get('Email', 'N/A')}")
            print(f"   🆔 {user.get('Matricule', 'N/A')}")
            print(f"   💼 {user.get('Poste', 'N/A')}")
            print()


# ==================== EXEMPLE D'UTILISATION ====================
if __name__ == "__main__":
    print("=" * 70)
    print("Test de recherche intelligente d'utilisateurs")
    print("=" * 70)
    
    # Créer une instance du service
    searcher = UserSearchService()
    
    # Test 1: Recherche par nom (ordre normal)
    print("\n🔍 Test 1: Recherche 'abel rakoto'")
    results = searcher.search_user_by_name("abel rakoto")
    searcher.display_search_results(results)
    
    # Test 2: Recherche par nom (ordre inversé)
    print("\n" + "=" * 70)
    print("\n🔍 Test 2: Recherche 'rakoto abel' (ordre inversé)")
    results = searcher.search_user_by_name("rakoto abel")
    searcher.display_search_results(results)
    
    # Test 3: Recherche avec accents
    print("\n" + "=" * 70)
    print("\n🔍 Test 3: Recherche 'honoré' (avec accent)")
    results = searcher.search_user_by_name("honoré")
    searcher.display_search_results(results)
    
    # Test 4: Recherche sans accent
    print("\n" + "=" * 70)
    print("\n🔍 Test 4: Recherche 'honore' (sans accent)")
    results = searcher.search_user_by_name("honore")
    searcher.display_search_results(results)
    
    # Test 5: Recherche par matricule
    print("\n" + "=" * 70)
    print("\n🔍 Test 5: Recherche par matricule '650136'")
    user = searcher.search_user_by_matricule("650136")
    if user:
        searcher.display_user_info(user)
    else:
        print("❌ Utilisateur non trouvé")
    
    # Test 6: Recherche par email
    print("\n" + "=" * 70)
    print("\n🔍 Test 6: Recherche par email")
    user = searcher.search_user_by_email("abel.rakotomandimby@castel-afrique.com")
    if user:
        searcher.display_user_info(user)
    else:
        print("❌ Utilisateur non trouvé")