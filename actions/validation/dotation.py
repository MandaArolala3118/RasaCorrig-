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


class ActionVerificationDotation(Action):
    """Valide et enregistre les dotations avec leurs IDs depuis la base de données"""
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_dotation"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Récupérer la liste actuelle des dotations (format: [{"dotation": "...", "dotation_id": ...}, ...])
        dotations_list = tracker.get_slot("dotations_list") or []
        
        # Extraire toutes les entités dotation du message actuel
        entities = tracker.latest_message.get('entities', [])
        dotations_nouvelles = []
        
        for entity in entities:
            if entity.get('entity') == 'dotation':
                dotation_value = entity.get('value', '').strip()
                if dotation_value and len(dotation_value) >= 2:
                    dotations_nouvelles.append(dotation_value)
        
        logger.info(f"🔍 verification_dotation")
        logger.info(f"   📋 Liste actuelle: {len(dotations_list)} dotation(s)")
        logger.info(f"   🆕 Nouvelles dotations détectées: {dotations_nouvelles}")
        
        # Si aucune entité dotation détectée
        if not dotations_nouvelles:
            logger.info("⚠️ Aucune dotation détectée dans le message")
            return []
        
        # Récupérer toutes les dotations depuis le backend
        dotations_db = self.backend.get_dotation_listes() or []
        
        if not dotations_db:
            dispatcher.utter_message(text="❌ Impossible de récupérer la liste des dotations.")
            return []
        
        # Traiter chaque nouvelle dotation
        events = []
        for dotation_str in dotations_nouvelles:
            
            # Vérifier si elle n'est pas déjà dans la liste
            if any(d.get('dotation', '').lower() == dotation_str.lower() for d in dotations_list):
                logger.info(f"⏭️ Dotation déjà présente: {dotation_str}")
                continue
            
            # Valider et récupérer l'ID depuis la base
            result = self.validate_dotation(dotation_str, dotations_db, dispatcher)
            
            if result:
                dotations_list.append(result)
                logger.info(f"✅ Dotation validée et ajoutée: {result['dotation']} (ID: {result['dotation_id']})")
        
        # Message de confirmation si des dotations ont été ajoutées
        if len(dotations_list) > 0:
            recap = "\n".join([f"  • {d['dotation']}" for d in dotations_list])
            dispatcher.utter_message(
                text=f"✅ **Dotations enregistrées ({len(dotations_list)}):**\n{recap}"
            )
        
        return [SlotSet("dotations_list", dotations_list)]
    
    def validate_dotation(self, dotation_str: str, dotations_db: List[Dict], dispatcher) -> Optional[Dict]:
        """
        Valide une dotation avec fuzzy matching et retourne {"dotation": "...", "dotation_id": ...} ou None
        """
        
        user_input = self._remove_accents(dotation_str.lower().strip())
        matches = []
        
        logger.info(f"🔍 Recherche dotation: '{dotation_str}' (normalisé: '{user_input}')")
        
        for d in dotations_db:
            # Utiliser le nom de colonne correct: DotationOption
            nom_dotation = d.get('DotationOption', '')
            dotation_id = d.get('IdDotation')
            
            if not nom_dotation or not dotation_id:
                continue
            
            nom_dotation_norm = self._remove_accents(nom_dotation.lower())
            
            # STRATÉGIE 1: Correspondance exacte
            if user_input == nom_dotation_norm:
                logger.info(f"✅ Correspondance exacte: {nom_dotation} (ID: {dotation_id})")
                return {"dotation": nom_dotation, "dotation_id": dotation_id}
            
            # STRATÉGIE 2: Le nom complet de la dotation dans l'input
            if nom_dotation_norm in user_input:
                score = len(nom_dotation_norm) / len(user_input)
                matches.append((nom_dotation, dotation_id, score))
                continue
            
            # STRATÉGIE 3: L'input dans le nom de la dotation
            if user_input in nom_dotation_norm:
                score = len(user_input) / len(nom_dotation_norm)
                matches.append((nom_dotation, dotation_id, score))
                continue
            
            # STRATÉGIE 4: Fuzzy matching
            ratio = SequenceMatcher(None, user_input, nom_dotation_norm).ratio()
            if ratio > 0.6:
                matches.append((nom_dotation, dotation_id, ratio))
        
        # Trier par score décroissant
        matches.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"📊 {len(matches)} correspondance(s) trouvée(s)")
        for match in matches[:3]:
            logger.info(f"  • {match[0]} (ID: {match[1]}, score: {match[2]:.2f})")
        
        # Aucune correspondance
        if len(matches) == 0:
            # Proposer des suggestions basées sur les premières lettres
            suggestions = self._get_suggestions(user_input, dotations_db)
            if suggestions:
                dispatcher.utter_message(
                    text=f"❌ Aucune dotation exacte trouvée pour '{dotation_str}'.\n\n"
                         f"💡 Dotations similaires:\n" + 
                         "\n".join([f"  • {s}" for s in suggestions[:10]])
                )
            else:
                dispatcher.utter_message(
                    text=f"❌ Dotation invalide: '{dotation_str}'. Veuillez vérifier l'orthographe."
                )
            return None
        
        # Une seule correspondance claire
        elif len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.15):
            nom_dotation, dotation_id, score = matches[0]
            logger.info(f"✅ Dotation validée: {nom_dotation} (ID: {dotation_id}, score: {score:.2f})")
            return {"dotation": nom_dotation, "dotation_id": dotation_id}
        
        # Plusieurs correspondances ambiguës
        else:
            propositions = [m[0] for m in matches[:5]]
            dispatcher.utter_message(
                text=f"🔍 Plusieurs dotations correspondent à '{dotation_str}'.\n\n" +
                    f"[{', '.join(propositions)}](verification_dotation)\n\n" +
                    "💬 Veuillez préciser la dotation exacte."
            )
            return None
    
    def _remove_accents(self, text: str) -> str:
        """Supprime les accents d'une chaîne de caractères"""
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        ).lower().strip()
    
    def _get_suggestions(self, user_input: str, dotations_db: List[Dict]) -> List[str]:
        """Génère des suggestions de dotations basées sur le premier mot"""
        suggestions = []
        first_word = user_input.split()[0] if user_input.split() else ""
        
        for d in dotations_db:
            # Utiliser le nom de colonne correct: DotationOption
            nom_dotation = d.get('DotationOption', '')
            if not nom_dotation:
                continue
            nom_dotation_norm = self._remove_accents(nom_dotation.lower())
            if first_word and first_word in nom_dotation_norm:
                suggestions.append(nom_dotation)
        
        return suggestions

