from typing import Any, Text, Dict, List, Optional
import requests
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class DmoeService:
    """Service pour la gestion des demandes DMOE"""
    
    def __init__(self):
        self.base_url = os.getenv("BACKEND_URL", "http://localhost:8000/api")
        self.timeout = 30
        
    def create_demande(self, demande_data: Dict[Text, Any]) -> Optional[Dict[Text, Any]]:
        """
        Crée une nouvelle demande DMOE via l'API
        
        Args:
            demande_data: Données de la demande DMOE
            
        Returns:
            Dict contenant la réponse de l'API ou None en cas d'erreur
        """
        try:
            url = f"{self.base_url}/demandes"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            logger.info(f"📤 Envoi demande DMOE vers: {url}")
            logger.info(f"📋 Données: {demande_data}")
            
            response = requests.post(
                url,
                json=demande_data,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 201:
                logger.info(f"✅ Demande DMOE créée avec succès - Status: {response.status_code}")
                return response.json()
            else:
                logger.error(f"❌ Erreur création demande DMOE - Status: {response.status_code}")
                logger.error(f"❌ Response: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout lors de la création de la demande DMOE")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("❌ Erreur de connexion lors de la création de la demande DMOE")
            return None
        except Exception as e:
            logger.error(f"❌ Exception lors de la création de la demande DMOE: {e}")
            return None
    
    def upload_file_from_metadata(self, attachment_metadata: Dict[Text, Any]) -> Optional[str]:
        """
        Upload un fichier à partir des métadonnées
        
        Args:
            attachment_metadata: Métadonnées du fichier
            
        Returns:
            Nom du fichier uploadé ou None en cas d'erreur
        """
        try:
            # Pour l'instant, on utilise le même service que DDR
            # Cette méthode peut être étendue pour gérer les spécificités DMOE
            from .ddr_service import get_backend_service
            backend = get_backend_service()
            return backend.upload_file_from_metadata(attachment_metadata)
            
        except Exception as e:
            logger.error(f"❌ Erreur upload fichier DMOE: {e}")
            return None

# Instance globale du service
_dmoe_service = None

def get_dmoe_service() -> DmoeService:
    """Retourne l'instance du service DMOE"""
    global _dmoe_service
    if _dmoe_service is None:
        _dmoe_service = DmoeService()
    return _dmoe_service