import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset, ActiveLoop, FollowupAction
from difflib import SequenceMatcher
import re
from datetime import datetime
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Import the backend service
from actions.services.ddr_service import get_backend_service

# ==================== CORRECTION 4 : Extraction et conservation de la justification ====================
class ActionVerificationJustification(Action):
    """Extraction proactive de la justification SANS réinitialisation"""
    
    def name(self) -> Text:
        return "verification_justification"
    
    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        
        justification = tracker.get_slot("justification")
        user_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        logger.info(f"🔍 verification_justification - Message: '{user_message[:100]}...'")
        logger.info(f"   Slot justification actuel: '{justification}'")
        
        # ✅ CORRECTION 1 : Si la justification existe déjà, NE PAS LA TOUCHER
        if justification and len(str(justification).strip()) >= 15:
            logger.info(f"✅ Justification déjà validée: '{justification[:50]}...'")
            return []  # Ne rien faire, garder la valeur existante
        
        # ✅ CORRECTION 2 : Chercher dans les entités EN PREMIER
        if not justification:
            for entity in entities:
                if entity.get('entity') == 'justification':
                    justification = entity.get('value', '').strip()
                    logger.info(f"✅ Justification trouvée dans les entités: '{justification[:50]}...'")
                    if len(justification) >= 15:
                        break
        
        # ✅ CORRECTION 3 : Extraire depuis le message avec patterns AMÉLIORÉS
        if not justification or len(justification) < 15:
            justification = self._extraire_justification_du_message(user_message)
        
        # Si toujours vide, retourner liste VIDE (pas de réinitialisation)
        if not justification:
            logger.info("⚠️ Aucune justification trouvée")
            return []
        
        # ✅ CORRECTION 4 : Nettoyage minimal (ne pas supprimer "Ce renfort...")
        justification_clean = self._nettoyer_justification(justification)
        
        if not justification_clean or len(justification_clean) < 15:
            dispatcher.utter_message(
                text="❌ La justification doit contenir au moins 15 caractères. "
                     "Veuillez fournir une justification détaillée."
            )
            return []
        
        logger.info(f"✅ Justification validée: '{justification_clean[:80]}...'")
        return [SlotSet("justification", justification_clean)]
    
    def _extraire_justification_du_message(self, message: str) -> Optional[str]:
        """
        ✅ CORRECTION : Extraction avec patterns ÉLARGIS
        """
        
        if not message or len(message) < 20:
            return None
        
        message_lower = message.lower()
        
        # ✅ PATTERNS AMÉLIORÉS (ordre de priorité)
        patterns_explicites = [
            # Pattern 1 : "La justification est la suivante : XXX"
            r'(?:la\s+)?justification\s+(?:est\s+)?(?:la\s+)?suivante\s*[:\s]+(.{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
            
            # Pattern 2 : "justification : XXX" ou "justification: XXX"
            r'justification\s*:\s*(.{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
            
            # Pattern 3 : "justifié par XXX" ou "motivé par XXX"
            r'(?:justifi[eé]e?|motiv[eé]e?)\s+(?:par|:)\s*(.{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
            
            # ✅ Pattern 4 : "Ce renfort permettra..." (CAS DU LOG)
            r'(?:ce\s+(?:renfort|poste|recrutement)|cette\s+(?:personne|embauche))\s+permettra\s+(?:de\s+)?(.{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
            
            # Pattern 5 : "pour XXX" ou "afin de XXX" (avec verbe)
            r'(?:pour|afin\s+de)\s+([a-zàâäéèêëïîôöùûüÿœæç\s]{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
            
            # Pattern 6 : "car XXX" ou "parce que XXX"
            r'(?:car|parce\s+que|à\s+cause\s+de)\s+(.{15,800}?)(?=\s*(?:objectif|exploitation|direction|dotation|pièce|$))',
        ]
        
        for pattern in patterns_explicites:
            match = re.search(pattern, message_lower, re.IGNORECASE | re.DOTALL)
            if match:
                justification = match.group(1).strip()
                
                # ✅ Reconstruire avec la casse originale
                start_pos = match.start(1)
                end_pos = match.end(1)
                justification_original = message[start_pos:end_pos].strip()
                
                if len(justification_original) >= 15:
                    logger.info(f"✅ Pattern trouvé: '{justification_original[:80]}...'")
                    return justification_original
        
        return None
    
    def _extraire_depuis_position(self, message: str, start_pos: int) -> str:
        """Extrait le texte depuis start_pos jusqu'au prochain marqueur"""
        
        marqueurs_fin = [
            r"objectif\s+\d+",
            r"(?:le\s+|l')?objectif",
            r"exploitation\s*:",
            r"direction\s*:",
            r"dotation\s*:",
            r"pièce\s+jointe",
        ]

        texte_apres = message[start_pos:]
        fin_position = len(texte_apres)

        for marqueur in marqueurs_fin:
            match = re.search(marqueur, texte_apres, re.IGNORECASE)
            if match and match.start() < fin_position:
                fin_position = match.start()

        justification = texte_apres[:fin_position].strip()
        justification = re.sub(r'\.+','.', justification)
        
        return justification
    
    def _nettoyer_justification(self, justification: str) -> str:
        """
        ✅ CORRECTION : Nettoyage MINIMAL (ne pas supprimer le contenu utile)
        """
        
        if not justification:
            return ""
        
        # Normaliser les espaces multiples
        justification = re.sub(r'\s+', ' ', justification)
        
        # ✅ CORRECTION : NE PAS supprimer "Ce renfort permettra"
        # On supprime UNIQUEMENT les préfixes métadonnées
        prefixes_a_supprimer = [
            r'^(?:la\s+)?justification\s+(?:est\s+)?(?:la\s+)?suivante\s*[:\s]*',
            r'^justifi[eé]e?\s+(?:par|:)\s*',
            r'^motiv[eé]e?\s+(?:par|:)\s*',
            r'^justification\s*:\s*',
        ]
        
        for prefix in prefixes_a_supprimer:
            justification = re.sub(prefix, '', justification, flags=re.IGNORECASE)
        
        justification = justification.strip()
        
        # Capitaliser la première lettre
        if justification:
            justification = justification[0].upper() + justification[1:]
        
        # Ajouter un point final si absent
        if justification and not justification.endswith(('.', '!', '?')):
            justification += '.'
        
        return justification