from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction
import logging
from actions.services.Calculate.DDR_calcul import DemandeSearchService
from actions.services.Calculate.Flux_calcul import FluxSearchService
from actions.services.Calculate.RechercheNom import UserSearchService
from actions.services.ddr_service import BackendService

from actions.Middleware.message_deduplicator import deduplicate_messages

from datetime import datetime
logger = logging.getLogger(__name__)
class ActionVerifyIfAllInformationValidationIsComplet(Action):
    """
    Action pour vérifier si tous les slots requis sont complétés.
    Slots requis: type_demande (DDR, DRI, DMI, DMOE), id_demande
    Slot optionnel: commentaire
    Vérifie également que l'utilisateur est le validateur actuel de la demande.
    """

    def name(self) -> Text:
        return "action_verify_if_all_information_validation_is_complet"
        
    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ========== Extraire les entités du dernier message ==========
        user_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        logger.info(f"Message utilisateur: '{user_message}'")
        logger.info(f"Entités détectées: {entities}")
        
        # Mapper les entités vers des variables
        extracted_data = {}
        for entity in entities:
            entity_name = entity.get('entity')
            entity_value = entity.get('value')
            
            if entity_name in ['id_demande', 'type_demande', 'commentaire']:
                extracted_data[entity_name] = entity_value
        
        # Récupérer les slots actuels
        id_demande = extracted_data.get('id_demande') or tracker.get_slot("id_demande")
        type_demande = extracted_data.get('type_demande') or tracker.get_slot("type_demande")
        commentaire = extracted_data.get('commentaire') or tracker.get_slot("commentaire")
        
        # Récupérer l'identifiant de l'utilisateur actuel (à adapter selon votre système)
        current_user = tracker.get_slot("user_id") or tracker.sender_id
        
        logger.info(f"Valeurs finales - ID: {id_demande}, Type: {type_demande}, Commentaire: {commentaire}")
        logger.info(f"Utilisateur actuel: {current_user}")
        
        # ========== VALIDATION TYPE DEMANDE ==========
        type_demande_valide = False
        types_valides = ["DDR", "DRI", "DMI", "DMOE"]
        
        if type_demande is not None and type_demande != "":
            type_demande_upper = type_demande.upper()
            
            if type_demande_upper in types_valides:
                type_demande = type_demande_upper
                type_demande_valide = True
                logger.info(f"Type de demande valide: {type_demande}")
            else:
                dispatcher.utter_message(
                    text=f"⚠️ Le type de demande '{type_demande}' n'est pas valide. "
                         f"Les types acceptés sont : **DDR**, **DRI**, **DMI**, **DMOE**.\n\n"
                         f"📋 Veuillez sélectionner l'un de ces types."
                )
                type_demande = None
        
        # ========== VALIDATION ID DEMANDE ET VALIDATEUR ==========
        id_demande_valide = False
        
        if id_demande is not None and id_demande != "":
            try:
                demande_id_int = int(id_demande)
                
                # Importer le service de recherche
                searcher = DemandeSearchService()
                demande_result = searcher.search_with_details(demande_id_int)
                logger.info(f"Résultat recherche demande {demande_id_int}: {demande_result}")
                
                if demande_result:
                    statut_id = demande_result.get('StatutId')
                    
                    if statut_id == 2:
                        # Statut 2 = demande en attente de validation
                        
                        # ========== VÉRIFICATION DU VALIDATEUR ACTUEL ==========
                        flux_taches = demande_result.get('MpFluxTaches', [])
                        
                        if not flux_taches:
                            dispatcher.utter_message(
                                text=f"⚠️ Aucun flux de validation n'est configuré pour la demande {id_demande}."
                            )
                            id_demande = None
                        else:
                            # Trouver le validateur actuel (premier avec Validation NULL)
                            validateur_actuel = None
                            validateurs_precedents = []
                            position_utilisateur = None
                            utilisateur_dans_liste = False
                            
                            for idx, tache in enumerate(flux_taches):
                                validateur = tache.get('Validateur')
                                validation = tache.get('Validation')
                                
                                # Vérifier si l'utilisateur est dans la liste des validateurs
                                if validateur and validateur.lower() == current_user.lower():
                                    utilisateur_dans_liste = True
                                    position_utilisateur = idx
                                
                                # Trouver le premier validateur avec Validation NULL
                                if validation is None and validateur_actuel is None:
                                    validateur_actuel = {
                                        'validateur': validateur,
                                        'position': idx,
                                        'nom': tache.get('NomValidateur', validateur)
                                    }
                                elif validation is None:
                                    # Ajouter aux validateurs précédents si pas encore validé et avant le validateur actuel
                                    pass
                                elif validation is not None and validateur_actuel is None:
                                    # Validateurs qui ont déjà validé avant le validateur actuel
                                    validateurs_precedents.append({
                                        'validateur': validateur,
                                        'nom': tache.get('NomValidateur', validateur)
                                    })
                            
                            logger.info(f"Validateur actuel: {validateur_actuel}")
                            logger.info(f"Utilisateur dans la liste: {utilisateur_dans_liste}")
                            logger.info(f"Position utilisateur: {position_utilisateur}")
                            
                            # CAS 1: L'utilisateur n'est pas dans la liste des validateurs
                            if not utilisateur_dans_liste:
                                dispatcher.utter_message(
                                    text=f"🚫 Vous ne faites pas partie de la liste des validateurs pour la demande **{id_demande}**.\n\n"
                                         f"Seuls les validateurs désignés peuvent traiter cette demande."
                                )
                                id_demande = None
                            
                            # CAS 2: L'utilisateur est le validateur actuel
                            elif validateur_actuel and validateur_actuel['validateur'].lower() == current_user.lower():
                                id_demande_valide = True
                                logger.info(f"✅ L'utilisateur {current_user} est le validateur actuel pour la demande {id_demande}")
                            
                            # CAS 3: L'utilisateur doit attendre son tour
                            elif position_utilisateur is not None and validateur_actuel and position_utilisateur > validateur_actuel['position']:
                                # Lister les validateurs qui doivent valider avant
                                validateurs_avant = []
                                for idx, tache in enumerate(flux_taches):
                                    if idx < position_utilisateur and tache.get('Validation') is None:
                                        nom = tache.get('NomValidateur') or tache.get('Validateur', 'Validateur inconnu')
                                        validateurs_avant.append(nom)
                                
                                if validateurs_avant:
                                    liste_validateurs = "\n".join([f"   • {nom}" for nom in validateurs_avant])
                                    dispatcher.utter_message(
                                        text=f"⏳ Vous ne pouvez pas encore valider la demande **{id_demande}**.\n\n"
                                             f"Les personnes suivantes doivent valider avant vous :\n{liste_validateurs}\n\n"
                                             f"💡 Vous pouvez les contacter pour accélérer le processus de validation."
                                    )
                                else:
                                    dispatcher.utter_message(
                                        text=f"⏳ Vous ne pouvez pas encore valider la demande **{id_demande}**.\n\n"
                                             f"Veuillez attendre que les validateurs précédents traitent la demande."
                                    )
                                id_demande = None
                            
                            # CAS 4: L'utilisateur a déjà validé
                            elif position_utilisateur is not None and validateur_actuel and position_utilisateur < validateur_actuel['position']:
                                dispatcher.utter_message(
                                    text=f"✅ Vous avez déjà validé la demande **{id_demande}**.\n\n"
                                         f"La demande est actuellement en attente de validation par : **{validateur_actuel['nom']}**"
                                )
                                id_demande = None
                            
                            else:
                                # Cas non prévu (sécurité)
                                dispatcher.utter_message(
                                    text=f"⚠️ Impossible de déterminer votre statut de validation pour la demande {id_demande}."
                                )
                                id_demande = None
                                
                    elif statut_id is None:
                        dispatcher.utter_message(
                            text=f"❌ La demande avec l'ID {id_demande} n'existe pas dans le système. "
                                f"Veuillez vérifier le numéro de demande et réessayer."
                        )
                        id_demande = None
                    else:
                        # Autres statuts = demande dans un état non valide pour validation/rejet
                        dispatcher.utter_message(
                            text=f"⚠️ La demande avec l'ID {id_demande} ne peut pas être traitée "
                                f"(Statut actuel: {statut_id}). Cette demande n'est pas en attente de validation."
                        )
                        id_demande = None
                else:
                    dispatcher.utter_message(
                        text=f"❌ La demande avec l'ID {id_demande} n'existe pas dans le système. "
                             f"Veuillez vérifier le numéro de demande et réessayer."
                    )
                    id_demande = None
                    
            except ValueError:
                dispatcher.utter_message(
                    text=f"⚠️ L'ID de demande '{id_demande}' n'est pas valide. "
                         f"Veuillez fournir un numéro valide."
                )
                id_demande = None
            except Exception as e:
                dispatcher.utter_message(
                    text=f"❌ Erreur lors de la vérification de la demande: {str(e)}"
                )
                logger.error(f"Erreur validation demande: {e}")
                id_demande = None
        
        # ========== DÉFINIR LES SLOTS REQUIS ==========
        required_slots = {
            "type_demande": type_demande,
            "id_demande": id_demande
        }
        
        slot_labels = {
            "type_demande": "le type de demande",
            "id_demande": "l'ID de la demande"
        }
        
        missing_slots = []
        slots_to_set = []
        
        # Vérifier les slots requis
        for slot_name, slot_value in required_slots.items():
            if slot_value is None or slot_value == "":
                missing_slots.append(slot_labels.get(slot_name, slot_name))
            else:
                if slot_name in extracted_data or \
                   (slot_name == 'id_demande' and id_demande_valide) or \
                   (slot_name == 'type_demande' and type_demande_valide):
                    slots_to_set.append(SlotSet(slot_name, slot_value))
                    logger.info(f"Slot {slot_name} défini à: {slot_value}")
        
        # Ajouter le commentaire s'il est présent (optionnel)
        if commentaire and commentaire != "":
            slots_to_set.append(SlotSet("commentaire", commentaire))
            logger.info(f"Commentaire défini à: {commentaire}")
        
        # ========== SI TOUS LES SLOTS REQUIS SONT REMPLIS ==========
        if not missing_slots:
            recap_message = "✅ Toutes les informations nécessaires ont été collectées :\n\n"
            recap_message += f"   • **Type de demande** : {type_demande}\n"
            recap_message += f"   • **ID de demande** : {id_demande}\n"
            
            if commentaire:
                recap_message += f"   • **Commentaire** : {commentaire}\n"
            
            dispatcher.utter_message(text=recap_message)
            logger.info("Tous les slots requis sont remplis, validation complète")
            return slots_to_set + [
                SlotSet("verify_validation", True),
                SlotSet("id_demande", id_demande),  # ← Forcer la conservation
                SlotSet("type_demande", type_demande),  # ← Forcer la conservation
                SlotSet("commentaire", commentaire),  # ← Forcer la conservation
                FollowupAction("action_demander_confirmation_validation")
            ]        
        # ========== SI DES INFORMATIONS MANQUENT ==========
        else:
            if len(missing_slots) == 1:
                message = f"Il manque l'information suivante : **{missing_slots[0]}**."
            else:
                missing_str = " et ".join(missing_slots)
                message = f"Il manque les informations suivantes : {missing_str}."
            
            # Messages spécifiques selon le slot manquant
            if "le type de demande" in missing_slots:
                message += "\n\n📋 Voici la liste des types de demande possibles, veuillez en sélectionner un : [DDR, DRI, DMI, DMOE](demande_type_demande)"
            
            if "l'ID de la demande" in missing_slots:
                if type_demande is not None:
                    message += f"\n\n🔢 Veuillez fournir le numéro de la {type_demande}."
                else:
                    message += "\n\n🔢 Veuillez fournir le numéro de la demande."
            
            message += "\n\n💡 Vous pouvez aussi donner toutes les informations d'un coup. 😉"
            
            dispatcher.utter_message(text=message)
            logger.info(f"Slots manquants: {missing_slots}")
            return slots_to_set + [SlotSet("verify_validation", False)]