class ActionSupprimerDotation(Action):
    """
    Supprime UNE SEULE dotation spécifique
    Exemples : "supprime la dotation smartphone", "retire l'ordinateur portable"
    """
    
    def name(self) -> Text:
        return "action_supprimer_dotation"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Récupérer la liste actuelle des dotations
        dotations_list = tracker.get_slot("dotations_list") or []
        
        if not dotations_list:
            dispatcher.utter_message(
                text="❌ **Aucune dotation à supprimer.**\n\nLa liste est déjà vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION D'UNE DOTATION")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Dotations actuelles: {len(dotations_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE LE NOM DE LA DOTATION
        # ==========================================
        nom_dotation = self._extraire_nom_dotation(user_message, dotations_list)
        
        if not nom_dotation:
            dispatcher.utter_message(
                text="❓ **Quelle dotation souhaitez-vous supprimer ?**\n\n"
                     f"📦 **Dotations actuelles ({len(dotations_list)}) :**\n" +
                     "\n".join([f"  • {d.get('dotation', 'N/A')}" for d in dotations_list]) +
                     "\n\n💡 **Exemple :** *'Supprime le smartphone'*"
            )
            return [FollowupAction("action_listen")]
        
        logger.info(f"🎯 Dotation à supprimer: '{nom_dotation}'")
        
        # ==========================================
        # ÉTAPE 2 : VÉRIFIER L'EXISTENCE
        # ==========================================
        dotation_trouvee = None
        index_dotation = None
        
        for i, dotation in enumerate(dotations_list):
            dotation_name = dotation.get('dotation', '')
            if self._match_dotation(nom_dotation, dotation_name):
                dotation_trouvee = dotation
                index_dotation = i
                break
        
        if not dotation_trouvee:
            suggestions = self._get_suggestions_dotation(nom_dotation, dotations_list)
            
            message_erreur = f"❌ **La dotation '{nom_dotation}' n'a pas été trouvée.**\n\n"
            
            if suggestions:
                message_erreur += (
                    f"💡 **Dotations similaires :**\n" +
                    "\n".join([f"  • {s}" for s in suggestions])
                )
            else:
                message_erreur += (
                    f"📦 **Dotations disponibles :**\n" +
                    "\n".join([f"  • {d.get('dotation', 'N/A')}" for d in dotations_list])
                )
            
            dispatcher.utter_message(text=message_erreur)
            return []
        
        # ==========================================
        # ÉTAPE 3 : SUPPRIMER LA DOTATION
        # ==========================================
        dotations_list.pop(index_dotation)
        
        logger.info(f"✅ Dotation '{dotation_trouvee.get('dotation')}' supprimée")
        logger.info(f"📊 Dotations restantes: {len(dotations_list)}")
        
        # ==========================================
        # ÉTAPE 4 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Dotation supprimée avec succès !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"🗑️ **Dotation supprimée :** {dotation_trouvee.get('dotation')}\n\n"
        message += f"{'─' * 50}\n\n"
        
        if dotations_list:
            message += f"📦 **Dotations restantes ({len(dotations_list)}) :**\n"
            message += "\n".join([f"  • {d.get('dotation')}" for d in dotations_list])
        else:
            message += "⚠️ **Toutes les dotations ont été supprimées.**"
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 5 : METTRE À JOUR LE SLOT
        # ==========================================
        return [SlotSet("dotations_list", dotations_list), FollowupAction("verify_if_all_information_is_complet_add_ddr")]
    
    def _extraire_nom_dotation(self, message: str, dotations_existantes: List[Dict]) -> Optional[str]:
        """Extrait le nom de la dotation à supprimer"""
        
        message_lower = message.lower()
        
        # Pattern 1 : "supprime/retire/efface [la/le/l'] dotation X"
        patterns = [
            r"(?:supprime|retire|efface|enlève|enleve)\s+(?:la|le|l')?\s*(?:dotation)?\s+(.+?)(?:\s|$)",
            r"(?:dotation)\s+(.+?)(?:\s+à\s+supprimer|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                nom = match.group(1).strip()
                # Nettoyer
                nom = re.sub(r'\s+(s\'il\s+te\s+plaît|s\'il\s+vous\s+plaît|stp|svp)$', '', nom)
                if len(nom) >= 3:
                    return nom
        
        # Pattern 2 : Chercher directement une dotation existante dans le message
        for dotation in dotations_existantes:
            dotation_name = dotation.get('dotation', '')
            if dotation_name and dotation_name.lower() in message_lower:
                return dotation_name
        
        # Pattern 3 : Mots-clés courants de dotations
        dotations_keywords = [
            'smartphone', 'ordinateur', 'portable', 'pc', 'laptop',
            'badge', 'carte', 'véhicule', 'voiture', 'bureau',
            'téléphone', 'telephone', 'tablette', 'ipad',
            'écran', 'ecran', 'moniteur', 'clavier', 'souris'
        ]
        
        for keyword in dotations_keywords:
            if keyword in message_lower:
                # Chercher la dotation correspondante
                for dotation in dotations_existantes:
                    dotation_name = dotation.get('dotation', '').lower()
                    if keyword in dotation_name:
                        return dotation.get('dotation')
        
        return None
    
    def _match_dotation(self, nom_recherche: str, nom_dotation: str) -> bool:
        """Vérifie si deux noms de dotations correspondent"""
        
        from difflib import SequenceMatcher
        
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        nom_dotation_clean = remove_accents(nom_dotation.lower().strip())
        
        # Correspondance exacte
        if nom_recherche_clean == nom_dotation_clean:
            return True
        
        # Le nom recherché est contenu dans le nom de la dotation
        if nom_recherche_clean in nom_dotation_clean:
            return True
        
        # Le nom de la dotation est contenu dans la recherche
        if nom_dotation_clean in nom_recherche_clean:
            return True
        
        # Fuzzy matching (80% de similarité)
        ratio = SequenceMatcher(None, nom_recherche_clean, nom_dotation_clean).ratio()
        if ratio > 0.8:
            return True
        
        return False
    
    def _get_suggestions_dotation(self, nom_recherche: str, dotations: List[Dict]) -> List[str]:
        """Retourne des suggestions de dotations similaires"""
        
        from difflib import SequenceMatcher
        
        suggestions = []
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        
        for dotation in dotations:
            dotation_name = dotation.get('dotation', '')
            if not dotation_name:
                continue
            
            dotation_clean = remove_accents(dotation_name.lower().strip())
            ratio = SequenceMatcher(None, nom_recherche_clean, dotation_clean).ratio()
            
            if ratio > 0.4:  # Seuil de similarité
                suggestions.append((dotation_name, ratio))
        
        # Trier par score décroissant
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in suggestions[:3]]


class ActionSupprimerDotationsMultiples(Action):
    """
    Supprime PLUSIEURS dotations spécifiques
    Exemples : "supprime le smartphone et l'ordinateur", "retire badge, voiture"
    """
    
    def name(self) -> Text:
        return "action_supprimer_dotations_multiples"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        dotations_list = tracker.get_slot("dotations_list") or []
        
        if not dotations_list:
            dispatcher.utter_message(
                text="❌ **Aucune dotation à supprimer.**"
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE PLUSIEURS DOTATIONS")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Dotations actuelles: {len(dotations_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE TOUS LES NOMS
        # ==========================================
        noms_dotations = self._extraire_noms_multiples(user_message, dotations_list)
        
        if not noms_dotations or len(noms_dotations) < 2:
            dispatcher.utter_message(
                text="❓ **Quelles dotations souhaitez-vous supprimer ?**\n\n"
                     f"📦 **Dotations disponibles ({len(dotations_list)}) :**\n" +
                     "\n".join([f"  • {d.get('dotation', 'N/A')}" for d in dotations_list]) +
                     "\n\n💡 **Exemples :**\n"
                     "  • *'Supprime le smartphone et l'ordinateur'*\n"
                     "  • *'Retire badge, carte d'accès'*"
            )
            return [FollowupAction("action_listen")]
        
        logger.info(f"🎯 Dotations à supprimer: {noms_dotations}")
        
        # ==========================================
        # ÉTAPE 2 : MATCHER AVEC LES DOTATIONS EXISTANTES
        # ==========================================
        dotations_a_supprimer = []
        dotations_non_trouvees = []
        
        for nom in noms_dotations:
            trouve = False
            for dotation in dotations_list:
                dotation_name = dotation.get('dotation', '')
                if self._match_dotation(nom, dotation_name):
                    if dotation not in dotations_a_supprimer:
                        dotations_a_supprimer.append(dotation)
                    trouve = True
                    break
            
            if not trouve:
                dotations_non_trouvees.append(nom)
        
        if not dotations_a_supprimer:
            dispatcher.utter_message(
                text=f"❌ **Aucune des dotations mentionnées n'a été trouvée.**\n\n"
                     f"❌ Non trouvées : {', '.join(dotations_non_trouvees)}\n\n"
                     f"📦 Dotations disponibles :\n" +
                     "\n".join([f"  • {d.get('dotation')}" for d in dotations_list])
            )
            return []
        
        # ==========================================
        # ÉTAPE 3 : SUPPRIMER
        # ==========================================
        for dotation in dotations_a_supprimer:
            dotations_list.remove(dotation)
        
        logger.info(f"✅ {len(dotations_a_supprimer)} dotation(s) supprimée(s)")
        logger.info(f"📊 Dotations restantes: {len(dotations_list)}")
        
        # ==========================================
        # ÉTAPE 4 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **{len(dotations_a_supprimer)} dotation(s) supprimée(s) !**\n\n"
        
        if dotations_non_trouvees:
            message += (
                f"⚠️ **Dotations non trouvées :** {', '.join(dotations_non_trouvees)}\n\n"
            )
        
        message += f"{'─' * 50}\n\n"
        message += "🗑️ **Dotations supprimées :**\n"
        message += "\n".join([f"  ❌ {d.get('dotation')}" for d in dotations_a_supprimer])
        message += f"\n\n{'─' * 50}\n\n"
        
        if dotations_list:
            message += f"📦 **Dotations restantes ({len(dotations_list)}) :**\n"
            message += "\n".join([f"  • {d.get('dotation')}" for d in dotations_list])
        else:
            message += "⚠️ **Toutes les dotations ont été supprimées.**"
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 5 : METTRE À JOUR LE SLOT
        # ==========================================
        return [SlotSet("dotations_list", dotations_list), FollowupAction("verify_if_all_information_is_complet_add_ddr")]
    
    def _extraire_noms_multiples(self, message: str, dotations_existantes: List[Dict]) -> List[str]:
        """Extrait plusieurs noms de dotations"""
        
        noms = []
        message_lower = message.lower()
        
        # Pattern 1 : Chercher toutes les dotations existantes mentionnées
        for dotation in dotations_existantes:
            dotation_name = dotation.get('dotation', '')
            if dotation_name and dotation_name.lower() in message_lower:
                noms.append(dotation_name)
        
        # Pattern 2 : Mots-clés courants
        dotations_keywords = [
            'smartphone', 'ordinateur', 'portable', 'pc', 'laptop',
            'badge', 'carte', 'véhicule', 'voiture', 'bureau',
            'téléphone', 'telephone', 'tablette', 'ipad',
            'écran', 'ecran', 'moniteur', 'clavier', 'souris'
        ]
        
        for keyword in dotations_keywords:
            if keyword in message_lower:
                for dotation in dotations_existantes:
                    dotation_name = dotation.get('dotation', '')
                    if keyword in remove_accents(dotation_name.lower()):
                        if dotation_name not in noms:
                            noms.append(dotation_name)
        
        # Pattern 3 : Séparateurs "et", ","
        segments = re.split(r'\s+et\s+|,\s*', message)
        
        for segment in segments:
            segment_clean = segment.strip()
            for dotation in dotations_existantes:
                dotation_name = dotation.get('dotation', '')
                if dotation_name and dotation_name.lower() in segment_clean.lower():
                    if dotation_name not in noms:
                        noms.append(dotation_name)
        
        return noms
    
    def _match_dotation(self, nom_recherche: str, nom_dotation: str) -> bool:
        """Vérifie si deux noms de dotations correspondent"""
        
        from difflib import SequenceMatcher
        
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        nom_dotation_clean = remove_accents(nom_dotation.lower().strip())
        
        if nom_recherche_clean == nom_dotation_clean:
            return True
        
        if nom_recherche_clean in nom_dotation_clean or nom_dotation_clean in nom_recherche_clean:
            return True
        
        ratio = SequenceMatcher(None, nom_recherche_clean, nom_dotation_clean).ratio()
        return ratio > 0.8


class ActionSupprimerToutesDotations(Action):
    """
    Supprime TOUTES les dotations avec confirmation
    Exemples : "supprime toutes les dotations", "efface tout"
    """
    
    def name(self) -> Text:
        return "action_supprimer_toutes_dotations"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        dotations_list = tracker.get_slot("dotations_list") or []
        
        if not dotations_list:
            dispatcher.utter_message(
                text="ℹ️ **Aucune dotation à supprimer.**\n\nLa liste est déjà vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE TOUTES LES DOTATIONS")
        logger.info(f"📊 Dotations actuelles: {len(dotations_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # VÉRIFICATION : CONFIRMATION EXPLICITE
        # ==========================================
        patterns_confirmation = [
            r"\btoutes\s+les\s+dotations?\b",
            r"\btout\b",
            r"\btoutes?\b",
            r"\bl'ensemble\b",
            r"\btotalité\b",
            r"\breset\b",
        ]
        
        confirmation_explicite = any(
            re.search(pattern, user_message) 
            for pattern in patterns_confirmation
        )
        
        if not confirmation_explicite:
            dispatcher.utter_message(
                text=f"⚠️ **Êtes-vous sûr(e) de vouloir supprimer TOUTES les dotations ?**\n\n"
                     f"📊 **{len(dotations_list)} dotation(s) seront supprimées :**\n" +
                     "\n".join([f"  • {d.get('dotation')}" for d in dotations_list]) +
                     "[Oui supprime tout, Annuler la suppression](action_supprimer_toutes_dotations)\n\n"
            )
            return []
        
        # ==========================================
        # SAUVEGARDER POUR LE MESSAGE
        # ==========================================
        nb_dotations = len(dotations_list)
        dotations_supprimees = dotations_list.copy()
        
        # ==========================================
        # SUPPRESSION TOTALE
        # ==========================================
        dotations_list = []
        
        # ==========================================
        # MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Toutes les dotations ont été supprimées !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"🗑️ **{nb_dotations} dotation(s) supprimée(s) :**\n\n"
        message += "\n".join([f"  ❌ {d.get('dotation')}" for d in dotations_supprimees])
        message += f"\n\n{'─' * 50}\n\n"
        message += "⚠️ **La liste des dotations est maintenant vide.**"
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"✅ Toutes les dotations supprimées")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # METTRE À JOUR LE SLOT
        # ==========================================
        return [
            SlotSet("dotations_list", []),
            SlotSet("dotation", None),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]

class ActionRemplacerDotation(Action):
    """
    Remplace une dotation par une autre
    Exemples : 
    - "remplace le smartphone par une tablette"
    - "change l'ordinateur portable par un PC fixe"
    """
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "action_remplacer_dotation"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        dotations_list = tracker.get_slot("dotations_list") or []
        
        if not dotations_list:
            dispatcher.utter_message(
                text="❌ **Aucune dotation à remplacer.**\n\nLa liste est vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔄 REMPLACEMENT D'UNE DOTATION")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Dotations actuelles: {len(dotations_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE L'ANCIENNE ET LA NOUVELLE DOTATION
        # ==========================================
        ancienne_dotation, nouvelle_dotation = self._extraire_remplacement(
            user_message, 
            dotations_list
        )
        
        if not ancienne_dotation:
            dispatcher.utter_message(
                text="❓ **Quelle dotation souhaitez-vous remplacer ?**\n\n"
                     f"📦 **Dotations disponibles :**\n" +
                     "\n".join([f"  • {d.get('dotation')}" for d in dotations_list]) +
                     "\n\n💡 **Exemple :** *'Remplace le smartphone par une tablette'*"
            )
            return []
        
        if not nouvelle_dotation:
            dispatcher.utter_message(
                text=f"❓ **Par quelle dotation souhaitez-vous remplacer '{ancienne_dotation}' ?**\n\n"
                     f"💡 **Exemple :** *'Remplace-le par un ordinateur portable'*"
            )
            return []
        
        logger.info(f"🎯 Ancienne dotation: '{ancienne_dotation}'")
        logger.info(f"🎯 Nouvelle dotation: '{nouvelle_dotation}'")
        
        # ==========================================
        # ÉTAPE 2 : VÉRIFIER L'EXISTENCE DE L'ANCIENNE
        # ==========================================
        dotation_trouvee = None
        index_dotation = None
        
        for i, dotation in enumerate(dotations_list):
            dotation_name = dotation.get('dotation', '')
            if self._match_dotation(ancienne_dotation, dotation_name):
                dotation_trouvee = dotation
                index_dotation = i
                break
        
        if not dotation_trouvee:
            suggestions = self._get_suggestions_dotation(ancienne_dotation, dotations_list)
            
            message_erreur = f"❌ **La dotation '{ancienne_dotation}' n'a pas été trouvée.**\n\n"
            
            if suggestions:
                message_erreur += (
                    f"💡 **Dotations similaires :**\n" +
                    "\n".join([f"  • {s}" for s in suggestions])
                )
            else:
                message_erreur += (
                    f"📦 **Dotations disponibles :**\n" +
                    "\n".join([f"  • {d.get('dotation')}" for d in dotations_list])
                )
            
            dispatcher.utter_message(text=message_erreur)
            return []
        
        # ==========================================
        # ÉTAPE 3 : VALIDER LA NOUVELLE DOTATION AVEC LE BACKEND
        # ==========================================
        dotations_db = self.backend.get_dotation_listes() or []
        
        if not dotations_db:
            dispatcher.utter_message(
                text="❌ **Impossible de récupérer la liste des dotations depuis la base.**"
            )
            return []
        
        nouvelle_dotation_validee = None
        nouvelle_dotation_id = None
        matches = []
        
        nouvelle_dotation_norm = remove_accents(nouvelle_dotation.lower().strip())
        
        logger.info(f"🔍 Validation de la nouvelle dotation: '{nouvelle_dotation}'")
        
        for d in dotations_db:
            nom_dotation_db = d.get('DotationOption', '')
            dotation_id = d.get('IdDotation')
            
            if not nom_dotation_db or not dotation_id:
                continue
            
            nom_dotation_norm = remove_accents(nom_dotation_db.lower())
            
            # STRATÉGIE 1: Correspondance exacte
            if nouvelle_dotation_norm == nom_dotation_norm:
                logger.info(f"✅ Correspondance exacte: {nom_dotation_db} (ID: {dotation_id})")
                nouvelle_dotation_validee = nom_dotation_db
                nouvelle_dotation_id = dotation_id
                break
            
            # STRATÉGIE 2: Contenu
            if nouvelle_dotation_norm in nom_dotation_norm:
                score = len(nouvelle_dotation_norm) / len(nom_dotation_norm)
                matches.append((nom_dotation_db, dotation_id, score))
                continue
            
            if nom_dotation_norm in nouvelle_dotation_norm:
                score = len(nom_dotation_norm) / len(nouvelle_dotation_norm)
                matches.append((nom_dotation_db, dotation_id, score))
                continue
            
            # STRATÉGIE 3: Fuzzy matching
            ratio = SequenceMatcher(None, nouvelle_dotation_norm, nom_dotation_norm).ratio()
            if ratio > 0.6:
                matches.append((nom_dotation_db, dotation_id, ratio))
        
        # Si pas de correspondance exacte, vérifier les matches
        if not nouvelle_dotation_validee:
            matches.sort(key=lambda x: x[2], reverse=True)
            
            logger.info(f"📊 {len(matches)} correspondance(s) trouvée(s)")
            for match in matches[:3]:
                logger.info(f"  • {match[0]} (ID: {match[1]}, score: {match[2]:.2f})")
            
            # Une seule correspondance claire
            if len(matches) == 1 or (len(matches) > 1 and matches[0][2] - matches[1][2] > 0.15):
                nouvelle_dotation_validee, nouvelle_dotation_id, score = matches[0]
                logger.info(f"✅ Dotation validée: {nouvelle_dotation_validee} (score: {score:.2f})")
            
            # Plusieurs correspondances ambiguës
            elif len(matches) > 1:
                propositions = [m[0] for m in matches[:5]]
                dispatcher.utter_message(
                    text=f"🔍 **Plusieurs dotations correspondent à '{nouvelle_dotation}'.**\n\n"
                         f"**Laquelle souhaitez-vous utiliser ?**\n\n" +
                         "\n".join([f"  • {p}" for p in propositions]) +
                         "\n\n💬 Veuillez préciser."
                )
                return []
            
            # Aucune correspondance
            else:
                suggestions_db = self._get_suggestions_from_db(nouvelle_dotation, dotations_db)
                
                message_erreur = f"❌ **La dotation '{nouvelle_dotation}' n'existe pas.**\n\n"
                
                if suggestions_db:
                    message_erreur += (
                        f"💡 **Dotations similaires disponibles :**\n" +
                        "\n".join([f"  • {s}" for s in suggestions_db[:10]])
                    )
                else:
                    message_erreur += "📝 Veuillez vérifier l'orthographe."
                
                dispatcher.utter_message(text=message_erreur)
                return []
        
        # ==========================================
        # ÉTAPE 4 : VÉRIFIER QUE LA NOUVELLE DOTATION N'EST PAS DÉJÀ DANS LA LISTE
        # ==========================================
        for dotation in dotations_list:
            if dotation.get('dotation_id') == nouvelle_dotation_id:
                dispatcher.utter_message(
                    text=f"⚠️ **La dotation '{nouvelle_dotation_validee}' est déjà dans votre liste.**\n\n"
                         f"💡 Veuillez choisir une autre dotation ou supprimer d'abord l'ancienne."
                )
                return []
        
        # ==========================================
        # ÉTAPE 5 : REMPLACER
        # ==========================================
        dotations_list[index_dotation] = {
            'dotation': nouvelle_dotation_validee,
            'dotation_id': nouvelle_dotation_id
        }
        
        logger.info(f"✅ Remplacement effectué:")
        logger.info(f"   Ancienne: '{dotation_trouvee.get('dotation')}' (ID: {dotation_trouvee.get('dotation_id')})")
        logger.info(f"   Nouvelle: '{nouvelle_dotation_validee}' (ID: {nouvelle_dotation_id})")
        
        # ==========================================
        # ÉTAPE 6 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Dotation remplacée avec succès !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"❌ **Ancienne dotation :** {dotation_trouvee.get('dotation')}\n"
        message += f"✅ **Nouvelle dotation :** {nouvelle_dotation_validee}\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"📦 **Liste mise à jour ({len(dotations_list)}) :**\n"
        message += "\n".join([f"  • {d.get('dotation')}" for d in dotations_list])
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 7 : METTRE À JOUR LE SLOT
        # ==========================================
        return [SlotSet("dotations_list", dotations_list), FollowupAction("verify_if_all_information_is_complet_add_ddr")]
    
    def _extraire_remplacement(
        self, 
        message: str, 
        dotations_existantes: List[Dict]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extrait l'ancienne et la nouvelle dotation"""
        
        message_lower = message.lower()
        
        logger.info(f"🔍 Extraction du remplacement...")
        
        # Pattern principal : "remplace X par Y"
        patterns = [
            # "remplace le smartphone par une tablette"
            r"(?:remplace|remplacer|change|changer|modifie|modifier)\s+(?:le|la|l')?\s*(.+?)\s+par\s+(?:le|la|l'|un|une)?\s*(.+?)(?:\s|$)",
            
            # "change X avec Y"
            r"(?:remplace|change|modifie)\s+(.+?)\s+avec\s+(.+?)(?:\s|$)",
            
            # "X devient Y" ou "X sera Y"
            r"(.+?)\s+(?:devient|sera|deviendra)\s+(.+?)(?:\s|$)",
        ]
        
        for pattern_idx, pattern in enumerate(patterns, 1):
            match = re.search(pattern, message_lower)
            if match:
                ancienne = match.group(1).strip()
                nouvelle = match.group(2).strip()
                
                logger.info(f"  ✓ Pattern {pattern_idx} match:")
                logger.info(f"    Ancienne: '{ancienne}'")
                logger.info(f"    Nouvelle: '{nouvelle}'")
                
                # Nettoyer les préfixes
                ancienne = re.sub(r'^(le|la|l\'|un|une|les|des)\s+', '', ancienne)
                nouvelle = re.sub(r'^(le|la|l\'|un|une|les|des)\s+', '', nouvelle)
                
                # Nettoyer les suffixes
                ancienne = re.sub(r'\s+(par|avec|de)$', '', ancienne)
                nouvelle = re.sub(r'\s+(s\'il\s+te\s+plaît|s\'il\s+vous\s+plaît|stp|svp)$', '', nouvelle)
                
                logger.info(f"  ✓ Après nettoyage:")
                logger.info(f"    Ancienne: '{ancienne}'")
                logger.info(f"    Nouvelle: '{nouvelle}'")
                
                if len(ancienne) >= 3 and len(nouvelle) >= 3:
                    return (ancienne, nouvelle)
        
        logger.warning("  ❌ Aucun pattern de remplacement trouvé")
        return (None, None)
    
    def _match_dotation(self, nom_recherche: str, nom_dotation: str) -> bool:
        """Vérifie si deux noms de dotations correspondent"""
        
        from difflib import SequenceMatcher
        
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        nom_dotation_clean = remove_accents(nom_dotation.lower().strip())
        
        # Correspondance exacte
        if nom_recherche_clean == nom_dotation_clean:
            return True
        
        # Contenu
        if nom_recherche_clean in nom_dotation_clean or nom_dotation_clean in nom_recherche_clean:
            return True
        
        # Fuzzy matching (75%)
        ratio = SequenceMatcher(None, nom_recherche_clean, nom_dotation_clean).ratio()
        return ratio > 0.75
    
    def _get_suggestions_dotation(self, nom_recherche: str, dotations: List[Dict]) -> List[str]:
        """Retourne des suggestions de dotations similaires"""
        
        from difflib import SequenceMatcher
        
        suggestions = []
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        
        for dotation in dotations:
            dotation_name = dotation.get('dotation', '')
            if not dotation_name:
                continue
            
            dotation_clean = remove_accents(dotation_name.lower().strip())
            ratio = SequenceMatcher(None, nom_recherche_clean, dotation_clean).ratio()
            
            if ratio > 0.4:  # Seuil de similarité
                suggestions.append((dotation_name, ratio))
        
        # Trier par score décroissant
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in suggestions[:3]]
    
    def _get_suggestions_from_db(self, nom_recherche: str, dotations_db: List[Dict]) -> List[str]:
        """Retourne des suggestions depuis la base de données"""
        
        from difflib import SequenceMatcher
        
        suggestions = []
        nom_recherche_clean = remove_accents(nom_recherche.lower().strip())
        
        for d in dotations_db:
            dotation_name = d.get('DotationOption', '')
            if not dotation_name:
                continue
            
            dotation_clean = remove_accents(dotation_name.lower())
            
            # Calculer la similarité
            ratio = SequenceMatcher(None, nom_recherche_clean, dotation_clean).ratio()
            
            # Chercher aussi le premier mot
            first_word = nom_recherche_clean.split()[0] if nom_recherche_clean.split() else ""
            if first_word and first_word in dotation_clean:
                ratio = max(ratio, 0.5)
            
            if ratio > 0.4:
                suggestions.append((dotation_name, ratio))
        
        # Trier par score décroissant
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in suggestions[:10]]

class ActionExtractDotationsSecours(Action):
    """Extraction de secours des dotations par pattern matching"""
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "action_extract_dotations_secours"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        # Vérifier si des dotations ont déjà été extraites
        dotations_nlu = [e.get('value') for e in entities if e.get('entity') == 'dotation']
        
        if dotations_nlu:
            logger.info(f"✅ NLU a déjà extrait {len(dotations_nlu)} dotation(s)")
            return []
        
        # Pattern matching de secours
        logger.info("🔍 Extraction de secours des dotations...")
        
        # Récupérer la liste des dotations de la base
        dotations_db = self.backend.get_dotation_listes() or []
        
        if not dotations_db:
            return []
        
        dotations_trouvees = []
        message_lower = remove_accents(message.lower())
        
        # Chercher chaque dotation de la base dans le message
        for d in dotations_db:
            nom_dotation = d.get('DotationOption', '')
            if not nom_dotation:
                continue
            
            nom_dotation_norm = remove_accents(nom_dotation.lower())
            
            # Vérifier si la dotation est mentionnée dans le message
            if nom_dotation_norm in message_lower:
                dotations_trouvees.append({
                    'dotation': nom_dotation,
                    'dotation_id': d.get('IdDotation')
                })
                logger.info(f"  ✅ Trouvé par pattern: {nom_dotation}")
        
        if dotations_trouvees:
            # Mettre à jour la liste des dotations
            dotations_list = tracker.get_slot("dotations_list") or []
            
            for dotation in dotations_trouvees:
                # Éviter les doublons
                if not any(d.get('dotation_id') == dotation['dotation_id'] for d in dotations_list):
                    dotations_list.append(dotation)
            
            logger.info(f"✅ {len(dotations_trouvees)} dotation(s) extraites par secours")
            
            return [SlotSet("dotations_list", dotations_list)]
        
        return []