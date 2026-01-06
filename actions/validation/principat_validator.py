import asyncio
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import logging
from typing import Any, Text, Dict, List, Set
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

logger = logging.getLogger(__name__)

# Import des validateurs
from .poste import ActionVerificationPoste
from .encadreur import ActionVerificationEncadreur
from .hierarchie import ActionVerificationHierarchie
from .motif import ActionVerificationMotif
from .contrat import ActionVerificationContrat
from .justification import ActionVerificationJustification
from .objectifs import ActionVerificationObjectif
from .dotation import ActionVerificationDotation
from .piece_joint import ActionVerificationPieceJointe


class ActionValidateSlots(Action):
    """
    Middleware universel optimisé pour la validation automatique des slots
    ✅ Validation asynchrone parallèle pour réduire le temps d'exécution
    """
    
    # ✅ OPTIMISATION 1: Cache des instances de validateurs (évite les instanciations répétées)
    _validators_cache = None
    
    # ✅ OPTIMISATION 2: Pré-compilation des patterns de détection
    _justification_keywords = frozenset([
        'justification', 'justifié', 'motivé', 'raison',
        'renfort permettra', 'accélérer le développement'
    ])
    
    def name(self) -> Text:
        return "action_validate_slots"
    
    @classmethod
    def _get_validators_map(cls) -> Dict[str, Action]:
        """Cache partagé des validateurs pour éviter les instanciations multiples"""
        if cls._validators_cache is None:
            cls._validators_cache = {
                "nom_poste": ActionVerificationPoste(),
                "nom_encadreur": ActionVerificationEncadreur(),
                "direction": ActionVerificationHierarchie(),
                "exploitation": ActionVerificationHierarchie(),
                "motif": ActionVerificationMotif(),
                "situation_budget": ActionVerificationMotif(),
                "effectif": ActionVerificationContrat(),
                "duree_contrat": ActionVerificationContrat(),
                "nature_contrat": ActionVerificationContrat(),
                "date_mise_en_service": ActionVerificationContrat(),
                "justification": ActionVerificationJustification(),
                "objectifs_list": ActionVerificationObjectif(),
                "objectif": ActionVerificationObjectif(),
                "dotations_list": ActionVerificationDotation(),
                "dotation": ActionVerificationDotation(),
                "piece_jointe": ActionVerificationPieceJointe(),
            }
        return cls._validators_cache
    
    def _detect_slots_to_validate(
        self, 
        entities: List[Dict], 
        user_message: str, 
        metadata: Dict
    ) -> Set[str]:
        """
        ✅ OPTIMISATION 3: Détection rapide des slots en une seule passe
        """
        slots = set()
        validators_map = self._get_validators_map()
        
        # Extraction depuis les entités
        for entity in entities:
            entity_name = entity.get("entity")
            if entity_name in validators_map:
                slots.add(entity_name)
        
        # Détection de fichier joint
        attachments = metadata.get("attachments", [])
        if attachments:
            slots.add("piece_jointe")
        
        # Détection contextuelle de justification (optimisée)
        if not slots.intersection({"justification"}) and user_message:
            user_message_lower = user_message.lower()
            if any(kw in user_message_lower for kw in self._justification_keywords):
                slots.add("justification")
        
        # ✅ OPTIMISATION 4: Application des règles de groupage en une fois
        if slots.intersection({"direction", "exploitation"}):
            slots.update(["direction", "exploitation"])
        
        if slots.intersection({"motif", "situation_budget"}):
            slots.update(["motif", "situation_budget"])
        
        contrat_slots = {"effectif", "duree_contrat", "nature_contrat", "date_mise_en_service"}
        if slots.intersection(contrat_slots):
            slots.update(contrat_slots)
        
        if "objectif" in slots:
            slots.add("objectifs_list")
        
        if "dotation" in slots:
            slots.add("dotations_list")
        
        return slots
    
    async def _execute_validator(
        self,
        slot_name: str,
        validator: Action,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> tuple[str, List[Dict[Text, Any]], bool]:
        """
        ✅ OPTIMISATION 5: Wrapper pour exécution async uniforme avec gestion d'erreur
        Retourne: (slot_name, events, success)
        """
        try:
            result = validator.run(dispatcher, tracker, domain)
            
            # Gestion async/sync
            if asyncio.iscoroutine(result):
                validation_events = await result
            else:
                validation_events = result
            
            return (slot_name, validation_events or [], True)
        
        except Exception as e:
            logger.error(f"❌ Erreur validation {slot_name}: {e}")
            return (slot_name, [], False)
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ✅ OPTIMISATION 6: Extraction des données en une seule passe
        latest_message = tracker.latest_message
        entities = latest_message.get("entities", [])
        user_message = latest_message.get('text', '')
        
        # Métadonnées
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        latest_metadata = latest_message.get("metadata", {})
        all_metadata = {**session_metadata, **latest_metadata}
        
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"\n{'='*80}")
            logger.info(f"🔍 ACTION_VALIDATE_SLOTS - Message: '{user_message[:100]}'")
            logger.info(f"📊 Entités: {len(entities)}")
            logger.info(f"{'='*80}\n")
        
        # Détection rapide des slots à valider
        slots_a_valider = self._detect_slots_to_validate(entities, user_message, all_metadata)
        
        if not slots_a_valider:
            logger.info("ℹ️ Aucun slot à valider")
            return []
        
        logger.info(f"📊 SLOTS À VALIDER: {', '.join(sorted(slots_a_valider))}\n")
        
        # ✅ OPTIMISATION 7: Ordre de validation optimisé
        ordre_validation = [
            "nom_poste", "nom_encadreur",
            "direction", "exploitation",
            "nature_contrat", "effectif", "duree_contrat", "date_mise_en_service",
            "motif", "situation_budget",
            "justification",
            "objectif", "objectifs_list",
            "dotation", "dotations_list",
            "piece_jointe",
        ]
        
        # Filtrer l'ordre pour ne garder que les slots pertinents
        slots_ordonnes = [s for s in ordre_validation if s in slots_a_valider]
        
        # ✅ OPTIMISATION 8: Regroupement par validateur pour éviter les doublons
        validators_map = self._get_validators_map()
        validator_to_slots = {}
        
        for slot_name in slots_ordonnes:
            validator = validators_map.get(slot_name)
            if validator:
                validator_id = id(validator)
                if validator_id not in validator_to_slots:
                    validator_to_slots[validator_id] = (validator, slot_name)
        
        # ✅ OPTIMISATION 9: VALIDATION PARALLÈLE avec asyncio.gather
        # Au lieu d'exécuter séquentiellement, on exécute tous les validateurs en parallèle
        validation_tasks = [
            self._execute_validator(slot_name, validator, dispatcher, tracker, domain)
            for validator, slot_name in validator_to_slots.values()
        ]
        
        # Exécution parallèle de toutes les validations
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        
        # Traitement des résultats
        all_events = []
        validations_effectuees = {}
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ Exception durant validation: {result}")
                continue
            
            slot_name, events, success = result
            validations_effectuees[slot_name] = success
            
            if events:
                all_events.extend(events)
                if logger.isEnabledFor(logging.INFO):
                    logger.info(f"✅ {slot_name} → {len(events)} event(s)")
        
        # Statistiques
        nb_valides = sum(1 for v in validations_effectuees.values() if v)
        nb_total = len(validations_effectuees)
        
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"\n{'='*80}")
            logger.info(f"✅ VALIDATION: {nb_valides}/{nb_total} slot(s) validé(s)")
            logger.info(f"📊 Events: {len(all_events)}")
            logger.info(f"{'='*80}\n")
        
        # ✅ OPTIMISATION 10: Déduplication optimisée
        return self._deduplicate_events_fast(all_events)
    
    def _deduplicate_events_fast(self, events: List[Dict[Text, Any]]) -> List[Dict[Text, Any]]:
        """
        ✅ OPTIMISATION 11: Déduplication ultra-rapide avec dict comprehension
        """
        slots_dict = {}
        other_events = []
        
        for event in events:
            if hasattr(event, 'key'):
                slots_dict[event.key] = event
            elif isinstance(event, dict):
                event_type = event.get('event')
                if event_type == 'slot':
                    slot_name = event.get('name')
                    if slot_name:
                        slots_dict[slot_name] = event
                else:
                    other_events.append(event)
            else:
                other_events.append(event)
        
        # Reconstruction rapide
        result = list(slots_dict.values()) + other_events
        
        if len(events) != len(result) and logger.isEnabledFor(logging.INFO):
            logger.info(f"🔧 Déduplication: {len(events)} → {len(result)} events")
        
        return result