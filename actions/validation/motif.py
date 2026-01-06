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


class ActionVerificationMotif(Action):
    """Valide le motif avec extraction prioritaire depuis le message initial"""
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_motif"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        events = []
        entities = tracker.latest_message.get('entities', [])
        user_message = tracker.latest_message.get('text', '')
        
        # 🆕 CORRECTION CRITIQUE : Récupérer les valeurs ACTUELLES des slots
        current_motif = tracker.get_slot('motif')
        current_motif_id = tracker.get_slot('motif_id')
        current_budget = tracker.get_slot('situation_budget')
        current_budget_id = tracker.get_slot('situation_budget_id')
        
        # Extraction depuis le message
        motif = self._extract_motif_from_message(user_message)
        situation_budget = self._extract_budget_from_message(user_message)
        
        # Si pas trouvé dans le message, chercher dans les entités avec score élevé
        if not motif:
            best_motif = None
            best_score = 0.0
            
            for entity in entities:
                if entity.get('entity') == 'motif':
                    score = entity.get('confidence_entity', 0.0)
                    value = entity.get('value', '')
                    
                    # Valider SYSTÉMATIQUEMENT avec le backend
                    validated = self._validate_and_normalize_motif(value)
                    
                    if validated and score > best_score:
                        best_score = score
                        best_motif = validated
            
            if best_motif and best_score > 0.85:
                logger.info(f"✅ Motif depuis entité validée: '{best_motif}' (score: {best_score:.2%})")
                motif = best_motif
        
        # Même logique pour le budget
        if not situation_budget:
            best_budget = None
            best_score = 0.0
            
            for entity in entities:
                if entity.get('entity') == 'situation_budget':
                    score = entity.get('confidence_entity', 0.0)
                    value = entity.get('value', '')
                    
                    # Valider SYSTÉMATIQUEMENT avec le backend
                    validated = self._validate_and_normalize_budget(value)
                    
                    if validated and score > best_score:
                        best_score = score
                        best_budget = validated
            
            if best_budget and best_score > 0.85:
                logger.info(f"✅ Budget depuis entité validée: '{best_budget}' (score: {best_score:.2%})")
                situation_budget = best_budget
        
        # 🆕 CORRECTION : Ne valider QUE si une nouvelle valeur a été trouvée
        # Sinon, conserver la valeur actuelle
        if motif:
            logger.info(f"🔄 Validation du nouveau motif: '{motif}'")
            motif_result = self.validate_motif(motif, dispatcher)
            events.extend([SlotSet(k, v) for k, v in motif_result.items()])
        elif current_motif:
            # Conserver l'ancienne valeur
            logger.info(f"✅ Conservation du motif existant: '{current_motif}' (ID: {current_motif_id})")
            events.extend([
                SlotSet('motif', current_motif),
                SlotSet('motif_id', current_motif_id)
            ])
        else:
            # Aucune valeur trouvée ni existante
            events.extend([
                SlotSet('motif', None),
                SlotSet('motif_id', None)
            ])
        
        # Même logique pour la situation budgétaire
        if situation_budget:
            logger.info(f"🔄 Validation de la nouvelle situation budgétaire: '{situation_budget}'")
            budget_result = self.validate_situation_budget(situation_budget, dispatcher)
            events.extend([SlotSet(k, v) for k, v in budget_result.items()])
        elif current_budget:
            # Conserver l'ancienne valeur
            logger.info(f"✅ Conservation de la situation budgétaire existante: '{current_budget}' (ID: {current_budget_id})")
            events.extend([
                SlotSet('situation_budget', current_budget),
                SlotSet('situation_budget_id', current_budget_id)
            ])
        else:
            # Aucune valeur trouvée ni existante
            events.extend([
                SlotSet('situation_budget', None),
                SlotSet('situation_budget_id', None)
            ])
        
        return events
    
    def _extract_motif_from_message(self, message: str) -> Optional[str]:
        """
        Extraction contextuelle intelligente du motif
        Cherche le motif UNIQUEMENT dans le contexte explicite
        """
        if not message:
            return None
        
        message_norm = self._remove_accents(message.lower())
        
        # STRATÉGIE : Extraire UNIQUEMENT la zone qui parle du motif
        motif_patterns = [
            # "Le motif est X" (jusqu'à un point, virgule, ou nouveau sujet)
            r'(?:le|la)\s+motif\s+(?:est|de\s+(?:la\s+)?demande)?\s*:?\s*([^.,]+?)(?=\s*[.,]|\s+avec\s+une\s+situation|\s+situation\s+budg)',
            
            # "motif: X" ou "motif : X" (jusqu'à virgule ou point)
            r'motif\s*:\s*([^.,]+?)(?=\s*[.,]|$)',
            
            # "avec un motif X" (court, avant virgule)
            r'avec\s+(?:un\s+)?motif\s+([^.,]{3,30})(?=\s*[.,]|$)',
        ]
        
        for pattern in motif_patterns:
            match = re.search(pattern, message_norm, re.IGNORECASE)
            if match:
                motif_extrait = match.group(1).strip()
                
                # Valider avec le backend
                return self._validate_and_normalize_motif(motif_extrait)
        
        return None
    
    def _extract_budget_from_message(self, message: str) -> Optional[str]:
        """
        Extraction contextuelle de la situation budgétaire
        """
        if not message:
            return None
        
        message_norm = self._remove_accents(message.lower())
        
        # Patterns pour extraire UNIQUEMENT la zone budgétaire
        budget_patterns = [
            # "situation budgétaire: X" ou "situation budgétaire X"
            r'situation\s+budg[eé]taire\s*:?\s*([^.,]+?)(?=\s*[.,]|$)',
            
            # "avec une situation budgétaire X"
            r'avec\s+une\s+situation\s+budg[eé]taire\s+([^.,]{3,30})(?=\s*[.,]|$)',
            
            # "poste budgétisé" ou "budget validé"
            r'(?:poste|budget)\s+(budg[eé]tis[eé]e?|valid[eé]e?|approuv[eé]e?|hors\s+budget)',
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message_norm, re.IGNORECASE)
            if match:
                budget_extrait = match.group(1).strip()
                
                # Valider avec le backend
                validated = self._validate_and_normalize_budget(budget_extrait)
                if validated:
                    return validated
        
        return None
    
    def _validate_and_normalize_motif(self, motif_extrait: str) -> Optional[str]:
        """
        Valide un motif extrait en le comparant avec la base de données
        Retourne le nom normalisé du motif ou None si invalide
        """
        if not motif_extrait or len(motif_extrait) < 3:
            return None
        
        # Récupérer les motifs valides depuis le backend
        motifs = self.backend.get_motif_demandes() or []
        
        if not motifs:
            logger.warning("⚠️ Impossible de récupérer les motifs depuis le backend")
            return None
        
        motif_norm = self._remove_accents(motif_extrait.lower().strip())
        
        # Chercher une correspondance
        for m in motifs:
            motif_name = m.get('Motif', '')
            if not motif_name:
                continue
            
            motif_db_norm = self._remove_accents(motif_name.lower())
            
            # Correspondance exacte
            if motif_norm == motif_db_norm:
                logger.info(f"✅ Motif validé (exact): '{motif_name}'")
                return motif_name
            
            # Correspondance partielle forte (80%)
            if motif_norm in motif_db_norm:
                score = len(motif_norm) / len(motif_db_norm)
                if score > 0.6:
                    logger.info(f"✅ Motif validé (partiel): '{motif_name}' (score: {score:.2%})")
                    return motif_name
            
            # Fuzzy matching fort
            ratio = SequenceMatcher(None, motif_norm, motif_db_norm).ratio()
            if ratio > 0.8:
                logger.info(f"✅ Motif validé (fuzzy): '{motif_name}' (ratio: {ratio:.2%})")
                return motif_name
        
        logger.info(f"⚠️ Motif non validé: '{motif_extrait}'")
        return None
    
    def _validate_and_normalize_budget(self, budget_extrait: str) -> Optional[str]:
        """
        Valide une situation budgétaire extraite
        """
        if not budget_extrait or len(budget_extrait) < 3:
            return None
        
        situations = self.backend.get_situation_budgets() or []
        
        if not situations:
            return None
        
        budget_norm = self._remove_accents(budget_extrait.lower().strip())
        
        for s in situations:
            situation_name = s.get('SituationBudget', '')
            if not situation_name:
                continue
            
            situation_norm = self._remove_accents(situation_name.lower())
            
            # Correspondance exacte ou partielle forte
            if budget_norm == situation_norm or budget_norm in situation_norm:
                score = len(budget_norm) / len(situation_norm) if budget_norm in situation_norm else 1.0
                if score > 0.5:
                    logger.info(f"✅ Budget validé: '{situation_name}'")
                    return situation_name
            
            # Fuzzy matching
            ratio = SequenceMatcher(None, budget_norm, situation_norm).ratio()
            if ratio > 0.8:
                logger.info(f"✅ Budget validé (fuzzy): '{situation_name}'")
                return situation_name
        
        return None
    
    def validate_motif(self, slot_value: Any, dispatcher) -> Dict[Text, Any]:
        """Valide le motif avec fuzzy matching"""
        
        if not slot_value:
            return {"motif": None, "motif_id": None}
        
        motifs = self.backend.get_motif_demandes() or []
        
        if not motifs:
            dispatcher.utter_message(text="❌ Impossible de récupérer la liste des motifs.")
            return {"motif": None, "motif_id": None}
        
        user_input = self._remove_accents(str(slot_value).lower().strip())
        matches = []
        
        for m in motifs:
            motif_name = m.get('Motif', '')
            motif_id = m.get('IdMotif')
            
            if not motif_name:
                continue
            
            motif_norm = self._remove_accents(motif_name.lower())
            
            # Correspondance exacte
            if user_input == motif_norm:
                return {"motif": motif_name, "motif_id": motif_id}
            
            # Correspondance partielle
            if user_input in motif_norm or motif_norm in user_input:
                score = len(user_input) / len(motif_norm) if motif_norm else 0
                matches.append((motif_name, motif_id, score))
                continue
            
            # Fuzzy matching
            ratio = SequenceMatcher(None, user_input, motif_norm).ratio()
            if ratio > 0.6:
                matches.append((motif_name, motif_id, ratio))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if len(matches) == 0:
            motif_list = ','.join([m.get('Motif', '') for m in motifs if m.get('Motif')])
            dispatcher.utter_message(
                text=f"❌ Motif invalide ({slot_value}). Choisissez parmi : {motif_list}"
            )
            return {"motif": None, "motif_id": None}
        
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.2):
            motif_name, motif_id, score = matches[0]
            logger.info(f"✅ Motif validé: {motif_name} (ID: {motif_id})")
            return {"motif": motif_name, "motif_id": motif_id}
        
        else:
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs motifs correspondent.\n\n" +
                    f"[{', '.join(propositions)}](verification_motif)\n\n" +
                    "💬 Veuillez préciser."
            )
            return {"motif": None, "motif_id": None}
    
    def validate_situation_budget(self, slot_value: Any, dispatcher) -> Dict[Text, Any]:
        """Valide la situation budgétaire"""
        
        if not slot_value:
            return {"situation_budget": None, "situation_budget_id": None}
        
        situations = self.backend.get_situation_budgets() or []
        
        if not situations:
            dispatcher.utter_message(text="❌ Impossible de récupérer les situations budgétaires.")
            return {"situation_budget": None, "situation_budget_id": None}
        
        user_input = self._remove_accents(str(slot_value).lower().strip())
        matches = []
        
        for s in situations:
            situation_name = s.get('SituationBudget', '')
            situation_id = s.get('IdSb')
            
            if not situation_name:
                continue
            
            situation_norm = self._remove_accents(situation_name.lower())
            
            if user_input == situation_norm:
                return {"situation_budget": situation_name, "situation_budget_id": situation_id}
            
            if user_input in situation_norm or situation_norm in user_input:
                score = len(user_input) / len(situation_norm) if situation_norm else 0
                matches.append((situation_name, situation_id, score))
                continue
            
            ratio = SequenceMatcher(None, user_input, situation_norm).ratio()
            if ratio > 0.6:
                matches.append((situation_name, situation_id, ratio))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if len(matches) == 0:
            budget_list = ','.join([s.get('SituationBudget', '') for s in situations if s.get('SituationBudget')])
            dispatcher.utter_message(
                text=f"❌ Situation budgétaire invalide. Choisissez parmi : {budget_list}"
            )
            return {"situation_budget": None, "situation_budget_id": None}
        
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.2):
            situation_name, situation_id, score = matches[0]
            return {"situation_budget": situation_name, "situation_budget_id": situation_id}
        
        else:
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs situations budgétaires correspondent.\n\n" +
                    f"[{', '.join(propositions)}](verification_situation_budget)\n\n" +
                    "💬 Veuillez préciser."
            )
            return {"situation_budget": None, "situation_budget_id": None}
    
    def _remove_accents(self, text: str) -> str:
        """Supprime les accents"""
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        ).lower().strip()
        