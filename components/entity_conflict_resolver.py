"""
Composant personnalisé pour résoudre les conflits d'entités qui se chevauchent.
Priorité : RegexEntityExtractor > DIETClassifier
"""

from typing import Any, Dict, List, Text, Optional
from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.constants import ENTITIES
import logging

logger = logging.getLogger(__name__)


@DefaultV1Recipe.register(
    DefaultV1Recipe.ComponentType.ENTITY_EXTRACTOR, is_trainable=False
)
class EntityConflictResolver(GraphComponent):
    """
    Résout les conflits entre entités qui se chevauchent.
    
    Ce composant traite les cas où plusieurs extracteurs détectent
    des entités aux mêmes positions ou qui se chevauchent.
    
    Règles de priorité :
    1. RegexEntityExtractor a la priorité sur DIETClassifier
    2. Entre deux DIETClassifier, l'entité la plus longue est conservée
    3. Entre deux Regex, l'entité la plus longue est conservée
    """

    @classmethod
    def create(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
    ) -> "EntityConflictResolver":
        """Crée une instance du composant."""
        return cls()

    def process(self, messages: List[Message]) -> List[Message]:
        """
        Traite les messages pour résoudre les conflits d'entités.
        
        Args:
            messages: Liste des messages à traiter
            
        Returns:
            Liste des messages avec entités résolues
        """
        for message in messages:
            entities = message.get(ENTITIES, [])
            
            if len(entities) > 1:
                # Résoudre les conflits
                resolved_entities = self._resolve_conflicts(entities)
                message.set(ENTITIES, resolved_entities, add_to_output=True)
                
                # Log si des conflits ont été résolus
                if len(resolved_entities) < len(entities):
                    logger.info(
                        f"Conflits résolus : {len(entities)} entités "
                        f"-> {len(resolved_entities)} entités"
                    )
        
        return messages

    def _resolve_conflicts(self, entities: List[Dict]) -> List[Dict]:
        """
        Résout les conflits entre entités qui se chevauchent.
        
        Args:
            entities: Liste des entités détectées
            
        Returns:
            Liste des entités sans chevauchement
        """
        if not entities:
            return entities

        # Trier par position de départ, puis par longueur décroissante
        entities.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
        
        resolved = []
        
        for entity in entities:
            # Vérifier si cette entité chevauche une entité déjà acceptée
            conflict_index = self._find_conflict(entity, resolved)
            
            if conflict_index is None:
                # Pas de conflit, ajouter l'entité
                resolved.append(entity)
            else:
                # Conflit détecté, appliquer les règles de priorité
                accepted = resolved[conflict_index]
                winner = self._resolve_single_conflict(entity, accepted)
                
                if winner != accepted:
                    # Remplacer l'entité acceptée
                    resolved[conflict_index] = winner
                    logger.debug(
                        f"Conflit résolu : '{winner['value']}' "
                        f"({winner.get('extractor', 'unknown')}) remplace "
                        f"'{accepted['value']}' ({accepted.get('extractor', 'unknown')}) "
                        f"à la position {winner['start']}-{winner['end']}"
                    )
        
        return resolved

    def _find_conflict(
        self, entity: Dict, resolved: List[Dict]
    ) -> Optional[int]:
        """
        Trouve l'index de la première entité en conflit.
        
        Args:
            entity: L'entité à vérifier
            resolved: Liste des entités déjà acceptées
            
        Returns:
            Index de l'entité en conflit, ou None si pas de conflit
        """
        for i, accepted in enumerate(resolved):
            if self._entities_overlap(entity, accepted):
                return i
        return None

    def _resolve_single_conflict(
        self, entity1: Dict, entity2: Dict
    ) -> Dict:
        """
        Résout un conflit entre deux entités.
        
        Règles de priorité :
        1. RegexEntityExtractor > DIETClassifier
        2. Si même extracteur, la plus longue entité gagne
        3. Si même longueur, la première (entity2) est conservée
        
        Args:
            entity1: Première entité
            entity2: Deuxième entité
            
        Returns:
            L'entité gagnante
        """
        extractor1 = entity1.get("extractor", "")
        extractor2 = entity2.get("extractor", "")
        
        # Règle 1 : Regex a priorité sur DIET
        if extractor1 == "RegexEntityExtractor" and extractor2 != "RegexEntityExtractor":
            return entity1
        if extractor2 == "RegexEntityExtractor" and extractor1 != "RegexEntityExtractor":
            return entity2
        
        # Règle 2 : Si même type d'extracteur, la plus longue entité gagne
        length1 = entity1["end"] - entity1["start"]
        length2 = entity2["end"] - entity2["start"]
        
        if length1 > length2:
            return entity1
        elif length2 > length1:
            return entity2
        
        # Règle 3 : Si même longueur, conserver la première (entity2)
        return entity2

    def _entities_overlap(self, e1: Dict, e2: Dict) -> bool:
        """
        Vérifie si deux entités se chevauchent.
        
        Deux entités se chevauchent si leurs intervalles [start, end]
        ont une intersection non vide.
        
        Args:
            e1: Première entité
            e2: Deuxième entité
            
        Returns:
            True si les entités se chevauchent, False sinon
        """
        # Pas de chevauchement si :
        # - e1 se termine avant ou au début de e2
        # - e1 commence après ou à la fin de e2
        return not (e1["end"] <= e2["start"] or e1["start"] >= e2["end"])

    @staticmethod
    def get_default_config() -> Dict[Text, Any]:
        """Retourne la configuration par défaut du composant."""
        return {}