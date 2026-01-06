"""
Système de déduplication des messages pour éviter les réponses en double du chatbot.
Utilise un cache temporel avec hash MD5 pour détecter les doublons.
"""

from functools import wraps
from typing import Any, Dict, List, Text, Optional
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Tracker
import hashlib
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MessageCache:
    """
    Cache global pour stocker les messages récents et détecter les doublons.
    """
    
    def __init__(self, cache_duration_seconds: int = 5):
        """
        Args:
            cache_duration_seconds: Durée pendant laquelle un message est considéré 
                                   comme "récent" (en secondes)
        """
        self._cache = {}  # {sender_id: [(message_hash, timestamp)]}
        self._cache_duration = timedelta(seconds=cache_duration_seconds)
    
    def _get_message_hash(self, text: Text) -> str:
        """
        Génère un hash MD5 unique pour un message.
        
        Args:
            text: Le texte du message
            
        Returns:
            Hash MD5 du message
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _clean_expired_messages(self):
        """
        Nettoie les messages expirés du cache pour éviter une croissance illimitée.
        """
        now = datetime.now()
        
        for sender_id in list(self._cache.keys()):
            # Filtrer les messages encore valides
            self._cache[sender_id] = [
                (msg_hash, timestamp)
                for msg_hash, timestamp in self._cache[sender_id]
                if now - timestamp < self._cache_duration
            ]
            
            # Supprimer l'entrée si plus aucun message
            if not self._cache[sender_id]:
                del self._cache[sender_id]
    
    def is_duplicate(self, sender_id: Text, message: Text) -> bool:
        """
        Vérifie si un message est un doublon récent.
        
        Args:
            sender_id: Identifiant de l'utilisateur
            message: Texte du message à vérifier
            
        Returns:
            True si le message est un doublon, False sinon
        """
        # Nettoyer le cache
        self._clean_expired_messages()
        
        # Calculer le hash du message
        message_hash = self._get_message_hash(message)
        now = datetime.now()
        
        # Vérifier si le sender_id existe dans le cache
        if sender_id not in self._cache:
            self._cache[sender_id] = []
        
        # Chercher un doublon
        for stored_hash, timestamp in self._cache[sender_id]:
            if stored_hash == message_hash:
                time_diff = (now - timestamp).total_seconds()
                logger.warning(
                    f"🚫 DOUBLON DÉTECTÉ pour '{sender_id}' "
                    f"(envoyé il y a {time_diff:.2f}s): '{message[:80]}...'"
                )
                return True
        
        # Pas de doublon trouvé, ajouter au cache
        self._cache[sender_id].append((message_hash, now))
        logger.debug(f"✅ Message unique enregistré pour '{sender_id}'")
        
        return False
    
    def clear_cache(self, sender_id: Optional[Text] = None):
        """
        Vide le cache pour un utilisateur spécifique ou pour tous.
        
        Args:
            sender_id: Identifiant de l'utilisateur (None = vider tout le cache)
        """
        if sender_id:
            if sender_id in self._cache:
                del self._cache[sender_id]
                logger.info(f"🗑️ Cache vidé pour '{sender_id}'")
        else:
            self._cache.clear()
            logger.info("🗑️ Cache global vidé")


# Instance globale du cache
_global_cache = MessageCache(cache_duration_seconds=5)


class DeduplicatingDispatcher:
    """
    Wrapper autour de CollectingDispatcher qui déduplique automatiquement les messages.
    """
    
    def __init__(self, original_dispatcher: CollectingDispatcher, sender_id: Text):
        """
        Args:
            original_dispatcher: Le dispatcher Rasa original
            sender_id: Identifiant de l'utilisateur
        """
        self._dispatcher = original_dispatcher
        self._sender_id = sender_id
    
    def utter_message(
        self, 
        text: Optional[Text] = None,
        image: Optional[Text] = None,
        json_message: Optional[Dict] = None,
        template: Optional[Text] = None,
        attachment: Optional[Text] = None,
        buttons: Optional[List[Dict]] = None,
        elements: Optional[List[Dict]] = None,
        **kwargs
    ):
        """
        Envoie un message uniquement s'il n'est pas un doublon récent.
        
        Args:
            text: Texte du message
            image: URL d'une image
            json_message: Message JSON personnalisé
            template: Nom du template à utiliser
            attachment: URL d'une pièce jointe
            buttons: Liste de boutons
            elements: Liste d'éléments
            **kwargs: Autres arguments
        """
        # Si c'est un message texte, vérifier les doublons
        if text:
            if _global_cache.is_duplicate(self._sender_id, text):
                logger.info(f"⏭️ Message dupliqué ignoré pour '{self._sender_id}'")
                return  # Ne pas envoyer le message
        
        # Envoyer le message via le dispatcher original
        self._dispatcher.utter_message(
            text=text,
            image=image,
            json_message=json_message,
            template=template,
            attachment=attachment,
            buttons=buttons,
            elements=elements,
            **kwargs
        )


def deduplicate_messages(func):
    """
    Décorateur pour dédupliquer automatiquement les messages d'une action Rasa.
    
    Usage:
        @deduplicate_messages
        def run(self, dispatcher, tracker, domain):
            dispatcher.utter_message(text="Bonjour!")
            return []
    
    Les messages identiques envoyés dans une fenêtre de 5 secondes seront ignorés.
    """
    @wraps(func)
    def wrapper(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        sender_id = tracker.sender_id
        
        # Créer un dispatcher avec déduplication
        dedup_dispatcher = DeduplicatingDispatcher(dispatcher, sender_id)
        
        # Appeler la fonction originale avec le dispatcher dédupliqué
        result = func(self, dedup_dispatcher, tracker, domain)
        
        return result
    
    return wrapper


def clear_message_cache(sender_id: Optional[Text] = None):
    """
    Fonction utilitaire pour vider le cache de messages.
    
    Args:
        sender_id: Identifiant de l'utilisateur (None = vider tout le cache)
    """
    _global_cache.clear_cache(sender_id)