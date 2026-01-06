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

class ActionVerificationEncadreur(Action):
    """Valide l'encadreur avec recherche intelligente optimisée"""
    
    def __init__(self):
        super().__init__()
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_encadreur"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        nom_encadreur = tracker.get_slot("nom_encadreur")
        user_message = tracker.latest_message.get('text', '')

        logger.info(f"🔍 verification_encadreur - message: '{user_message}'")
        logger.info(f"   Slot nom_encadreur: '{nom_encadreur}'")
        
        if not nom_encadreur or len(str(nom_encadreur).strip()) < 3:
            return [SlotSet("nom_encadreur", None), SlotSet("poste_encadreur", None)]
        
        # ==========================================
        # RECHERCHE INTELLIGENTE AVEC FUZZY MATCHING
        # ==========================================
        list_matching_users = self._recherche_intelligente(nom_encadreur)
        
        logger.info(f"📊 Nombre de correspondances trouvées: {len(list_matching_users)}")
        
        # ==========================================
        # CAS 1 : UNE SEULE CORRESPONDANCE CLAIRE
        # ==========================================
        if len(list_matching_users) == 1:
            user_details = list_matching_users[0]['user_details']
            fullname = user_details.get('FullName', '')
            poste = user_details.get('Poste', '')
            score = list_matching_users[0].get('match_score', 100)
            
            logger.info(f"✅ Encadreur trouvé - Nom: {fullname}, Poste: {poste}, Score: {score:.1f}%")
            
            return [
                SlotSet("nom_encadreur", fullname),
                SlotSet("poste_encadreur", poste)
            ]
        
        # ==========================================
        # CAS 2 : PLUSIEURS CORRESPONDANCES (MAX 5)
        # ==========================================
        if len(list_matching_users) > 1:
            # 🆕 NOUVEAU : Vérifier si le premier résultat est significativement meilleur
            best_match = list_matching_users[0]
            second_match = list_matching_users[1] if len(list_matching_users) > 1 else None
            
            # Si le meilleur score est 95+ ET 20 points au-dessus du 2e → accepter automatiquement
            if (best_match['match_score'] >= 95 and 
                second_match and 
                best_match['match_score'] - second_match['match_score'] >= 20):
                
                user_details = best_match['user_details']
                fullname = user_details.get('FullName', '')
                poste = user_details.get('Poste', '')
                
                logger.info(f"✅ Correspondance dominante acceptée automatiquement: {fullname} ({best_match['match_score']:.1f}%)")
                
                return [
                    SlotSet("nom_encadreur", fullname),
                    SlotSet("poste_encadreur", poste)
                ]
            
            # Sinon, demander clarification
            top_matches = list_matching_users[:5]
            
            names_with_scores = []
            for match in top_matches:
                user_details = match['user_details']
                fullname = user_details.get('FullName', '')
                poste = user_details.get('Poste', '')
                names_with_scores.append(f"{fullname}")
            
            logger.info(f"🔍 Top {len(top_matches)} correspondances:")
            for i, match in enumerate(top_matches, 1):
                logger.info(f"   {i}. {match['user_details'].get('FullName')} - Score: {match.get('match_score', 0):.1f}%")
            
            dispatcher.utter_message(
                text=f"🔍 **Plusieurs encadreurs correspondent à '{nom_encadreur}'**\n\n"
                     f"Voici les {len(top_matches)} résultats les plus proches:\n\n" +
                     f"[{', '.join([name for name in names_with_scores])}](verification_encadreur)\n\n" +
                     f"\n\n💬 Veuillez préciser le nom complet exact."
            )
            
            return [
                SlotSet("nom_encadreur", None),
                SlotSet("poste_encadreur", None)
            ]

        # ==========================================
        # CAS 3 : AUCUNE CORRESPONDANCE
        # ==========================================
        logger.warning(f"❌ Aucun encadreur trouvé pour: {nom_encadreur}")
        
        suggestions = self._get_suggestions(nom_encadreur)
        
        if suggestions:
            dispatcher.utter_message(
                text=f"❌ Aucun encadreur trouvé pour **'{nom_encadreur}'**.\n\n"
                     f"💡 Suggestions (noms similaires):\n [" +
                     ",".join([f"{s}" for s in suggestions[:5]]) +
                     f"](verification_encadreur)\n\n📝 Veuillez vérifier l'orthographe et réessayer avec le nom complet."
            )
        else:
            dispatcher.utter_message(
                text=f"❌ Aucun encadreur trouvé pour **'{nom_encadreur}'**.\n\n"
                     f"📝 Veuillez indiquer le nom et prénom complet (ex: Jean Dupont)."
            )
        
        return [
            SlotSet("nom_encadreur", None),
            SlotSet("poste_encadreur", None)
        ]
    
    def _recherche_intelligente(self, nom_recherche: str) -> List[Dict]:
        """
        Recherche intelligente avec fuzzy matching optimisé
        
        AMÉLIORATIONS:
        - Seuils adaptatifs selon le type de match
        - Filtrage plus strict des faux positifs
        - Priorité aux noms complets vs partiels
        """
        from rapidfuzz import fuzz, process
        
        users = self.backend.get_all_user_details() or []
        
        if not users:
            logger.warning("⚠️ Impossible de récupérer la liste des utilisateurs")
            return []
        
        nom_recherche_norm = self._remove_accents(nom_recherche.lower().strip())
        tokens_recherche = set(nom_recherche_norm.split())
        
        logger.info(f"🔍 Recherche pour: '{nom_recherche}' (tokens: {tokens_recherche})")
        logger.info(f"📊 Base de données: {len(users)} utilisateurs")
        
        # ==========================================
        # PHASE 1: CORRESPONDANCES EXACTES
        # ==========================================
        exact_matches = []
        
        for user in users:
            fullname = user.get('FullName', '')
            if not fullname or len(fullname) < 2:
                continue
            
            fullname_norm = self._remove_accents(fullname.lower().strip())
            
            # CORRESPONDANCE EXACTE (avec casse)
            if nom_recherche.lower().strip() == fullname.lower().strip():
                exact_matches.append({
                    'user_details': user,
                    'match_score': 100.0,
                    'method': 'exact'
                })
            # CORRESPONDANCE EXACTE SANS ACCENTS
            elif nom_recherche_norm == fullname_norm:
                exact_matches.append({
                    'user_details': user,
                    'match_score': 98.0,
                    'method': 'exact_no_accent'
                })
        
        if exact_matches:
            logger.info(f"✅ Correspondance exacte trouvée: {exact_matches[0]['user_details'].get('FullName')}")
            return exact_matches
        
        # ==========================================
        # PHASE 2: RECHERCHE FUZZY OPTIMISÉE
        # ==========================================
        fuzzy_matches = []
        
        for user in users:
            fullname = user.get('FullName', '')
            if not fullname or len(fullname) < 2:
                continue
            
            fullname_norm = self._remove_accents(fullname.lower().strip())
            tokens_fullname = set(fullname_norm.split())
            
            # 🆕 FILTRE PRÉ-CALCUL: Ignorer si < 50% tokens communs
            common_tokens = tokens_recherche.intersection(tokens_fullname)
            if len(common_tokens) == 0 or len(common_tokens) / max(len(tokens_recherche), 1) < 0.4:
                continue
            
            best_score = 0
            best_method = None
            
            # TOKEN SORT RATIO (gère inversions) - SEUIL ÉLEVÉ
            score_token_sort = fuzz.token_sort_ratio(nom_recherche_norm, fullname_norm)
            if score_token_sort >= 90:  # 🆕 Augmenté de 85 → 90
                best_score = score_token_sort
                best_method = 'token_sort'
            
            # PARTIAL RATIO (noms partiels) - SEUIL MOYEN
            score_partial = fuzz.partial_ratio(nom_recherche_norm, fullname_norm)
            if score_partial >= 85:  # 🆕 Augmenté de 80 → 85
                adjusted_score = score_partial * 0.88  # 🆕 Réduit de 0.9 → 0.88
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_method = 'partial'
            
            # TOKEN SET RATIO (mots manquants) - SEUIL BAS
            score_token_set = fuzz.token_set_ratio(nom_recherche_norm, fullname_norm)
            if score_token_set >= 80:  # 🆕 Augmenté de 75 → 80
                adjusted_score = score_token_set * 0.82  # 🆕 Réduit de 0.85 → 0.82
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_method = 'token_set'
            
            # 🆕 SEUIL FINAL AUGMENTÉ: 80 au lieu de 70
            if best_score >= 80:
                fuzzy_matches.append({
                    'user_details': user,
                    'match_score': best_score,
                    'method': best_method
                })
        
        # ==========================================
        # TRIER ET LIMITER
        # ==========================================
        fuzzy_matches.sort(key=lambda x: x['match_score'], reverse=True)
        top_matches = fuzzy_matches[:5]
        
        logger.info(f"📊 Résultats fuzzy: {len(top_matches)} correspondance(s)")
        for i, match in enumerate(top_matches, 1):
            logger.info(
                f"   {i}. {match['user_details'].get('FullName')} "
                f"(Score: {match['match_score']:.1f}%, Méthode: {match['method']})"
            )
        
        return top_matches
    
    def _get_suggestions(self, nom_recherche: str) -> List[str]:
        """Retourne des suggestions de noms similaires"""
        from rapidfuzz import fuzz, process
        
        users = self.backend.get_all_user_details() or []
        if not users:
            return []
        
        nom_recherche_norm = self._remove_accents(nom_recherche.lower().strip())
        suggestions = []
        
        for user in users:
            fullname = user.get('FullName', '')
            if not fullname:
                continue
            
            fullname_norm = self._remove_accents(fullname.lower().strip())
            score = fuzz.token_sort_ratio(nom_recherche_norm, fullname_norm)
            
            if score >= 60:  # 🆕 Augmenté de 50 → 60
                suggestions.append({
                    'name': fullname,
                    'score': score
                })
        
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return [s['name'] for s in suggestions[:5]]
    
    def _remove_accents(self, text: str) -> str:
        """Supprime les accents d'une chaîne de caractères"""
        import unicodedata
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        ).lower().strip()