class ActionVerifyIfAllInformationIsRejectionComplet(Action):
    """
    Action pour vérifier si tous les slots requis sont complétés.
    Slots requis: type_demande (DDR, DRI, DMI, DMOE), id_demande
    Slot optionnel: commentaire
    """

    def name(self) -> Text:
        return "action_verify_if_all_information_rejection_is_complet"

    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ========== Extraire les entités du dernier message ==========
        user_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        logger.info(f"Message utilisateur: '{user_message}'")
        logger.info(f"Entités détectées: {entities}")
        
        # Mapper les entités vers des variables
        extracted_data = {}
        for entity in entities:
            entity_name = entity.get('entity')
            entity_value = entity.get('value')
            
            if entity_name in ['id_demande', 'type_demande', 'commentaire']:
                extracted_data[entity_name] = entity_value
        
        # Récupérer les slots actuels
        id_demande = extracted_data.get('id_demande') or tracker.get_slot("id_demande")
        type_demande = extracted_data.get('type_demande') or tracker.get_slot("type_demande")
        commentaire = extracted_data.get('commentaire') or tracker.get_slot("commentaire")
        
        # Récupérer l'identifiant de l'utilisateur actuel (à adapter selon votre système)
        current_user = tracker.get_slot("user_id") or tracker.sender_id
        
        logger.info(f"Valeurs finales - ID: {id_demande}, Type: {type_demande}, Commentaire: {commentaire}")
        logger.info(f"Utilisateur actuel: {current_user}")
        
        # ========== VALIDATION TYPE DEMANDE ==========
        type_demande_valide = False
        types_valides = ["DDR", "DRI", "DMI", "DMOE"]
        
        if type_demande is not None and type_demande != "":
            type_demande_upper = type_demande.upper()
            
            if type_demande_upper in types_valides:
                type_demande = type_demande_upper
                type_demande_valide = True
                logger.info(f"Type de demande valide: {type_demande}")
            else:
                dispatcher.utter_message(
                    text=f"⚠️ Le type de demande '{type_demande}' n'est pas valide. "
                         f"Les types acceptés sont : **DDR**, **DRI**, **DMI**, **DMOE**.\n\n"
                         f"📋 Veuillez sélectionner l'un de ces types."
                )
                type_demande = None
        
        # ========== VALIDATION ID DEMANDE ET VALIDATEUR ==========
        id_demande_valide = False
        
        if id_demande is not None and id_demande != "":
            try:
                demande_id_int = int(id_demande)
                
                # Importer le service de recherche
                searcher = DemandeSearchService()
                demande_result = searcher.search_with_details(demande_id_int)
                logger.info(f"Résultat recherche demande {demande_id_int}: {demande_result}")
                
                if demande_result:
                    statut_id = demande_result.get('StatutId')
                    
                    if statut_id == 2:
                        # Statut 2 = demande en attente de validation
                        
                        # ========== VÉRIFICATION DU VALIDATEUR ACTUEL ==========
                        flux_taches = demande_result.get('MpFluxTaches', [])
                        
                        if not flux_taches:
                            dispatcher.utter_message(
                                text=f"⚠️ Aucun flux de validation n'est configuré pour la demande {id_demande}."
                            )
                            id_demande = None
                        else:
                            # Trouver le validateur actuel (premier avec Validation NULL)
                            validateur_actuel = None
                            validateurs_precedents = []
                            position_utilisateur = None
                            utilisateur_dans_liste = False
                            
                            for idx, tache in enumerate(flux_taches):
                                validateur = tache.get('Validateur')
                                validation = tache.get('Validation')
                                
                                # Vérifier si l'utilisateur est dans la liste des validateurs
                                if validateur and validateur.lower() == current_user.lower():
                                    utilisateur_dans_liste = True
                                    position_utilisateur = idx
                                
                                # Trouver le premier validateur avec Validation NULL
                                if validation is None and validateur_actuel is None:
                                    validateur_actuel = {
                                        'validateur': validateur,
                                        'position': idx,
                                        'nom': tache.get('NomValidateur', validateur)
                                    }
                                elif validation is None:
                                    # Ajouter aux validateurs précédents si pas encore validé et avant le validateur actuel
                                    pass
                                elif validation is not None and validateur_actuel is None:
                                    # Validateurs qui ont déjà validé avant le validateur actuel
                                    validateurs_precedents.append({
                                        'validateur': validateur,
                                        'nom': tache.get('NomValidateur', validateur)
                                    })
                            
                            logger.info(f"Validateur actuel: {validateur_actuel}")
                            logger.info(f"Utilisateur dans la liste: {utilisateur_dans_liste}")
                            logger.info(f"Position utilisateur: {position_utilisateur}")
                            
                            # CAS 1: L'utilisateur n'est pas dans la liste des validateurs
                            if not utilisateur_dans_liste:
                                dispatcher.utter_message(
                                    text=f"🚫 Vous ne faites pas partie de la liste des validateurs pour la demande **{id_demande}**.\n\n"
                                         f"Seuls les validateurs désignés peuvent traiter cette demande."
                                )
                                id_demande = None
                            
                            # CAS 2: L'utilisateur est le validateur actuel
                            elif validateur_actuel and validateur_actuel['validateur'].lower() == current_user.lower():
                                id_demande_valide = True
                                logger.info(f"✅ L'utilisateur {current_user} est le validateur actuel pour la demande {id_demande}")
                            
                            # CAS 3: L'utilisateur doit attendre son tour
                            elif position_utilisateur is not None and validateur_actuel and position_utilisateur > validateur_actuel['position']:
                                # Lister les validateurs qui doivent valider avant
                                validateurs_avant = []
                                for idx, tache in enumerate(flux_taches):
                                    if idx < position_utilisateur and tache.get('Validation') is None:
                                        nom = tache.get('NomValidateur') or tache.get('Validateur', 'Validateur inconnu')
                                        validateurs_avant.append(nom)
                                
                                if validateurs_avant:
                                    liste_validateurs = "\n".join([f"   • {nom}" for nom in validateurs_avant])
                                    dispatcher.utter_message(
                                        text=f"⏳ Vous ne pouvez pas encore valider la demande **{id_demande}**.\n\n"
                                             f"Les personnes suivantes doivent valider avant vous :\n{liste_validateurs}\n\n"
                                             f"💡 Vous pouvez les contacter pour accélérer le processus de validation."
                                    )
                                else:
                                    dispatcher.utter_message(
                                        text=f"⏳ Vous ne pouvez pas encore valider la demande **{id_demande}**.\n\n"
                                             f"Veuillez attendre que les validateurs précédents traitent la demande."
                                    )
                                id_demande = None
                            
                            # CAS 4: L'utilisateur a déjà validé
                            elif position_utilisateur is not None and validateur_actuel and position_utilisateur < validateur_actuel['position']:
                                dispatcher.utter_message(
                                    text=f"✅ Vous avez déjà validé la demande **{id_demande}**.\n\n"
                                         f"La demande est actuellement en attente de validation par : **{validateur_actuel['nom']}**"
                                )
                                id_demande = None
                            
                            else:
                                # Cas non prévu (sécurité)
                                dispatcher.utter_message(
                                    text=f"⚠️ Impossible de déterminer votre statut de validation pour la demande {id_demande}."
                                )
                                id_demande = None
                                
                    elif statut_id is None:
                        dispatcher.utter_message(
                            text=f"❌ La demande avec l'ID {id_demande} n'existe pas dans le système. "
                                f"Veuillez vérifier le numéro de demande et réessayer."
                        )
                        id_demande = None
                    else:
                        # Autres statuts = demande dans un état non valide pour validation/rejet
                        dispatcher.utter_message(
                            text=f"⚠️ La demande avec l'ID {id_demande} ne peut pas être traitée "
                                f"(Statut actuel: {statut_id}). Cette demande n'est pas en attente de validation."
                        )
                        id_demande = None
                else:
                    dispatcher.utter_message(
                        text=f"❌ La demande avec l'ID {id_demande} n'existe pas dans le système. "
                             f"Veuillez vérifier le numéro de demande et réessayer."
                    )
                    id_demande = None
                    
            except ValueError:
                dispatcher.utter_message(
                    text=f"⚠️ L'ID de demande '{id_demande}' n'est pas valide. "
                         f"Veuillez fournir un numéro valide."
                )
                id_demande = None
            except Exception as e:
                dispatcher.utter_message(
                    text=f"❌ Erreur lors de la vérification de la demande: {str(e)}"
                )
                logger.error(f"Erreur validation demande: {e}")
                id_demande = None
        
        # ========== DÉFINIR LES SLOTS REQUIS ==========
        required_slots = {
            "type_demande": type_demande,
            "id_demande": id_demande
        }
        
        slot_labels = {
            "type_demande": "le type de demande",
            "id_demande": "l'ID de la demande"
        }
        
        missing_slots = []
        slots_to_set = []
        
        # Vérifier les slots requis
        for slot_name, slot_value in required_slots.items():
            if slot_value is None or slot_value == "":
                missing_slots.append(slot_labels.get(slot_name, slot_name))
            else:
                if slot_name in extracted_data or \
                   (slot_name == 'id_demande' and id_demande_valide) or \
                   (slot_name == 'type_demande' and type_demande_valide):
                    slots_to_set.append(SlotSet(slot_name, slot_value))
                    logger.info(f"Slot {slot_name} défini à: {slot_value}")
        
        # Ajouter le commentaire s'il est présent (optionnel)
        if commentaire and commentaire != "":
            slots_to_set.append(SlotSet("commentaire", commentaire))
            logger.info(f"Commentaire défini à: {commentaire}")
        
        # ========== SI TOUS LES SLOTS REQUIS SONT REMPLIS ==========
        if not missing_slots:
            recap_message = "✅ Toutes les informations nécessaires ont été collectées :\n\n"
            recap_message += f"   • **Type de demande** : {type_demande}\n"
            recap_message += f"   • **ID de demande** : {id_demande}\n"
            
            if commentaire:
                recap_message += f"   • **Commentaire** : {commentaire}\n"
            
            dispatcher.utter_message(text=recap_message)
            logger.info("Tous les slots requis sont remplis, validation complète")
            return slots_to_set + [
                SlotSet("verify_rejection", True),
                SlotSet("id_demande", id_demande),  # ← Forcer la conservation
                SlotSet("type_demande", type_demande),  # ← Forcer la conservation
                SlotSet("commentaire", commentaire),  # ← Forcer la conservation
                FollowupAction("action_demander_confirmation_rejet")
            ]        
        # ========== SI DES INFORMATIONS MANQUENT ==========
        else:
            if len(missing_slots) == 1:
                message = f"Il manque l'information suivante : **{missing_slots[0]}**."
            else:
                missing_str = " et ".join(missing_slots)
                message = f"Il manque les informations suivantes : {missing_str}."
            
            # Messages spécifiques selon le slot manquant
            if "le type de demande" in missing_slots:
                message += "\n\n📋 Voici la liste des types de demande possibles, veuillez en sélectionner un : [DDR, DRI, DMI, DMOE](demande_type_demande)"
            
            if "l'ID de la demande" in missing_slots:
                if type_demande is not None:
                    message += f"\n\n🔢 Veuillez fournir le numéro de la {type_demande}."
                else:
                    message += "\n\n🔢 Veuillez fournir le numéro de la demande."
            
            message += "\n\n💡 Vous pouvez aussi donner toutes les informations d'un coup. 😉"
            
            dispatcher.utter_message(text=message)
            logger.info(f"Slots manquants: {missing_slots}")
            return slots_to_set + [SlotSet("verify_rejection", False)]

