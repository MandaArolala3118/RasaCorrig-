import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, SessionStarted, ActionExecuted
from difflib import SequenceMatcher
import re
from datetime import datetime
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Import the backend service
from actions.services.ddr_service import get_backend_service


logger = logging.getLogger(__name__)


class ActionVerifierPermission(Action):
    """Donne la permission de continuer"""
    
    def name(self) -> Text:
        return "action_verifier_permission"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        metadata = tracker.latest_message.get('metadata', {})
        type_demande = tracker.get_slot("type_demande")
        intention_demande = tracker.get_slot("intention_demande")
        role = metadata.get('role', 'Unknown')
        print("-------------------------------------------------------Role dans action_verifier_permission : ", role)
        print("-------------------------------------------------------meta data : ", metadata)
        
        # ========== GESTION DES PERMISSIONS - STRICTEMENT ==========
        
        # ✅ Seul ERM peut lancer un flux de recrutement
        if intention_demande == "flux":
            if role == "ERM":
                return [
                    SlotSet("role", role),
                    SlotSet("permission", True),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", None),
                    SlotSet("rejection_intent", None),
                    SlotSet("lancement_flux_intent", True),
                    SlotSet("ajout_ddr_intent", None)
                ]
            else:
                # EV et autres rôles ne peuvent pas lancer un flux
                return [
                    SlotSet("role", role),
                    SlotSet("permission", False),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", None),
                    SlotSet("rejection_intent", None),
                    SlotSet("lancement_flux_intent", False),
                    SlotSet("ajout_ddr_intent", None)
                ]
        
        # ✅ Seul EV peut valider une demande
        if intention_demande == "validation":
            if role == "EV":
                return [
                    SlotSet("role", role),
                    SlotSet("permission", True),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", True),
                    SlotSet("rejection_intent", None),
                    SlotSet("lancement_flux_intent", None),
                    SlotSet("ajout_ddr_intent", None)
                ]
            else:
                # ERM et autres rôles ne peuvent pas valider
                return [
                    SlotSet("role", role),
                    SlotSet("permission", False),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", False),
                    SlotSet("rejection_intent", None),
                    SlotSet("lancement_flux_intent", None),
                    SlotSet("ajout_ddr_intent", None)
                ]
        
        # ✅ Seul EV peut rejeter une demande
        if intention_demande == "rejet":
            if role == "EV":
                return [
                    SlotSet("role", role),
                    SlotSet("permission", True),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", None),
                    SlotSet("rejection_intent", True),
                    SlotSet("lancement_flux_intent", None),
                    SlotSet("ajout_ddr_intent", None)
                ]
            else:
                # ERM et autres rôles ne peuvent pas rejeter
                return [
                    SlotSet("role", role),
                    SlotSet("permission", False),
                    SlotSet("type_demande", type_demande),
                    SlotSet("intention_demande", intention_demande),
                    SlotSet("validation_intent", None),
                    SlotSet("rejection_intent", False),
                    SlotSet("lancement_flux_intent", None),
                    SlotSet("ajout_ddr_intent", None)
                ]
        
        # DDR - Ajout de demande de recrutement (tous les rôles qui le demandent)
        if type_demande == "DDR" and intention_demande == "ajouter":
            return [
                SlotSet("role", role),
                SlotSet("permission", True),
                SlotSet("type_demande", type_demande),
                SlotSet("intention_demande", intention_demande),
                SlotSet("validation_intent", None),
                SlotSet("rejection_intent", None),
                SlotSet("lancement_flux_intent", None),
                SlotSet("ajout_ddr_intent", True)
            ]
        
        # ❌ Aucune permission par défaut
        return [
            SlotSet("role", role),
            SlotSet("permission", False),
            SlotSet("type_demande", type_demande),
            SlotSet("intention_demande", intention_demande),
            SlotSet("validation_intent", False),
            SlotSet("rejection_intent", False),
            SlotSet("lancement_flux_intent", False),
            SlotSet("ajout_ddr_intent", None)
        ]
