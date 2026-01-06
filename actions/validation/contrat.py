import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset, ActiveLoop, FollowupAction
from difflib import SequenceMatcher
import re
from datetime import datetime, date, timedelta
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Import the backend service
from actions.services.ddr_service import get_backend_service

# ============================================================
# DICTIONNAIRES DE CONVERSION
# ============================================================

MOIS_FR = {
    'janvier': 1, 'jan': 1,
    'février': 2, 'fevrier': 2, 'fév': 2, 'fev': 2,
    'mars': 3, 'mar': 3,
    'avril': 4, 'avr': 4,
    'mai': 5,
    'juin': 6, 'jun': 6,
    'juillet': 7, 'juil': 7, 'jul': 7,
    'août': 8, 'aout': 8, 'aoû': 8,
    'septembre': 9, 'sept': 9, 'sep': 9,
    'octobre': 10, 'oct': 10,
    'novembre': 11, 'nov': 11,
    'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12
}

JOURS_TEXTE = {
    'premier': 1, '1er': 1, '1ere': 1, '1ère': 1,
    'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5,
    'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9, 'dix': 10,
    'onze': 11, 'douze': 12, 'treize': 13, 'quatorze': 14,
    'quinze': 15, 'seize': 16, 'dix-sept': 17, 'dix-huit': 18,
    'dix-neuf': 19, 'vingt': 20, 'vingt-et-un': 21, 'vingt-deux': 22,
    'vingt-trois': 23, 'vingt-quatre': 24, 'vingt-cinq': 25,
    'vingt-six': 26, 'vingt-sept': 27, 'vingt-huit': 28,
    'vingt-neuf': 29, 'trente': 30, 'trente-et-un': 31
}


def get_current_year() -> int:
    """Retourne l'année courante"""
    return datetime.now().year


def parse_jour_texte(jour_str: str) -> Optional[int]:
    """Convertit un jour en texte en nombre"""
    jour_str = jour_str.lower().strip()
    
    if jour_str.isdigit():
        jour = int(jour_str)
        return jour if 1 <= jour <= 31 else None
    
    if jour_str in JOURS_TEXTE:
        return JOURS_TEXTE[jour_str]
    
    match = re.match(r'^(\d+)(?:er|ère|ere|eme|ème|e)?$', jour_str)
    if match:
        jour = int(match.group(1))
        return jour if 1 <= jour <= 31 else None
    
    return None


def parse_mois_texte(mois_str: str) -> Optional[int]:
    """Convertit un mois en texte en nombre"""
    mois_str = mois_str.lower().strip()
    
    if mois_str.isdigit():
        mois = int(mois_str)
        return mois if 1 <= mois <= 12 else None
    
    return MOIS_FR.get(mois_str)


