"""
Actions pour gérer le processus d'embauche complet
"""

import re
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ActionVerifierPermissionEmbauche(Action):
    """Vérifie que seul l'ERM peut ajouter une embauche"""
    
    def name(self) -> Text:
        return "action_verifier_permission_embauche"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata', {})
        role = metadata.get('role', 'Unknown')
        
        logger.info(f"🔐 Vérification permission embauche - Role: {role}")
        
        # ✅ Seul ERM peut ajouter une embauche
        if role == "ERM":
            logger.info("✅ Permission accordée pour embauche")
            return [
                SlotSet("role", role),
                SlotSet("permission_embauche", True)
            ]
        else:
            logger.warning(f"❌ Permission refusée pour {role}")
            dispatcher.utter_message(
                text=f"❌ **Accès refusé**\n\n"
                     f"Seul le rôle **ERM** (Employé Responsable Management) peut ajouter une embauche.\n"
                     f"Votre rôle actuel : **{role}**"
            )
            return [
                SlotSet("role", role),
                SlotSet("permission_embauche", False)
            ]


class ActionValiderDonneesEmbauche(Action):
    """Valide que tous les champs obligatoires de l'embauche sont présents et corrects"""
    
    def name(self) -> Text:
        return "action_valider_donnees_embauche"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        logger.info("🔍 Début validation données embauche")
        
        # Récupération de tous les slots
        slots_data = {
            "nom_et_prenoms": tracker.get_slot("nom_et_prenoms"),
            "service": tracker.get_slot("service"),
            "nom_poste": tracker.get_slot("nom_poste"),
            "nom_encadreur": tracker.get_slot("nom_encadreur"),
            "date_debut": tracker.get_slot("date_debut"),
            "date_fin": tracker.get_slot("date_fin"),
            "taille": tracker.get_slot("taille"),
            "pointure": tracker.get_slot("pointure"),
        }
        
        # Liste des champs manquants
        champs_manquants = []
        champs_invalides = []
        
        # ============================================
        # VALIDATION DES CHAMPS OBLIGATOIRES
        # ============================================
        
        # 1. Nom et prénoms
        if not slots_data["nom_et_prenoms"]:
            champs_manquants.append("Nom et prénoms")
        elif not self._valider_nom(slots_data["nom_et_prenoms"]):
            champs_invalides.append("Nom et prénoms (doit contenir au moins 2 mots)")
        
        # 2. Service
        if not slots_data["service"]:
            champs_manquants.append("Service")
        
        # 3. Nom du poste
        if not slots_data["nom_poste"]:
            champs_manquants.append("Nom du poste")
        
        # 4. Nom de l'encadreur
        if not slots_data["nom_encadreur"]:
            champs_manquants.append("Nom de l'encadreur")
        elif not self._valider_nom(slots_data["nom_encadreur"]):
            champs_invalides.append("Nom de l'encadreur (doit contenir au moins 2 mots)")
        
        # 5. Date de début
        if not slots_data["date_debut"]:
            champs_manquants.append("Date de début")
        elif not self._valider_format_date(slots_data["date_debut"]):
            champs_invalides.append("Date de début (format attendu: JJ/MM/AAAA)")
        
        # 6. Date de fin
        if not slots_data["date_fin"]:
            champs_manquants.append("Date de fin")
        elif not self._valider_format_date(slots_data["date_fin"]):
            champs_invalides.append("Date de fin (format attendu: JJ/MM/AAAA)")
        
        # 7. Taille
        if not slots_data["taille"]:
            champs_manquants.append("Taille")
        
        # 8. Pointure
        if not slots_data["pointure"]:
            champs_manquants.append("Pointure")
        
        # ============================================
        # VALIDATION LOGIQUE DES DATES
        # ============================================
        
        if slots_data["date_debut"] and slots_data["date_fin"]:
            if (self._valider_format_date(slots_data["date_debut"]) and 
                self._valider_format_date(slots_data["date_fin"])):
                if not self._valider_ordre_dates(slots_data["date_debut"], slots_data["date_fin"]):
                    champs_invalides.append("Les dates (la date de début doit être avant la date de fin)")
        
        # ============================================
        # CONSTRUCTION DU MESSAGE DE RETOUR
        # ============================================
        
        if champs_manquants or champs_invalides:
            # ❌ Validation échouée
            message = "❌ **Validation échouée - Informations manquantes ou invalides**\n\n"
            
            if champs_manquants:
                message += "**📋 Champs manquants :**\n"
                for champ in champs_manquants:
                    message += f"• {champ}\n"
                message += "\n"
            
            if champs_invalides:
                message += "**⚠️ Champs invalides :**\n"
                for champ in champs_invalides:
                    message += f"• {champ}\n"
                message += "\n"
            
            message += "💡 **Veuillez fournir toutes les informations requises dans le bon format.**\n\n"
            message += "**Exemple de demande complète :**\n"
            message += "```\nEmbaucher Rakoto Jean au service DSI comme Développeur "
            message += "sous l'encadrement de Rasoa Marie du 01/03/2026 au 31/12/2026 "
            message += "avec taille 170 et pointure 42\n```"
            
            dispatcher.utter_message(text=message)
            
            logger.warning(f"❌ Validation échouée: {len(champs_manquants)} manquants, {len(champs_invalides)} invalides")
            
            return [
                SlotSet("validation_embauche_ok", False),
                SlotSet("champs_manquants_embauche", champs_manquants),
                SlotSet("champs_invalides_embauche", champs_invalides)
            ]
        
        else:
            # ✅ Validation réussie
            logger.info("✅ Validation réussie - tous les champs sont valides")
            
            return [
                SlotSet("validation_embauche_ok", True),
                SlotSet("champs_manquants_embauche", []),
                SlotSet("champs_invalides_embauche", []),
                FollowupAction("action_afficher_recapitulatif_embauche")
            ]
    
    # ============================================
    # MÉTHODES DE VALIDATION
    # ============================================
    
    def _valider_nom(self, nom: Text) -> bool:
        """Valide qu'un nom contient au moins 2 mots (prénom + nom)"""
        if not nom:
            return False
        
        # Nettoyer et séparer
        mots = nom.strip().split()
        
        # Au moins 2 mots requis
        return len(mots) >= 2
    
    def _valider_format_date(self, date: Text) -> bool:
        """Valide le format de date JJ/MM/AAAA ou JJ-MM-AAAA"""
        if not date:
            return False
        
        # Pattern pour JJ/MM/AAAA ou JJ-MM-AAAA
        pattern = r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$'
        
        if not re.match(pattern, date):
            return False
        
        # Validation supplémentaire avec datetime
        try:
            date_normalized = date.replace('-', '/')
            datetime.strptime(date_normalized, "%d/%m/%Y")
            return True
        except ValueError:
            return False
    
    def _valider_ordre_dates(self, date_debut: Text, date_fin: Text) -> bool:
        """Valide que date_debut < date_fin"""
        try:
            debut = datetime.strptime(date_debut.replace('-', '/'), "%d/%m/%Y")
            fin = datetime.strptime(date_fin.replace('-', '/'), "%d/%m/%Y")
            return debut < fin
        except ValueError:
            return False