class ActionDemanderConfirmationValidation(Action):
    """
    Action pour demander confirmation avant de valider une demande.
    Affiche un récapitulatif des informations et demande une confirmation.
    CORRIGÉ : Préserve TOUS les slots nécessaires aux conditions des rules.
    """

    def name(self) -> Text:
        return "action_demander_confirmation_validation"
        
    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Demander confirmation avant de valider la demande"""
        
        # ========== RÉCUPÉRER TOUS LES SLOTS CRITIQUES ==========
        id_demande = tracker.get_slot("id_demande")
        type_demande = tracker.get_slot("type_demande")
        commentaire = tracker.get_slot("commentaire")
        verify_rejection = tracker.get_slot("verify_rejection")
        
        # ✅ SLOTS CRITIQUES POUR LES CONDITIONS DES RULES
        role = tracker.get_slot("role")
        intention_demande = tracker.get_slot("intention_demande")
        validation_intent = tracker.get_slot("validation_intent")
        permission = tracker.get_slot("permission")
        
        logger.info(f"Demande de confirmation validation - ID: {id_demande}, Type: {type_demande}")
        logger.info(f"Slots critiques - role: {role}, intention: {intention_demande}, validation_intent: {validation_intent}")
        
        # ========== CONSTRUIRE LE MESSAGE DE CONFIRMATION ==========
        message = f"""📋 **Récapitulatif de la validation de demande**

