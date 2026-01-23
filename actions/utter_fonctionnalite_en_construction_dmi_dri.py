from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict

class ActionUtterFonctionnaliteEnConstructionDmiDri(Action):
    """Action pour informer que les fonctionnalités DMI/DRI sont en construction"""
    
    def name(self) -> Text:
        return "utter_fonctionnalite_en_construction_dmi_dri"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Affiche un message indiquant que les fonctionnalités DMI/DRI sont en construction"""
        
        type_demande = tracker.get_slot("type_demande")
        
        if type_demande == "DMI":
            message = """🚧 **Fonctionnalité DMI en construction**

Nous sommes désolés, mais la gestion des **Demandes de Mobilité Interne (DMI)** est actuellement en cours de développement.

**Fonctionnalités bientôt disponibles :**
- Création de demandes de mutation interne
- Suivi des processus de mobilité
- Validation par les managers et RH
- Historique des mobilités

**En attendant :**
Vous pouvez continuer à utiliser les **Demandes DDR** pour les recrutements externes.

Merci de votre patience ! 🙏

Souhaitez-vous créer une demande DDR à la place ?"""
        
        elif type_demande == "DRI":
            message = """🚧 **Fonctionnalité DRI en construction**

Nous sommes désolés, mais la gestion des **Demandes de Recrutement Interne (DRI)** est actuellement en cours de développement.

**Fonctionnalités bientôt disponibles :**
- Publication d'offres internes
- Candidature des employés
- Gestion des entretiens internes
- Suivi des processus de recrutement interne

**En attendant :**
Vous pouvez continuer à utiliser les **Demandes DDR** pour les recrutements externes.

Merci de votre compréhension ! 🙏

Souhaitez-vous créer une demande DDR à la place ?"""
        
        else:
            message = """🚧 **Fonctionnalité en construction**

Cette fonctionnalité est actuellement en cours de développement.

Merci de votre patience ! 🙏

Souhaitez-vous créer une demande DDR à la place ?"""
        
        dispatcher.utter_message(text=message)
        
        return []