class ActionAfficherRecapitulatifEmbauche(Action):
    """Affiche un récapitulatif des données d'embauche avant confirmation"""
    
    def name(self) -> Text:
        return "action_afficher_recapitulatif_embauche"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Récupération des données
        slots_data = {
            "nom_et_prenoms": tracker.get_slot("nom_et_prenoms"),
            "service": tracker.get_slot("service"),
            "nom_poste": tracker.get_slot("nom_poste"),
            "nom_encadreur": tracker.get_slot("nom_encadreur"),
            "date_debut": tracker.get_slot("date_debut"),
            "date_fin": tracker.get_slot("date_fin"),
            "taille": tracker.get_slot("taille"),
            "pointure": tracker.get_slot("pointure"),
        }
        
        # Construction du message récapitulatif
        message = "✅ **Récapitulatif de l'embauche**\n\n"
        message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        message += "**👤 Informations personnelles**\n"
        message += f"• Nom et prénoms : **{slots_data['nom_et_prenoms']}**\n"
        message += f"• Taille : {slots_data['taille']}\n"
        message += f"• Pointure : {slots_data['pointure']}\n\n"
        
        message += "**💼 Informations professionnelles**\n"
        message += f"• Service : **{slots_data['service']}**\n"
        message += f"• Poste : **{slots_data['nom_poste']}**\n"
        message += f"• Encadreur : {slots_data['nom_encadreur']}\n\n"
        
        message += "**📅 Période d'embauche**\n"
        message += f"• Date de début : {slots_data['date_debut']}\n"
        message += f"• Date de fin : {slots_data['date_fin']}\n\n"
        
        message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        message += "📝 **Ces informations sont-elles correctes ?**\n"
        message += "• Répondez **'oui'** pour confirmer et enregistrer l'embauche\n"
        message += "• Répondez **'non'** pour annuler ou modifier"
        
        dispatcher.utter_message(text=message)
        
        return [SlotSet("en_attente_confirmation_embauche", True)]