🆔 **Demande** : {type_demande} #{id_demande}
"""
        
        # Ajouter le commentaire s'il existe
        if commentaire and commentaire != "":
            message += f"💬 **Commentaire** : {commentaire}\n"
        
        message += "\n❓ **Voulez-vous valider cette demande ?** [Oui,Non](confirmation)"
        
        dispatcher.utter_message(text=message)
        
        logger.info("Message de confirmation envoyé - Préservation de tous les slots")
        
        # ========== RETOURNER TOUS LES SLOTS NÉCESSAIRES ==========
        return [
            # Slots de données
            SlotSet("id_demande", id_demande),
            SlotSet("type_demande", type_demande),
            SlotSet("commentaire", commentaire),
            
            # Slots de contrôle de flux
            SlotSet("verify_validation", True),  # ← FORCER À TRUE
            SlotSet("verify_rejection", verify_rejection),
            
            # ✅ SLOTS CRITIQUES POUR LES CONDITIONS DES RULES
            SlotSet("role", role),
            SlotSet("intention_demande", intention_demande),
            SlotSet("validation_intent", validation_intent),
            SlotSet("permission", permission)
        ]


class ActionDemanderConfirmationRejet(Action):
    """
    Action pour demander confirmation avant de rejeter une demande.
    Affiche un récapitulatif des informations et demande une confirmation.
    CORRIGÉ : Préserve TOUS les slots nécessaires aux conditions des rules.
    """

    def name(self) -> Text:
        return "action_demander_confirmation_rejet"
        
    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Demander confirmation avant de rejeter la demande"""
        
        # ========== RÉCUPÉRER TOUS LES SLOTS CRITIQUES ==========
        id_demande = tracker.get_slot("id_demande")
        type_demande = tracker.get_slot("type_demande")
        commentaire = tracker.get_slot("commentaire")
        verify_validation = tracker.get_slot("verify_validation")
        
        # ✅ SLOTS CRITIQUES POUR LES CONDITIONS DES RULES
        role = tracker.get_slot("role")
        intention_demande = tracker.get_slot("intention_demande")
        rejection_intent = tracker.get_slot("rejection_intent")
        permission = tracker.get_slot("permission")
        
        logger.info(f"Demande de confirmation rejet - ID: {id_demande}, Type: {type_demande}")
        logger.info(f"Slots critiques - role: {role}, intention: {intention_demande}, rejection_intent: {rejection_intent}")
        
        # ========== CONSTRUIRE LE MESSAGE DE CONFIRMATION ==========
        message = f"""📋 **Récapitulatif du rejet de demande**

🆔 **Demande** : {type_demande} #{id_demande}
"""
        
        # Ajouter le commentaire s'il existe
        if commentaire and commentaire != "":
            message += f"💬 **Commentaire** : {commentaire}\n"
        
        message += "\n❓ **Voulez-vous rejeter cette demande ?** [Oui,Non](confirmation)"
        
        dispatcher.utter_message(text=message)
        
        logger.info("Message de confirmation envoyé - Préservation de tous les slots")
        
        # ========== RETOURNER TOUS LES SLOTS NÉCESSAIRES ==========
        return [
            # Slots de données
            SlotSet("id_demande", id_demande),
            SlotSet("type_demande", type_demande),
            SlotSet("commentaire", commentaire),
            
            # Slots de contrôle de flux
            SlotSet("verify_validation", verify_validation),
            SlotSet("verify_rejection", True),  # ← FORCER À TRUE
            
            # ✅ SLOTS CRITIQUES POUR LES CONDITIONS DES RULES
            SlotSet("role", role),
            SlotSet("intention_demande", intention_demande),
            SlotSet("rejection_intent", rejection_intent),
            SlotSet("permission", permission)
        ]
