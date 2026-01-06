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

class ActionVerificationPoste(Action):
    """Valide le poste avec extraction prioritaire depuis le message initial"""
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_poste"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        nom_poste = tracker.get_slot("nom_poste")
        user_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        logger.info(f"🔍 verification_poste - message: '{user_message[:100]}...'")
        logger.info(f"   Slot nom_poste: {nom_poste}")
        
        # Récupérer tous les postes depuis le backend
        postes = self.backend.get_postes() or []
        
        if not postes:
            dispatcher.utter_message(text="❌ Impossible de récupérer la liste des postes.")
            return [SlotSet("nom_poste", None), SlotSet("poste_id", None)]
        
        # 🆕 CORRECTION : Prioriser les entités avec score élevé
        best_poste_entity = None
        best_score = 0.0
        
        for entity in entities:
            if entity.get('entity') == 'nom_poste':
                score = entity.get('confidence_entity', 0.0)
                if score > best_score:
                    best_score = score
                    best_poste_entity = entity.get('value')
        
        # Si on a trouvé une entité avec score > 90%, l'utiliser en priorité
        if best_poste_entity and best_score > 0.90:
            logger.info(f"✅ Entité poste prioritaire trouvée: '{best_poste_entity}' (score: {best_score:.2%})")
            nom_poste = best_poste_entity
        
        # 🆕 Si toujours pas de poste, essayer d'extraire du message initial
        if not nom_poste or nom_poste == "":
            extracted = self.extract_poste_from_message(user_message, postes)
            if extracted:
                nom_poste_found, id_poste = extracted
                logger.info(f"✅ Poste extrait du message: '{nom_poste_found}'")
                return [SlotSet("nom_poste", nom_poste_found), SlotSet("poste_id", id_poste)]
        
        # Si toujours vide, retourner None
        if not nom_poste or nom_poste == "":
            return [SlotSet("nom_poste", None), SlotSet("poste_id", None)]
        
        # Faire le matching avec la base de données
        user_input = self._remove_accents(str(nom_poste).lower().strip())
        matches = []
        
        for p in postes:
            nom_poste_db = p.get('NomPoste', '')
            id_poste = p.get('id') or p.get('IdPoste')
            if not nom_poste_db:
                continue
            
            nom_poste_norm = self._remove_accents(nom_poste_db.lower())
            
            # STRATÉGIE 1: Correspondance exacte
            if user_input == nom_poste_norm:
                logger.info(f"✅ Correspondance exacte: {nom_poste_db}")
                return [SlotSet("nom_poste", nom_poste_db), SlotSet("poste_id", id_poste)]
            
            # STRATÉGIE 2: Le nom complet du poste dans l'input
            if nom_poste_norm in user_input:
                matches.append((nom_poste_db, id_poste, 1.0, "poste_in_input"))
                continue
            
            # STRATÉGIE 3: L'input dans le nom du poste
            if user_input in nom_poste_norm:
                score = len(user_input) / len(nom_poste_norm)
                matches.append((nom_poste_db, id_poste, score, "input_in_poste"))
                continue
            
            # STRATÉGIE 4: Fuzzy matching
            ratio = SequenceMatcher(None, user_input, nom_poste_norm).ratio()
            if ratio > 0.6:
                matches.append((nom_poste_db, id_poste, ratio, "fuzzy_match"))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if len(matches) == 0:
            suggestions = self._get_suggestions(user_input, postes)
            if suggestions:
                dispatcher.utter_message(
                    text=f"❌ Aucun poste exact trouvé pour '{nom_poste}'.\n\n"
                        f"💡 Postes similaires:\n [" + 
                        ",".join([f"{s}" for s in suggestions[:10]])+"](verification_poste)"
                )
            return [SlotSet("nom_poste", None), SlotSet("poste_id", None)]
        
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.15):
            nom_poste_found, id_poste, score, method = matches[0]
            logger.info(f"✅ Poste validé: {nom_poste_found} (score: {score:.2f})")
            return [SlotSet("nom_poste", nom_poste_found), SlotSet("poste_id", id_poste)]
        
        else:
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs postes correspondent à '{nom_poste}'.\n\n" +
                    f"[{', '.join(propositions)}](verification_poste)\n\n" +
                    "💬 Veuillez préciser le poste exact."
            )
            return [SlotSet("nom_poste", None), SlotSet("poste_id", None)]
    
    def extract_poste_from_message(self, message: str, postes_list: List[Dict]) -> Optional[Tuple[str, Any]]:
        """Extrait intelligemment un poste depuis le DÉBUT du message"""
        
        # 🆕 CORRECTION : Extraire uniquement du début du message (500 premiers caractères)
        # pour éviter de capturer des fragments d'objectifs
        message_debut = message[:500]
        message_norm = self._remove_accents(message_debut.lower())
        matches = []
        
        for p in postes_list:
            nom_poste = p.get('NomPoste', '')
            id_poste = p.get('id') or p.get('IdPoste')
            if not nom_poste:
                continue
            
            nom_poste_norm = self._remove_accents(nom_poste.lower())
            
            # STRATÉGIE 1: Le nom complet du poste dans le début du message
            if nom_poste_norm in message_norm:
                # Vérifier que c'est bien au début (dans les 200 premiers caractères)
                pos = message_norm.find(nom_poste_norm)
                if pos < 200:
                    matches.append((nom_poste, id_poste, 1.0, pos))
                    continue
            
            # STRATÉGIE 2: Mots-clés communs
            poste_words = set(nom_poste_norm.split())
            message_words = set(message_norm.split())
            
            stop_words = {'le', 'la', 'les', 'un', 'une', 'de', 'du', 'des', 'et', 'ou', 'pour', 'avec'}
            poste_words_filtered = poste_words - stop_words
            message_words_filtered = message_words - stop_words
            
            common_words = poste_words_filtered & message_words_filtered
            
            if len(common_words) >= 2:
                score = len(common_words) / len(poste_words_filtered) if poste_words_filtered else 0
                if score >= 0.6:
                    matches.append((nom_poste, id_poste, score, 100))
        
        # Trier par score (puis par position dans le message)
        matches.sort(key=lambda x: (x[2], -x[3]), reverse=True)
        
        if matches and matches[0][2] >= 0.7:
            logger.info(f"✅ Poste extrait du début du message: {matches[0][0]} (score: {matches[0][2]:.2f})")
            return (matches[0][0], matches[0][1])
        
        return None
    
    def _remove_accents(self, text: str) -> str:
        """Supprime les accents"""
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        ).lower().strip()
    
    def _get_suggestions(self, user_input: str, postes: List[Dict]) -> List[str]:
        """Génère des suggestions de postes"""
        suggestions = []
        first_word = user_input.split()[0] if user_input.split() else ""
        
        for p in postes:
            nom_poste = p.get('NomPoste', '')
            if not nom_poste:
                continue
            nom_poste_norm = self._remove_accents(nom_poste.lower())
            if first_word and first_word in nom_poste_norm:
                suggestions.append(nom_poste)
        
        return suggestions