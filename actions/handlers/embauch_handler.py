"""
Custom action to clean and normalize extracted entities from the embaucher intent.
This action fixes entity values that include extra context words from regex extraction.
"""

import re
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet


class ActionCleanHireEntities(Action):
    """
    Clean and normalize entities extracted during hire intent processing.
    
    Fixes common issues:
    - Removes label words from taille/pointure (e.g., "taille 165" -> "165")
    - Removes action verbs from nom_et_prenoms (e.g., "embaucher Manda..." -> "Manda...")
    - Removes prepositions from dates (e.g., "du 01/02/2026" -> "01/02/2026")
    - Cleans service names
    """
    
    def name(self) -> Text:
        return "action_clean_hire_entities"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        slots_to_set = []
        
        # Clean nom_et_prenoms
        nom = tracker.get_slot("nom_et_prenoms")
        if nom:
            cleaned_nom = self._clean_name(nom)
            if cleaned_nom != nom:
                slots_to_set.append(SlotSet("nom_et_prenoms", cleaned_nom))
        
        # Clean service
        service = tracker.get_slot("service")
        if service:
            cleaned_service = self._clean_service(service)
            if cleaned_service != service:
                slots_to_set.append(SlotSet("service", cleaned_service))
        
        # Clean taille
        taille = tracker.get_slot("taille")
        if taille:
            cleaned_taille = self._clean_taille(taille)
            if cleaned_taille != taille:
                slots_to_set.append(SlotSet("taille", cleaned_taille))
        
        # Clean pointure
        pointure = tracker.get_slot("pointure")
        if pointure:
            cleaned_pointure = self._clean_pointure(pointure)
            if cleaned_pointure != pointure:
                slots_to_set.append(SlotSet("pointure", cleaned_pointure))
        
        # Clean date_debut
        date_debut = tracker.get_slot("date_debut")
        if date_debut:
            cleaned_date = self._clean_date(date_debut)
            if cleaned_date != date_debut:
                slots_to_set.append(SlotSet("date_debut", cleaned_date))
        
        # Clean date_fin
        date_fin = tracker.get_slot("date_fin")
        if date_fin:
            cleaned_date = self._clean_date(date_fin)
            if cleaned_date != date_fin:
                slots_to_set.append(SlotSet("date_fin", cleaned_date))
        
        # Clean direction (remove if it's just the word "direction")
        direction = tracker.get_slot("direction")
        if direction and direction.lower() == "direction":
            slots_to_set.append(SlotSet("direction", None))
        
        return slots_to_set
    
    def _clean_name(self, name: Text) -> Text:
        """
        Remove action verbs and prepositions from person names.
        
        Examples:
            "embaucher Manda Andrianina au service" -> "Manda Andrianina"
            "recruter Jean Rakoto avec" -> "Jean Rakoto"
        """
        if not name:
            return name
        
        # Remove leading action verbs
        name = re.sub(
            r'^(?:embaucher|recruter|embauche\s+de)\s+',
            '',
            name,
            flags=re.IGNORECASE
        )
        
        # Split at common prepositions and take the first part
        name = re.split(
            r'\s+(?:au|à|avec|comme|pour|sous|,|du|de\s+la|de)',
            name,
            maxsplit=1
        )[0]
        
        return name.strip()
    
    def _clean_service(self, service: Text) -> Text:
        """
        Clean service/department names.
        
        Examples:
            "au service Informatique" -> "Informatique"
            "service DSI comme" -> "DSI"
        """
        if not service:
            return service
        
        # Remove "service" and "au service" prefixes
        service = re.sub(
            r'^(?:au\s+)?service\s+(?:de\s+|d\')?',
            '',
            service,
            flags=re.IGNORECASE
        )
        
        # Remove trailing prepositions
        service = re.split(
            r'\s+(?:comme|pour|en|à|,)',
            service,
            maxsplit=1
        )[0]
        
        # Map common service names to their codes
        service_mapping = {
            'informatique': 'DSI',
            'rh': 'DRH',
            'ressources humaines': 'DRH',
            'marketing': 'DMA',
            'finance': 'DAF',
            'commercial': 'DCM',
            'logistique': 'DGL',
            'communication': 'DCO',
        }
        
        service_lower = service.lower().strip()
        mapped_service = service_mapping.get(service_lower)
        
        return mapped_service if mapped_service else service.strip()
    
    def _clean_taille(self, taille: Text) -> Text:
        """
        Extract size value from taille field.
        
        Examples:
            "taille 165 cm" -> "165"
            "taille L" -> "L"
            "taille 1m65" -> "165"
        """
        if not taille:
            return taille
        
        # Handle metric format "1m65" -> "165"
        metric_match = re.search(r'(\d{1})\s*m\s*(\d{2})', taille)
        if metric_match:
            meters = metric_match.group(1)
            centimeters = metric_match.group(2)
            return f"{meters}{centimeters}"
        
        # Extract numeric value (e.g., "165")
        numeric_match = re.search(r'\d{2,3}', taille)
        if numeric_match:
            return numeric_match.group()
        
        # Extract size code (e.g., "L", "XL", "M")
        size_match = re.search(r'\b([XSML]{1,3})\b', taille, re.IGNORECASE)
        if size_match:
            return size_match.group(1).upper()
        
        # If nothing matches, return original
        return taille.strip()
    
    def _clean_pointure(self, pointure: Text) -> Text:
        """
        Extract shoe size from pointure field.
        
        Examples:
            "pointure 38" -> "38"
            "pointure: 42" -> "42"
        """
        if not pointure:
            return pointure
        
        # Extract numeric value
        match = re.search(r'\d{1,2}', pointure)
        if match:
            return match.group()
        
        return pointure.strip()
    
    def _clean_date(self, date: Text) -> Text:
        """
        Remove prepositions from dates.
        
        Examples:
            "du 01/02/2026" -> "01/02/2026"
            "au 01/02/2027" -> "01/02/2027"
            "à partir du 15/03/2026" -> "15/03/2026"
            "jusqu'au 20/12/2027" -> "20/12/2027"
        """
        if not date:
            return date
        
        # Remove common date prepositions
        date = re.sub(
            r'^(?:du|au|à\s+partir\s+du|jusqu\'au|le)\s+',
            '',
            date,
            flags=re.IGNORECASE
        )
        
        return date.strip()


