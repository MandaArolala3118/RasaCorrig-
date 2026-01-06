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

def remove_accents(text: str) -> str:
    """Supprime les accents d'une chaîne de caractères"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()


class ActionVerificationHierarchie(Action):
    """Valide la hiérarchie (direction, exploitation) avec fuzzy matching"""
    
    def __init__(self):
        super().__init__()
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_hierarchie"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        events = []
        user_message = tracker.latest_message.get('text', '')
        logger.info(f"🔍 verification_hierarchie - message: '{user_message}'")
        
        # ========== RÉCUPÉRATION DES ENTITÉS NON MAPPÉES ==========
        entities = tracker.latest_message.get('entities', [])
        logger.info(f"📋 Entités extraites pour hiérarchie: {len(entities)}")
        
        # Vérifier la direction
        direction = tracker.get_slot("direction")
        
        # 🆕 Si le slot est vide, chercher dans les entités
        if not direction:
            for entity in entities:
                if entity.get('entity') == 'direction':
                    direction = entity.get('value')
                    logger.info(f"✅ Direction récupérée depuis l'entité: '{direction}'")
                    break
        
        direction_result = self.validate_direction(direction, dispatcher)
        events.extend([SlotSet(k, v) for k, v in direction_result.items()])
        
        # Vérifier l'exploitation
        exploitation = tracker.get_slot("exploitation")
        
        # 🆕 Si le slot est vide, chercher dans les entités
        if not exploitation:
            for entity in entities:
                if entity.get('entity') == 'exploitation':
                    exploitation = entity.get('value')
                    logger.info(f"✅ Exploitation récupérée depuis l'entité: '{exploitation}'")
                    break
        
        exploitation_result = self.validate_exploitation(exploitation, tracker, dispatcher)
        events.extend([SlotSet(k, v) for k, v in exploitation_result.items()])
        
        return events
    
    def validate_direction(self, slot_value: Any, dispatcher) -> Dict[Text, Any]:
        """Valide la direction avec fuzzy matching et récupère l'ID"""
        
        if not slot_value:
            logger.info("⚠️ Direction vide")
            return {"direction": None, "direction_id": None}
        
        directions = self.backend.get_directions() or []
        
        if not directions:
            dispatcher.utter_message(text="❌ Impossible de récupérer la liste des directions.")
            return {"direction": None, "direction_id": None}
        
        user_input = remove_accents(str(slot_value).lower().strip())
        matches = []
        
        logger.info(f"🔍 Recherche direction: '{slot_value}' (normalisé: '{user_input}')")
        
        for d in directions:
            nom_direction = d.get('NomDirection', '')
            direction_id = d.get('IdDir')  # 🆕 Récupérer l'ID
            
            if not nom_direction:
                continue
            
            nom_direction_norm = remove_accents(nom_direction.lower())
            
            # Correspondance exacte
            if user_input == nom_direction_norm:
                logger.info(f"✅ Correspondance exacte: {nom_direction} (ID: {direction_id})")
                return {"direction": nom_direction, "direction_id": direction_id}
            
            # Correspondance partielle
            if user_input in nom_direction_norm or nom_direction_norm in user_input:
                score = len(user_input) / len(nom_direction_norm) if nom_direction_norm else 0
                matches.append((nom_direction, direction_id, score))
                continue
            
            # Fuzzy matching
            ratio = SequenceMatcher(None, user_input, nom_direction_norm).ratio()
            if ratio > 0.6:
                matches.append((nom_direction, direction_id, ratio))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"📊 {len(matches)} correspondances trouvées")
        for match in matches[:3]:
            logger.info(f"  • {match[0]} (ID: {match[1]}, score: {match[2]:.2f})")
        
        if len(matches) == 0:
            direction_list = ','.join([d.get('NomDirection', '') for d in directions[:10] if d.get('NomDirection')])
            dispatcher.utter_message(
                text=f"❌ Direction invalide. Choisissez parmi : {direction_list}"
            )
            return {"direction": None, "direction_id": None}
        
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.2):
            # Une seule correspondance claire
            nom_direction, direction_id, score = matches[0]
            logger.info(f"✅ Direction validée: {nom_direction} (ID: {direction_id})")
            return {"direction": nom_direction, "direction_id": direction_id}
        
        else:
            # Plusieurs correspondances
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs directions correspondent.\n\n" +
                    f"[{', '.join(propositions)}](verification_hierarchie_direction)\n\n" +
                    "💬 Veuillez préciser."
            )
            return {"direction": None, "direction_id": None}
    
    def validate_exploitation(self, slot_value: Any, tracker: Tracker, dispatcher) -> Dict[Text, Any]:
        """Valide l'exploitation avec fuzzy matching et récupère l'ID"""
        
        if not slot_value:
            logger.info("⚠️ Exploitation vide")
            return {"exploitation": None, "exploitation_id": None}
        
        logger.info(f"🔍 Validation exploitation - Valeur: '{slot_value}'")
        
        exploitations = self.backend.get_exploitations() or []
        
        if not exploitations:
            dispatcher.utter_message(text="❌ Impossible de récupérer la liste des exploitations.")
            return {"exploitation": None, "exploitation_id": None}
        
        user_input = remove_accents(str(slot_value).lower().strip())
        matches = []
        
        logger.info(f"🔍 Recherche exploitation: '{slot_value}' (normalisé: '{user_input}')")
        
        for e in exploitations:
            nom_exploitation = e.get('NomExploitation', '')
            exploitation_id = e.get('IdExp')  # 🆕 Récupérer l'ID
            
            if not nom_exploitation:
                continue
            
            nom_exploitation_norm = remove_accents(nom_exploitation.lower())
            
            # Correspondance exacte
            if user_input == nom_exploitation_norm:
                # Vérifier si c'est un code d'exploitation confondu avec effectif
                if re.match(r'^\d{2}', str(slot_value)):
                    current_effectif = tracker.get_slot("effectif")
                    if current_effectif and str(slot_value).startswith(current_effectif):
                        logger.info(f"⚠️ Réinitialisation effectif '{current_effectif}'")
                        return {
                            "exploitation": nom_exploitation, 
                            "exploitation_id": exploitation_id,
                            "effectif": None
                        }
                
                logger.info(f"✅ Correspondance exacte: {nom_exploitation} (ID: {exploitation_id})")
                return {"exploitation": nom_exploitation, "exploitation_id": exploitation_id}
            
            # Correspondance partielle
            if user_input in nom_exploitation_norm or nom_exploitation_norm.endswith(user_input):
                score = len(user_input) / len(nom_exploitation_norm) if nom_exploitation_norm else 0
                matches.append((nom_exploitation, exploitation_id, score))
                continue
            
            # Fuzzy matching
            ratio = SequenceMatcher(None, user_input, nom_exploitation_norm).ratio()
            if ratio > 0.6:
                matches.append((nom_exploitation, exploitation_id, ratio))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"📊 {len(matches)} correspondances trouvées")
        for match in matches[:3]:
            logger.info(f"  • {match[0]} (ID: {match[1]}, score: {match[2]:.2f})")
        
        if len(matches) == 0:
            exploitation_list = ','.join([e.get('NomExploitation', '') for e in exploitations[:10] if e.get('NomExploitation')])
            dispatcher.utter_message(
                text=f"❌ Exploitation invalide. Choisissez parmi : {exploitation_list}"
            )
            return {"exploitation": None, "exploitation_id": None}
        
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.2):
            # Une seule correspondance claire
            nom_exploitation, exploitation_id, score = matches[0]
            logger.info(f"✅ Exploitation validée: {nom_exploitation} (ID: {exploitation_id})")
            return {"exploitation": nom_exploitation, "exploitation_id": exploitation_id}
        
        else:
            # Plusieurs correspondances
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs exploitations correspondent.\n\n" +
                    f"[{', '.join(propositions)}](verification_hierarchie_exploitation)\n\n" +
                    "💬 Veuillez préciser."
            )
            return {"exploitation": None, "exploitation_id": None}
        