class ActionAfficherInformations(Action):
    """
    Action pour afficher des informations spécifiques de la DDR
    Supporte l'affichage d'une ou plusieurs sections
    """
    
    def name(self) -> Text:
        return "action_afficher_informations"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ============================================
        # 1. EXTRACTION DES TYPES D'INFORMATIONS DEMANDÉS
        # ============================================
        
        entities = tracker.latest_message.get("entities", [])
        info_types_demandes = []
        
        # Extraire toutes les entités info_type
        for entity in entities:
            if entity.get("entity") == "info_type":
                value = entity.get("value", "").lower()
                info_types_demandes.append(value)
        
        logger.info(f"📋 Types d'infos demandés: {info_types_demandes}")
        
        # Si aucune info spécifique demandée, afficher tout
        if not info_types_demandes:
            logger.info("ℹ️ Aucune info spécifique → affichage complet")
            info_types_demandes = ["tout"]
        
        # ============================================
        # 2. NORMALISATION DES TYPES D'INFORMATIONS
        # ============================================
        
        # Mapper les variations vers des catégories standards
        categories_mapping = {
            "objectifs": ["objectifs", "objectif"],
            "dotations": ["dotations", "dotation"],
            "pieces_jointes": ["pièces jointes", "pièce jointe", "fichiers", "fichier", "documents", "document"],
            "poste": ["poste"],
            "encadreur": ["encadreur"],
            "direction": ["direction"],
            "exploitation": ["exploitation"],
            "contrat": ["contrat", "nature contrat", "durée", "effectif", "date", "date de service"],
            "motif": ["motif"],
            "justification": ["justification"],
            "budget": ["budget", "situation budget"],
            "organisation": ["organisation"],
            "infos_generales": ["infos générales", "informations générales"],
            "tout": ["tout", "tous", "toutes", "complet", "récapitulatif", "résumé"],
        }
        
        # Déterminer les catégories demandées
        categories_a_afficher = set()
        
        for info_demandee in info_types_demandes:
            for categorie, variations in categories_mapping.items():
                if any(variation in info_demandee for variation in variations):
                    categories_a_afficher.add(categorie)
        
        # Si "tout" est demandé, afficher toutes les sections
        if "tout" in categories_a_afficher:
            categories_a_afficher = {
                "poste", "encadreur", "direction", "exploitation",
                "contrat", "motif", "justification", "budget",
                "objectifs", "dotations", "pieces_jointes"
            }
        
        logger.info(f"📊 Catégories à afficher: {categories_a_afficher}")
        
        if not categories_a_afficher:
            dispatcher.utter_message(response="utter_ask_quelle_information")
            return []
        
        # ============================================
        # 3. RÉCUPÉRATION DES SLOTS
        # ============================================
        
        slots_data = {
            "nom_poste": tracker.get_slot("nom_poste"),
            "effectif": tracker.get_slot("effectif"),
            "nature_contrat": tracker.get_slot("nature_contrat"),
            "duree_contrat": tracker.get_slot("duree_contrat"),
            "date_mise_en_service": tracker.get_slot("date_mise_en_service"),
            "nom_encadreur": tracker.get_slot("nom_encadreur"),
            "poste_encadreur": tracker.get_slot("poste_encadreur"),
            "direction": tracker.get_slot("direction"),
            "exploitation": tracker.get_slot("exploitation"),
            "motif": tracker.get_slot("motif"),
            "justification": tracker.get_slot("justification"),
            "situation_budget": tracker.get_slot("situation_budget"),
            "objectifs_list": tracker.get_slot("objectifs_list") or [],
            "dotations_list": tracker.get_slot("dotations_list") or [],
            "piece_jointe": tracker.get_slot("piece_jointe") or "",
        }
        
        # ============================================
        # 4. CONSTRUCTION DU MESSAGE
        # ============================================
        
        message = "📋 **Informations de votre demande DDR**\n\n"
        sections_affichees = []
        
        # ========== SECTION POSTE ==========
        if "poste" in categories_a_afficher or "infos_generales" in categories_a_afficher:
            if slots_data["nom_poste"]:
                message += "**📌 Poste**\n"
                message += f"• Nom du poste : {slots_data['nom_poste']}\n"
                message += f"• Effectif : {slots_data['effectif'] or 'Non défini'}\n\n"
                sections_affichees.append("poste")
        
        # ========== SECTION ENCADREUR ==========
        if "encadreur" in categories_a_afficher:
            if slots_data["nom_encadreur"]:
                message += "**👤 Encadreur**\n"
                message += f"• Nom : {slots_data['nom_encadreur']}\n"
                if slots_data["poste_encadreur"]:
                    message += f"• Poste : {slots_data['poste_encadreur']}\n"
                message += "\n"
                sections_affichees.append("encadreur")
        
        # ========== SECTION ORGANISATION ==========
        if any(cat in categories_a_afficher for cat in ["direction", "exploitation", "organisation"]):
            if slots_data["direction"] or slots_data["exploitation"]:
                message += "**🏢 Organisation**\n"
                if slots_data["direction"]:
                    message += f"• Direction : {slots_data['direction']}\n"
                if slots_data["exploitation"]:
                    message += f"• Exploitation : {slots_data['exploitation']}\n"
                message += "\n"
                sections_affichees.append("organisation")
        
        # ========== SECTION CONTRAT ==========
        if "contrat" in categories_a_afficher or "infos_generales" in categories_a_afficher:
            if slots_data["nature_contrat"]:
                message += "**📄 Contrat**\n"
                message += f"• Nature : {slots_data['nature_contrat']}\n"
                if slots_data["duree_contrat"]:
                    message += f"• Durée : {slots_data['duree_contrat']}\n"
                if slots_data["date_mise_en_service"]:
                    message += f"• Date de mise en service : {slots_data['date_mise_en_service']}\n"
                message += "\n"
                sections_affichees.append("contrat")
        
        # ========== SECTION MOTIF & JUSTIFICATION ==========
        if any(cat in categories_a_afficher for cat in ["motif", "justification", "budget"]):
            if slots_data["motif"] or slots_data["justification"] or slots_data["situation_budget"]:
                message += "**💼 Justification**\n"
                if slots_data["motif"]:
                    message += f"• Motif : {slots_data['motif']}\n"
                if slots_data["situation_budget"]:
                    message += f"• Situation budgétaire : {slots_data['situation_budget']}\n"
                if slots_data["justification"]:
                    justif_preview = slots_data['justification'][:200]
                    if len(slots_data['justification']) > 200:
                        justif_preview += "..."
                    message += f"• Justification : {justif_preview}\n"
                message += "\n"
                sections_affichees.append("justification")
        
        # ========== SECTION OBJECTIFS ==========
        if "objectifs" in categories_a_afficher:
            objectifs_list = slots_data["objectifs_list"]
            if objectifs_list and len(objectifs_list) > 0:
                message += f"**🎯 Objectifs ({len(objectifs_list)})**\n"
                somme_poids = sum(obj.get("poids", 0) for obj in objectifs_list)
                message += f"━━━━━━━━━━━━━━━━━━━━\n"
                message += f"Total des poids : **{somme_poids:.0f}%** / 100%\n\n"
                
                for idx, obj in enumerate(objectifs_list, 1):
                    objectif = obj.get("objectif", "Non défini")
                    poids = obj.get("poids", 0)
                    resultat = obj.get("resultat", "Non défini")
                    
                    message += f"{idx}. **{objectif}** ({poids}%)\n"
                    message += f"   ➜ Résultat attendu : {resultat}\n\n"
                
                message += "━━━━━━━━━━━━━━━━━━━━\n\n"
                sections_affichees.append("objectifs")
            else:
                message += "**🎯 Objectifs**\n"
                message += "⚠️ Aucun objectif défini\n\n"
        
        # ========== SECTION DOTATIONS ==========
        if "dotations" in categories_a_afficher:
            dotations_list = slots_data["dotations_list"]
            if dotations_list and len(dotations_list) > 0:
                message += f"**💰 Dotations ({len(dotations_list)})**\n"
                for idx, dotation in enumerate(dotations_list, 1):
                    if isinstance(dotation, dict):
                        nom = dotation.get("nom") or dotation.get("dotation")
                        message += f"{idx}. {nom}\n"
                    else:
                        message += f"{idx}. Dotation ID: {dotation}\n"
                message += "\n"
                sections_affichees.append("dotations")
            else:
                message += "**💰 Dotations**\n"
                message += "⚠️ Aucune dotation définie\n\n"
        
        # ========== SECTION PIÈCES JOINTES ==========
        if "pieces_jointes" in categories_a_afficher:
            piece_jointes = slots_data["piece_jointe"]
            if piece_jointes and piece_jointes.strip():
                pieces_list = [p.strip() for p in piece_jointes.split(",") if p.strip()]
                message += f"**📎 Pièces jointes ({len(pieces_list)})**\n"
                for idx, piece in enumerate(pieces_list, 1):
                    message += f"{idx}. {piece}\n"
                message += "\n"
                sections_affichees.append("pieces_jointes")
            else:
                message += "**📎 Pièces jointes**\n"
                message += "⚠️ Aucune pièce jointe\n\n"
        
        # ============================================
        # 5. VÉRIFICATION SI AUCUNE DONNÉE DISPONIBLE
        # ============================================
        
        if not sections_affichees:
            message = (
                "⚠️ **Aucune information disponible pour les catégories demandées**\n\n"
                "Les informations suivantes n'ont pas encore été renseignées :\n"
                f"• {', '.join(categories_a_afficher)}\n\n"
                "💡 Commencez par remplir votre demande DDR ou demandez à afficher d'autres informations."
            )
        else:
            message += f"✅ **{len(sections_affichees)} section(s) affichée(s)**"
        
        # ============================================
        # 6. ENVOI DU MESSAGE
        # ============================================
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"✅ Affichage terminé - {len(sections_affichees)} section(s) affichée(s)")
        
        return [
            SlotSet("info_types_a_afficher", list(categories_a_afficher)),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]