# Alternative: More aggressive cleaning action
class ActionValidateAndCleanHireEntities(Action):
    """
    Advanced version that validates and cleans entities with logging.
    Use this if you need stricter validation and debugging.
    """
    
    def name(self) -> Text:
        return "action_validate_hire_entities"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        slots_to_set = []
        validation_errors = []
        
        # Validate and clean nom_et_prenoms
        nom = tracker.get_slot("nom_et_prenoms")
        if nom:
            cleaned = self._clean_and_validate_name(nom)
            if cleaned:
                slots_to_set.append(SlotSet("nom_et_prenoms", cleaned))
            else:
                validation_errors.append("Nom invalide détecté")
        
        # Validate dates
        date_debut = tracker.get_slot("date_debut")
        date_fin = tracker.get_slot("date_fin")
        
        if date_debut and date_fin:
            cleaned_debut = self._extract_date(date_debut)
            cleaned_fin = self._extract_date(date_fin)
            
            if cleaned_debut:
                slots_to_set.append(SlotSet("date_debut", cleaned_debut))
            if cleaned_fin:
                slots_to_set.append(SlotSet("date_fin", cleaned_fin))
            
            # Validate date logic
            if cleaned_debut and cleaned_fin:
                if not self._validate_date_range(cleaned_debut, cleaned_fin):
                    validation_errors.append(
                        "La date de début doit être antérieure à la date de fin"
                    )
        
        # If there are validation errors, notify user
        if validation_errors:
            error_msg = "⚠️ Attention: " + ", ".join(validation_errors)
            dispatcher.utter_message(text=error_msg)
        
        return slots_to_set
    
    def _clean_and_validate_name(self, name: Text) -> Text:
        """Clean name and validate it contains at least first and last name."""
        # Remove action verbs and prepositions
        cleaned = re.sub(r'^(?:embaucher|recruter|embauche\s+de)\s+', '', name, flags=re.I)
        cleaned = re.split(r'\s+(?:au|à|avec|comme|pour|sous|,)', cleaned)[0].strip()
        
        # Validate: should have at least 2 capitalized words
        words = cleaned.split()
        if len(words) < 2:
            return None
        
        # Check each word starts with capital letter
        if not all(word[0].isupper() for word in words):
            return None
        
        return cleaned
    
    def _extract_date(self, date_str: Text) -> Text:
        """Extract clean date in DD/MM/YYYY format."""
        # Remove prepositions
        cleaned = re.sub(
            r'^(?:du|au|à\s+partir\s+du|jusqu\'au|le)\s+',
            '',
            date_str,
            flags=re.I
        )
        
        # Try to extract DD/MM/YYYY or DD-MM-YYYY
        match = re.search(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', cleaned)
        if match:
            return match.group(1)
        
        return None
    
    def _validate_date_range(self, date_debut: Text, date_fin: Text) -> bool:
        """Validate that start date is before end date."""
        from datetime import datetime
        
        try:
            # Parse dates (assuming DD/MM/YYYY format)
            fmt = "%d/%m/%Y"
            
            # Handle different separators
            date_debut = date_debut.replace('-', '/')
            date_fin = date_fin.replace('-', '/')
            
            debut = datetime.strptime(date_debut, fmt)
            fin = datetime.strptime(date_fin, fmt)
            
            return debut < fin
        except ValueError:
            # If parsing fails, don't block the process
            return True