def extract_date_from_text(text: str) -> Optional[str]:
    """
    Extrait une date d'un texte et la retourne au format DD/MM/YYYY
    
    Formats acceptés:
    - "15/01/2025", "15-01-2025"
    - "15 janvier 2025", "15 janvier"
    - "premier janvier 2026", "premier janvier"
    - "12 décembre 2026"
    
    Si l'année n'est pas mentionnée, utilise l'année courante
    """
    if not text:
        return None
    
    text = text.lower().strip()
    logger.info(f"🔍 Extraction date depuis: '{text}'")
    
    # Pattern 1: Format numérique (DD/MM/YYYY)
    pattern_num = r'\b(\d{1,2})[\s/.-](\d{1,2})[\s/.-](\d{4})\b'
    match = re.search(pattern_num, text)
    if match:
        jour, mois, annee = match.groups()
        try:
            date_obj = datetime(int(annee), int(mois), int(jour))
            result = date_obj.strftime('%d/%m/%Y')
            logger.info(f"✓ Date numérique: {result}")
            return result
        except ValueError:
            pass
    
    # Pattern 2: Format texte avec année
    months_pattern = '|'.join(MOIS_FR.keys())
    pattern_texte_annee = rf'\b(\d{{1,2}}|premier|1er|' + \
                          r'deux|trois|quatre|cinq|six|sept|huit|neuf|dix|' + \
                          r'onze|douze|treize|quatorze|quinze|seize|' + \
                          r'vingt[- ]?(?:et[- ]?un|deux|trois|quatre|cinq|six|sept|huit|neuf)?|' + \
                          r'trente[- ]?(?:et[- ]?un)?)' + \
                          rf'\s+({months_pattern})\s+(\d{{4}})\b'
    
    match = re.search(pattern_texte_annee, text, re.IGNORECASE)
    if match:
        jour_str, mois_str, annee_str = match.groups()
        jour = parse_jour_texte(jour_str)
        mois = parse_mois_texte(mois_str)
        annee = int(annee_str) if annee_str.isdigit() else None
        
        if jour and mois and annee and 2000 <= annee <= 2100:
            try:
                date_obj = datetime(annee, mois, jour)
                result = date_obj.strftime('%d/%m/%Y')
                logger.info(f"✓ Date texte+année: {result}")
                return result
            except ValueError:
                pass
    
    # Pattern 3: Format texte SANS année (utilise année courante)
    pattern_texte_sans_annee = rf'\b(\d{{1,2}}|premier|1er|' + \
                               r'deux|trois|quatre|cinq|six|sept|huit|neuf|dix|' + \
                               r'onze|douze|treize|quatorze|quinze|seize|' + \
                               r'vingt[- ]?(?:et[- ]?un|deux|trois|quatre|cinq|six|sept|huit|neuf)?|' + \
                               r'trente[- ]?(?:et[- ]?un)?)' + \
                               rf'\s+({months_pattern})\b(?!\s+\d{{4}})'
    
    match = re.search(pattern_texte_sans_annee, text, re.IGNORECASE)
    if match:
        jour_str, mois_str = match.groups()
        jour = parse_jour_texte(jour_str)
        mois = parse_mois_texte(mois_str)
        annee = get_current_year()
        
        if jour and mois:
            try:
                date_obj = datetime(annee, mois, jour)
                result = date_obj.strftime('%d/%m/%Y')
                logger.info(f"✓ Date texte sans année: {result} (année {annee} ajoutée)")
                return result
            except ValueError:
                pass
    
    # Pattern 4: Format numérique sans année (DD/MM)
    pattern_num_sans_annee = r'\b(\d{1,2})[\s/.-](\d{1,2})\b(?!\s*[\s/.-]\s*\d{4})'
    match = re.search(pattern_num_sans_annee, text)
    if match:
        jour, mois = match.groups()
        annee = get_current_year()
        try:
            date_obj = datetime(annee, int(mois), int(jour))
            result = date_obj.strftime('%d/%m/%Y')
            logger.info(f"✓ Date DD/MM: {result} (année {annee} ajoutée)")
            return result
        except ValueError:
            pass
    
    logger.warning(f"❌ Aucune date trouvée dans: '{text}'")
    return None


def is_date_future(date_str: str, include_today: bool = False) -> bool:
    """
    Vérifie si une date est dans le futur
    
    Args:
        date_str: Date au format DD/MM/YYYY
        include_today: Si True, accepte la date d'aujourd'hui
    
    Returns:
        True si la date est future (ou aujourd'hui si include_today=True), False sinon
    """
    if not date_str:
        return False
    
    try:
        date_obj = datetime.strptime(date_str, '%d/%m/%Y').date()
        today = date.today()
        
        if include_today:
            return date_obj >= today
        else:
            return date_obj > today
            
    except ValueError as e:
        logger.error(f"Erreur parsing date '{date_str}': {e}")
        return False


def get_date_difference_message(date_str: str) -> str:
    """
    Retourne un message expliquant la différence entre la date et aujourd'hui
    
    Args:
        date_str: Date au format DD/MM/YYYY
    
    Returns:
        Message formaté (ex: "il y a 5 jours", "dans 10 jours")
    """
    try:
        date_obj = datetime.strptime(date_str, '%d/%m/%Y').date()
        today = date.today()
        diff = (date_obj - today).days
        
        if diff == 0:
            return "aujourd'hui"
        elif diff == -1:
            return "hier"
        elif diff == 1:
            return "demain"
        elif diff < 0:
            return f"il y a {abs(diff)} jours"
        else:
            return f"dans {diff} jours"
            
    except ValueError:
        return ""