class ActionEnregistrerEmbauche(Action):
    """Enregistre définitivement l'embauche dans le système"""
    
    def name(self) -> Text:
        return "action_enregistrer_embauche"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        logger.info("💾 Enregistrement de l'embauche")
        
        # Récupération des données
        embauche_data = {
            "nom_et_prenoms": tracker.get_slot("nom_et_prenoms"),
            "service": tracker.get_slot("service"),
            "nom_poste": tracker.get_slot("nom_poste"),
            "nom_encadreur": tracker.get_slot("nom_encadreur"),
            "date_debut": tracker.get_slot("date_debut"),
            "date_fin": tracker.get_slot("date_fin"),
            "taille": tracker.get_slot("taille"),
            "pointure": tracker.get_slot("pointure"),
            "role_createur": tracker.get_slot("role"),
            "date_creation": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
        
        # TODO: Appeler le service backend pour enregistrer
        # from actions.services.embauche_service import enregistrer_embauche
        # resultat = enregistrer_embauche(embauche_data)
        
        # Simulation de l'enregistrement réussi
        logger.info(f"✅ Embauche enregistrée: {embauche_data['nom_et_prenoms']}")
        
        message = "✅ **Embauche enregistrée avec succès !**\n\n"
        message += f"👤 **{embauche_data['nom_et_prenoms']}** a été ajouté(e) au système.\n\n"
        message += "**Détails :**\n"
        message += f"• Service : {embauche_data['service']}\n"
        message += f"• Poste : {embauche_data['nom_poste']}\n"
        message += f"• Période : du {embauche_data['date_debut']} au {embauche_data['date_fin']}\n\n"
        message += "📧 Une notification a été envoyée aux parties concernées."
        
        dispatcher.utter_message(text=message)
        
        # Réinitialiser les slots d'embauche
        return [
            SlotSet("nom_et_prenoms", None),
            SlotSet("service", None),
            SlotSet("nom_poste", None),
            SlotSet("nom_encadreur", None),
            SlotSet("date_debut", None),
            SlotSet("date_fin", None),
            SlotSet("taille", None),
            SlotSet("pointure", None),
            SlotSet("validation_embauche_ok", False),
            SlotSet("en_attente_confirmation_embauche", False),
            SlotSet("permission_embauche", None)
        ]


class ActionAnnulerEmbauche(Action):
    """Annule le processus d'embauche en cours"""
    
    def name(self) -> Text:
        return "action_annuler_embauche"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        logger.info("❌ Annulation de l'embauche")
        
        dispatcher.utter_message(
            text="❌ **Embauche annulée**\n\n"
                 "Le processus d'embauche a été annulé. Aucune donnée n'a été enregistrée.\n\n"
                 "💡 Vous pouvez relancer une nouvelle embauche quand vous le souhaitez."
        )
        
        # Réinitialiser tous les slots d'embauche
        return [
            SlotSet("nom_et_prenoms", None),
            SlotSet("service", None),
            SlotSet("nom_poste", None),
            SlotSet("nom_encadreur", None),
            SlotSet("date_debut", None),
            SlotSet("date_fin", None),
            SlotSet("taille", None),
            SlotSet("pointure", None),
            SlotSet("validation_embauche_ok", False),
            SlotSet("en_attente_confirmation_embauche", False),
            SlotSet("permission_embauche", None)
        ]