class ActionSoumettreValidationRecrutement(Action):
    """
    Action pour soumettre la validation d'une demande de recrutement.
    Valide la FluxTache en mettant à jour son état et en l'envoyant au backend.
    """

    def name(self) -> Text:
        return "action_soumettre_validation_recrutement"
        
    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Soumettre la validation de la demande"""
        
        # Récupérer les slots
        sender_id = tracker.sender_id
        id_demande = tracker.get_slot("id_demande")
        type_demande = tracker.get_slot("type_demande")
        commentaire = tracker.get_slot("commentaire")
        verify_validation = tracker.get_slot("verify_validation")
        verify_rejection = tracker.get_slot("verify_rejection")
        username = sender_id
        
        logger.info(f"Soumission validation - ID: {id_demande}, Type: {type_demande}, User: {sender_id}")
        
        # Vérifier que les informations nécessaires sont présentes
        if not id_demande or not username:
            dispatcher.utter_message(
                text="❌ Impossible de soumettre la validation : informations manquantes (ID demande)."
            )
            return [
                SlotSet("id_demande", id_demande),
                SlotSet("type_demande", type_demande),
                SlotSet("commentaire", commentaire),
                SlotSet("verify_validation", verify_validation),
                SlotSet("verify_rejection", verify_rejection)
            ]
        
        try:
            # Initialiser le service backend
            backend_service = BackendService()
            
            # Convertir l'ID en entier
            demande_id_int = int(id_demande)
            
            # 1. Récupérer la FluxTache pour ce validateur et cette demande
            logger.info(f"Récupération FluxTache pour demande {demande_id_int} et validateur {username}")
            
            # Choisir la méthode selon le type de demande
            if type_demande == "DMOE":
                flux_tache = backend_service.get_flux_tache_by_demande_manoeuvre_and_validateur(
                    demande_id_int, 
                    username
                )
            else:
                flux_tache = backend_service.get_flux_tache_by_demande_and_validateur(
                    demande_id_int, 
                    username
                )
            
            logger.info(f"FluxTache trouvée: {flux_tache}")
            if not flux_tache:
                dispatcher.utter_message(
                    text=f"❌ Aucune tâche de validation trouvée pour la demande #{id_demande} et le validateur {username}. "
                         f"Veuillez contacter l'administrateur si le problème persiste."
                )
                return []
            
            
            # 2. Récupérer les informations complètes de l'utilisateur
            user_details = backend_service.get_user_by_login(username)
            
            if not user_details:
                logger.warning(f"Détails utilisateur non trouvés pour {username}")
                nom_validateur = username
            else:
                nom_validateur = user_details.get('FullName', username)
            
            # 3. Mettre à jour la FluxTache
            flux_tache['Commentaire'] = commentaire if commentaire else ""
            flux_tache['Validateur'] = username
            flux_tache['Etat'] = True
            flux_tache['Validation'] = True
            flux_tache['DateValidation'] = datetime.now().isoformat()
            flux_tache['NomValidateur'] = nom_validateur
            
            logger.info(f"FluxTache mise à jour: {flux_tache}")
            
            # 4. Vérifier que l'ID de tâche existe
            id_tache = flux_tache.get('IdTache')
            
            if not id_tache or id_tache <= 0:
                dispatcher.utter_message(
                    text="❌ ID de tâche invalide. Impossible de soumettre la validation. "
                         "Veuillez contacter l'administrateur."
                )
                return []
            
            # 5. Valider la demande via l'API
            logger.info(f"Validation de la demande via API - IdTache: {id_tache}")
            
            if type_demande == "DMOE":
                result = backend_service.validate_mp_demande_manoeuvre(id_tache, flux_tache)
            else:
                result = backend_service.validate_mp_demande(id_tache, flux_tache)
            logger.info(f"Résultat de la validation API: {result}")
            # Succès
            message = f"""