def get_tomorrow_date() -> str:
    """Retourne la date de demain au format DD/MM/YYYY"""
    tomorrow = date.today() + timedelta(days=1)
    return tomorrow.strftime('%d/%m/%Y')


def text_to_number_fr(text: str) -> int:
    """Convertit un texte en nombre (supporte les nombres français)"""
    text = str(text).strip().lower()
    
    # Dictionnaire de conversion
    numbers = {
        'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4,
        'cinq': 5, 'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9,
        'dix': 10, 'onze': 11, 'douze': 12, 'treize': 13,
        'quatorze': 14, 'quinze': 15, 'seize': 16,
        'vingt': 20, 'trente': 30, 'quarante': 40,
        'cinquante': 50, 'soixante': 60, 'cent': 100,
        'mille': 1000
    }
    
    # Si c'est déjà un nombre
    if text.isdigit():
        return int(text)
    
    # Si c'est un mot
    if text in numbers:
        return numbers[text]
    
    # Sinon, essayer de convertir directement
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"Impossible de convertir '{text}' en nombre")


def extract_effectif_number(value: str) -> Optional[int]:
    """
    Extrait un nombre d'effectif de différents formats.
    
    Accepte :
    - "2" → 2
    - "2 personnes" → 2
    - "deux" → 2
    - "deux personnes" → 2
    - "effectif de 5" → 5
    
    Rejette :
    - "AG01" (code exploitation)
    - "00" (code exploitation)
    """
    if not value:
        return None
    
    value_str = str(value).strip().lower()
    logger.info(f"🔍 extract_effectif_number - Traitement de: '{value_str}'")
    
    # Rejeter codes d'exploitation
    if re.match(r'^(00|AG\d{2}|US\d{2})', value_str, re.IGNORECASE):
        logger.info(f"⚠️ Rejeté: code d'exploitation détecté")
        return None
    
    # Chercher un nombre (priorité)
    digit_match = re.search(r'\b(\d+)\b', value_str)
    if digit_match:
        effectif_int = int(digit_match.group(1))
        logger.info(f"✓ Nombre extrait via regex: {effectif_int}")
        return effectif_int
    
    # Chercher un mot-nombre français
    cleaned = re.sub(r'\b(personne|personnes|effectif|de|d\')\b', '', value_str).strip()
    
    word_numbers = {
        'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4,
        'cinq': 5, 'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9,
        'dix': 10, 'onze': 11, 'douze': 12, 'treize': 13,
        'quatorze': 14, 'quinze': 15, 'seize': 16, 'dix-sept': 17,
        'dix-huit': 18, 'dix-neuf': 19, 'vingt': 20
    }
    
    for word, num in word_numbers.items():
        if word in cleaned:
            logger.info(f"✓ Mot-nombre trouvé: '{word}' → {num}")
            return num
    
    # Dernière tentative
    try:
        return text_to_number_fr(cleaned)
    except (ValueError, TypeError):
        logger.warning(f"❌ Impossible d'extraire un nombre de: '{value_str}'")
        return None


def extract_number_from_context(message: str, keywords: List[str]) -> Optional[int]:
    """Extrait un nombre du contexte basé sur des mots-clés"""
    message_lower = message.lower()
    
    # Chercher un nombre près des mots-clés
    for keyword in keywords:
        if keyword in message_lower:
            # Chercher un nombre dans les 20 caractères suivants
            start_idx = message_lower.find(keyword)
            context = message_lower[start_idx:start_idx + 50]
            
            # Regex pour trouver un nombre
            match = re.search(r'\b(\d+)\b', context)
            if match:
                return int(match.group(1))
    
    return None