✅ **La demande {type_demande} a été validée avec succès !**
📋 ** {type_demande} #{id_demande} **
👤 **Validé par** : {nom_validateur}
📅 **Date** : {datetime.now().strftime('%d/%m/%Y à %H:%M')}
"""
            
            if commentaire:
                message += f"\n💬 **Commentaire** : {commentaire}"
            
            dispatcher.utter_message(text=message)
            logger.info(f"Validation soumise avec succès pour la demande {id_demande}")
            
            # Réinitialiser tous les slots
            return [
                SlotSet("id_demande", None),
                SlotSet("type_demande", None),
                SlotSet("commentaire", None),
                SlotSet("verify_validation", None),
                SlotSet("verify_rejection", None)
            ]
        
        except ValueError:
            dispatcher.utter_message(
                text=f"⚠️ L'ID de demande '{id_demande}' n'est pas valide. "
                     f"Veuillez contacter l'administrateur."
            )
            logger.error(f"ID demande invalide: {id_demande}")
            return []
        
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ Erreur lors de la soumission de la validation. "
                     f"Veuillez contacter l'administrateur."
            )
            logger.error(f"Erreur lors de la soumission de validation: {e}")
            import traceback
            traceback.print_exc()
            return []
class ActionSoumettreRejetRecrutement(Action):
    """
    Action pour soumettre le rejet d'une demande de recrutement.
    Rejette la FluxTache en mettant Validation à False et en l'envoyant au backend.
    """

    def name(self) -> Text:
        return "action_soumettre_rejet_recrutement"
        
    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Soumettre le rejet de la demande"""
        
        # Récupérer les slots
        
        sender_id = tracker.sender_id
        id_demande = tracker.get_slot("id_demande")
        type_demande = tracker.get_slot("type_demande")
        commentaire = tracker.get_slot("commentaire")
        username = sender_id  # Le validateur actuel
        
        logger.info(f"Soumission rejet - ID: {id_demande}, Type: {type_demande}, User: {username}")
        
        # Vérifier que les informations nécessaires sont présentes
        if not id_demande or not username:
            dispatcher.utter_message(
                text="❌ Impossible de soumettre le rejet : informations manquantes (ID demande ou utilisateur)."
            )
            return []
        
        try:
            # Initialiser le service backend
            backend_service = BackendService()
            
            # Convertir l'ID en entier
            demande_id_int = int(id_demande)
            
            # 1. Récupérer la FluxTache pour ce validateur et cette demande
            logger.info(f"Récupération FluxTache pour demande {demande_id_int} et validateur {username}")
            
            # Choisir la méthode selon le type de demande
            if type_demande == "DMOE":
                flux_tache = backend_service.get_flux_tache_by_demande_manoeuvre_and_validateur(
                    demande_id_int, 
                    username
                )
            else:
                flux_tache = backend_service.get_flux_tache_by_demande_and_validateur(
                    demande_id_int, 
                    username
                )
            
            logger.info(f"FluxTache trouvée: {flux_tache}")
            
            if not flux_tache:
                dispatcher.utter_message(
                    text=f"❌ Aucune tâche de validation trouvée pour la demande #{id_demande} et le validateur {username}. "
                         f"Veuillez contacter l'administrateur si le problème persiste."
                )
                return []
            
            
            # 2. Récupérer les informations complètes de l'utilisateur
            user_details = backend_service.get_user_by_login(username)
            
            if not user_details:
                logger.warning(f"Détails utilisateur non trouvés pour {username}")
                nom_validateur = username
            else:
                nom_validateur = user_details.get('FullName', username)
            
            # 3. Mettre à jour la FluxTache pour REJET
            flux_tache['Commentaire'] = commentaire if commentaire else ""
            flux_tache['Validateur'] = username
            flux_tache['Etat'] = True
            flux_tache['Validation'] = False  # ← REJET
            flux_tache['DateValidation'] = datetime.now().isoformat()
            flux_tache['NomValidateur'] = nom_validateur
            
            logger.info(f"FluxTache mise à jour (rejet): {flux_tache}")
            
            # 4. Vérifier que l'ID de tâche existe
            id_tache = flux_tache.get('IdTache')
            
            if not id_tache or id_tache <= 0:
                dispatcher.utter_message(
                    text="❌ ID de tâche invalide. Impossible de soumettre le rejet. "
                         "Veuillez contacter l'administrateur."
                )
                return []
            
            # 5. Valider (rejeter) la demande via l'API
            logger.info(f"Rejet de la demande via API - IdTache: {id_tache}")
            
            if type_demande == "DMOE":
                result = backend_service.validate_mp_demande_manoeuvre(id_tache, flux_tache)
            else:
                result = backend_service.validate_mp_demande(id_tache, flux_tache)
            logger.info(f"Résultat du rejet API: {result}")
            message = f"""
❌ **La demande {type_demande} a été rejetée avec succès !**

📋 ** {type_demande} #{id_demande} **
👤 **Validé par** : {nom_validateur}
📅 **Date** : {datetime.now().strftime('%d/%m/%Y à %H:%M')}
"""
            
            if commentaire:
                message += f"\n💬 **Motif du rejet** : {commentaire}"
            
            dispatcher.utter_message(text=message)
            logger.info(f"Rejet soumis avec succès pour la demande {id_demande}")
            
            # Réinitialiser tous les slots
            return [
                SlotSet("id_demande", None),
                SlotSet("type_demande", None),
                SlotSet("commentaire", None),
                SlotSet("verify_validation", None),
                SlotSet("verify_rejection", None)
            ]
        
        except ValueError:
            dispatcher.utter_message(
                text=f"⚠️ L'ID de demande '{id_demande}' n'est pas valide. "
                     f"Veuillez contacter l'administrateur."
            )
            logger.error(f"ID demande invalide: {id_demande}")
            return []
        
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ Erreur lors de la soumission du rejet. "
                     f"Veuillez contacter l'administrateur."
            )
            logger.error(f"Erreur lors de la soumission du rejet: {e}")
            import traceback
            traceback.print_exc()
            return []