class ActionVerificationContrat(Action):
    """Valide le contrat (effectif, dates, durée, nature)"""
    
    def __init__(self):
        super().__init__()
        self.backend = get_backend_service()
    
    def name(self) -> Text:
        return "verification_contrat"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        events = []
        user_message = tracker.latest_message.get('text', '').lower()
        logger.info(f"🔍 verification_contrat - message: '{user_message}'")
        
        # ========== RÉCUPÉRATION DES ENTITÉS NON MAPPÉES ==========
        entities = tracker.latest_message.get('entities', [])
        logger.info(f"📋 Entités extraites par le NLU: {len(entities)}")
        
        # Afficher toutes les entités pour debug
        for entity in entities:
            logger.info(f"  • {entity.get('entity')} = '{entity.get('value')}'")
        
        # ========== VÉRIFIER L'EFFECTIF ==========
        effectif = tracker.get_slot("effectif")
        logger.info(f"📊 Slot effectif initial: '{effectif}'")
        
        # Si le slot est vide, chercher dans les entités
        if not effectif:
            for entity in entities:
                if entity.get('entity') == 'effectif':
                    effectif = entity.get('value')
                    logger.info(f"✅ Effectif récupéré depuis l'entité: '{effectif}'")
                    break
        
        effectif_result = self.validate_effectif(effectif, user_message, tracker, dispatcher)
        events.extend([SlotSet(k, v) for k, v in effectif_result.items()])
        
        # ========== VÉRIFIER LA DURÉE ==========
        duree = tracker.get_slot("duree_contrat")
        logger.info(f"📊 Slot duree_contrat initial: '{duree}'")
        
        # Si le slot est vide, chercher dans les entités
        if not duree:
            for entity in entities:
                if entity.get('entity') == 'duree_contrat':
                    duree = entity.get('value')
                    logger.info(f"✅ Durée récupérée depuis l'entité: '{duree}'")
                    break
        
        logger.info(f"📊 Valeur finale AVANT validation: '{duree}'")
        duree_result = self.validate_duree_contrat(duree, user_message, tracker, dispatcher)
        logger.info(f"📊 Résultat validation durée: {duree_result}")
        events.extend([SlotSet(k, v) for k, v in duree_result.items()])
        
        # ========== VÉRIFIER LA NATURE DU CONTRAT ==========
        nature_contrat = tracker.get_slot("nature_contrat")
        nature_result = self.validate_nature_contrat(nature_contrat, dispatcher)
        events.extend([SlotSet(k, v) for k, v in nature_result.items()])
        
        # ========== VÉRIFIER LA DATE DE MISE EN SERVICE ==========
        date_service = tracker.get_slot("date_mise_en_service")
        date_service_result = self.validate_date_mise_en_service(date_service, dispatcher)
        events.extend([SlotSet(k, v) for k, v in date_service_result.items()])
        
        # ========== VÉRIFIER DATE DÉBUT (éviter duplication de message) ==========
        date_debut = tracker.get_slot("date_debut")
        if date_debut:
            # Si date_debut est identique à date_service, copier le résultat validé
            if date_debut == date_service:
                logger.info("📊 date_debut == date_mise_en_service, copie du résultat validé")
                validated_date = date_service_result.get("date_mise_en_service")
                events.append(SlotSet("date_debut", validated_date))
            else:
                # Sinon valider séparément
                logger.info("📊 date_debut différente de date_mise_en_service, validation séparée")
                date_debut_result = self.validate_date_mise_en_service(date_debut, dispatcher)
                events.append(SlotSet("date_debut", date_debut_result.get("date_mise_en_service")))
        
        # ========== VÉRIFIER DATE FIN (éviter duplication de message) ==========
        date_fin = tracker.get_slot("date_fin")
        if date_fin:
            # Si date_fin est identique à date_service ou date_debut, copier le résultat
            if date_fin == date_service or date_fin == date_debut:
                logger.info("📊 date_fin == autre date déjà validée, copie du résultat")
                validated_date = date_service_result.get("date_mise_en_service")
                events.append(SlotSet("date_fin", validated_date))
            else:
                # Sinon valider séparément
                logger.info("📊 date_fin différente des autres dates, validation séparée")
                date_fin_result = self.validate_date_mise_en_service(date_fin, dispatcher)
                events.append(SlotSet("date_fin", date_fin_result.get("date_mise_en_service")))
        
        # ========== VALIDATION GLOBALE ==========
        all_valid = all([
            effectif_result.get("effectif"),
            duree_result.get("duree_contrat") or nature_contrat != "CDD",
            nature_result.get("nature_contrat"),
            date_service_result.get("date_mise_en_service")
        ])
        
        logger.info(f"✅ Validation contrat terminée. Events retournés: {len(events)}")
        return events
    
    def validate_effectif(self, slot_value: Any, user_message: str, tracker: Tracker, dispatcher) -> Dict[Text, Any]:
        """
        Valide l'effectif avec extraction robuste.
        
        ✅ Accepte: "2", "2 personnes", "deux", "deux personnes"
        ❌ Rejette: "AG01", "00", "US02" (codes d'exploitation)
        """
        logger.info(f"🔍 validate_effectif - slot_value: '{slot_value}'")
        
        if not slot_value:
            logger.info("⚠️ Pas de valeur d'effectif fournie")
            return {"effectif": None}
        
        # Vérifier le contexte (optionnel mais recommandé)
        requested_slot = tracker.get_slot("requested_slot")
        if requested_slot and requested_slot not in ["effectif", None]:
            logger.info(f"⚠️ Slot effectif capturé hors contexte (requested_slot={requested_slot})")
        
        # Extraire le nombre avec la fonction robuste
        effectif_int = extract_effectif_number(slot_value)
        
        if effectif_int is None:
            dispatcher.utter_message(
                text="❌ Je n'ai pas compris l'effectif. Merci d'indiquer un nombre (ex: 5, cinq, 2 personnes)."
            )
            return {"effectif": None}
        
        # Validation de la plage
        if 1 <= effectif_int <= 10000:
            logger.info(f"✅ Effectif validé: {effectif_int} (valeur originale: '{slot_value}')")
            return {"effectif": str(effectif_int)}
        else:
            dispatcher.utter_message(
                text=f"❌ L'effectif doit être entre 1 et 10000. Vous avez indiqué {effectif_int}."
            )
            return {"effectif": None}

    def validate_duree_contrat(self, slot_value: Any, user_message: str, tracker: Tracker, dispatcher) -> Dict[Text, Any]:
        """Valide la durée avec extraction contextuelle améliorée"""
        
        logger.info(f"🔍 validate_duree_contrat - slot_value reçu: '{slot_value}'")
        
        # ÉTAPE 1 : Si pas de valeur, tenter extraction contextuelle
        if not slot_value:
            duree_extracted = extract_number_from_context(
                user_message, 
                ['durée', 'duree', 'durree', 'contrat', 'période', 'periode', 'mois']
            )
            if duree_extracted:
                slot_value = str(duree_extracted)
            else:
                logger.info("⚠️ Aucune durée extraite du contexte")
                return {"duree_contrat": None}
        
        slot_str = str(slot_value).strip()
        logger.info(f"🔍 Traitement de: '{slot_str}'")
        
        # ÉTAPE 2 : Rejeter les codes d'exploitation
        if re.match(r'^(00|AG\d{2}|US\d{2})', slot_str):
            logger.info(f"⚠️ Rejeté: '{slot_str}' ressemble à un code d'exploitation")
            return {"duree_contrat": None}
        
        # ÉTAPE 3 : Extraction intelligente
        duree_int = None
        
        # Pattern 1: "six mois", "12 mois", "trois ans", etc.
        match = re.search(r'([\w\d]+)\s*(mois|ans?|année?s?)', slot_str, re.IGNORECASE)
        if match:
            duree_word = match.group(1).strip()
            unite = match.group(2).lower()
            logger.info(f"✓ Extrait: '{duree_word}' {unite}")
            
            try:
                duree_int = text_to_number_fr(duree_word)
                
                # Si c'est en années, convertir en mois
                if 'an' in unite or 'année' in unite:
                    duree_int = duree_int * 12
                    logger.info(f"✓ Converti {duree_word} an(s) → {duree_int} mois")
            
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Erreur conversion: {e}")
                dispatcher.utter_message(
                    text="❌ Durée invalide. Indiquez un nombre de mois (ex: 6 mois, douze mois, 1 an)."
                )
                return {"duree_contrat": None}
        
        # Pattern 2: Juste un nombre ("6", "douze", "12")
        else:
            try:
                duree_int = text_to_number_fr(slot_str)
                logger.info(f"✓ Conversion directe: {slot_str} → {duree_int}")
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Erreur conversion: {e}")
                dispatcher.utter_message(
                    text="❌ Durée invalide. Indiquez un nombre de mois (ex: 6, douze)."
                )
                return {"duree_contrat": None}
        
        # ÉTAPE 4 : Validation de la plage
        if duree_int and 1 <= duree_int <= 120:
            logger.info(f"✅ Durée validée: {duree_int} mois (valeur originale: '{slot_str}')")
            return {"duree_contrat": str(duree_int)}
        
        logger.warning(f"⚠️ Durée hors limites: {duree_int}")
        dispatcher.utter_message(
            text=f"❌ La durée doit être comprise entre 1 et 120 mois. Vous avez indiqué {duree_int} mois."
        )
        return {"duree_contrat": None}
    
    def validate_nature_contrat(self, slot_value: Any, dispatcher) -> Dict[Text, Any]:
        """Valide la nature du contrat"""
        
        if not slot_value:
            return {"nature_contrat": None}
        
        valid_contrats = {"CDI", "CDD", "STAGE", "EXTERNALISÉ", "EXTERNALISE"}
        
        if str(slot_value).upper() in valid_contrats:
            return {"nature_contrat": slot_value}
        
        dispatcher.utter_message(
            text="❌ Nature de contrat invalide. Veuillez choisir parmi: CDI, CDD, Stage, Externalisé"
        )
        return {"nature_contrat": None}
    
    def validate_date_mise_en_service(self, slot_value: Any, dispatcher) -> Dict[Text, Any]:
        """
        Valide la date de mise en service avec support des formats français
        ET vérification que la date est dans le futur
        
        Formats acceptés:
        - 15/01/2025, 15-01-2025
        - 15 janvier 2025, 15 janvier
        - premier janvier 2026, premier janvier
        - 12 décembre 2026
        
        Règles de validation:
        - L'année courante est ajoutée si non mentionnée
        - La date doit être dans le FUTUR (pas aujourd'hui, pas le passé)
        """
        if not slot_value:
            return {"date_mise_en_service": None}
        
        slot_str = str(slot_value).strip()
        logger.info(f"🔍 Validation date_mise_en_service: '{slot_str}'")
        
        # Étape 1: Extraire et convertir la date
        date_parsed = extract_date_from_text(slot_str)
        
        if not date_parsed:
            # Essayer l'ancien format en fallback
            pattern = r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}"
            if re.match(pattern, slot_str):
                try:
                    if '/' in slot_str:
                        datetime.strptime(slot_str, '%d/%m/%Y')
                        date_parsed = slot_str
                    else:
                        date_obj = datetime.strptime(slot_str, '%Y-%m-%d')
                        date_parsed = date_obj.strftime('%d/%m/%Y')
                except ValueError:
                    pass
        
        if not date_parsed:
            dispatcher.utter_message(
                text="❌ Date invalide. Formats acceptés :\n"
                     "  • 15/01/2025\n"
                     "  • 15 janvier 2025\n"
                     "  • 15 janvier (année courante)\n"
                     "  • premier janvier 2026"
            )
            return {"date_mise_en_service": None}
        
        # Étape 2: Vérifier que la date est dans le futur
        if not is_date_future(date_parsed, include_today=False):
            diff_message = get_date_difference_message(date_parsed)
            
            logger.warning(f"⚠️ Date rejetée (passée): {date_parsed} ({diff_message})")
            
            dispatcher.utter_message(
                text=f"❌ La date de mise en service doit être dans le futur.\n"
                     f"📅 Date indiquée : {date_parsed} ({diff_message})\n"
                     f"📅 Date minimale : {get_tomorrow_date()}\n\n"
                     f"Veuillez indiquer une date future."
            )
            return {"date_mise_en_service": None}
        
        # Date valide et future
        logger.info(f"✅ Date validée: {date_parsed} ({get_date_difference_message(date_parsed)})")
        return {"date_mise_en_service": date_parsed}