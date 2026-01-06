from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, FollowupAction
import re
from rapidfuzz import fuzz, process

import logging

# Importer les services nécessaires
from actions.services.Calculate.DDR_calcul import DemandeSearchService
from actions.services.Calculate.Flux_calcul import FluxSearchService
from actions.services.Calculate.RechercheNom import UserSearchService
from actions.services.ddr_service import BackendService

from actions.Middleware.message_deduplicator import deduplicate_messages

logger = logging.getLogger(__name__)
def extract_and_validate_validateurs(
    entities: List[Dict],
    current_list: List[str],
    dispatcher: CollectingDispatcher
) -> tuple[List[str], List[Dict[Text, Any]]]:
    """
    Extrait et valide les noms de validateurs depuis les entités détectées.
    Recherche automatiquement un flux correspondant si des validateurs sont ajoutés.
    
    IMPORTANT: À chaque fois que l'utilisateur donne une liste de validateurs,
    la liste est RÉINITIALISÉE à cette nouvelle liste (pas d'accumulation).
    
    RECHERCHE STRICTE: Utilise search_by_strict_validator_sequence pour garantir
    que seuls les flux avec EXACTEMENT ces validateurs (et pas d'autres) sont trouvés.
    
    Args:
        entities: Liste des entités extraites du message
        current_list: Liste actuelle des validateurs (ignorée si de nouveaux validateurs sont détectés)
        dispatcher: Pour envoyer des messages à l'utilisateur
        
    Returns:
        tuple: (liste_validateurs_mise_à_jour, liste_des_SlotSet)
    """
    
    # Récupérer toutes les entités 'nom_validateur'
    validateur_entities = [e for e in entities if e.get('entity') == 'nom_validateur']
    
    if not validateur_entities:
        logger.info("Aucune entité 'nom_validateur' détectée")
        return current_list, []
    
    # Nettoyer les noms extraits
    noms_a_valider = []
    stop_words = ['sont', 'et', 'le', 'la', 'les', 'un', 'une', 'des']
    
    for entity in validateur_entities:
        nom_brut = entity.get('value', '').strip()
        mots = nom_brut.split()
        nom_nettoye = ' '.join([m for m in mots if m.lower() not in stop_words])
        
        if nom_nettoye and len(nom_nettoye) > 2:
            noms_a_valider.append(nom_nettoye)
            logger.info(f"Nom de validateur à valider: '{nom_nettoye}'")
    
    if not noms_a_valider:
        logger.warning("Aucun nom valide après nettoyage")
        return current_list, []
    
    # Initialiser le service de recherche utilisateur
    user_service = UserSearchService()
    
    # RÉINITIALISER la liste des validateurs (ne pas conserver l'ancienne liste)
    validateurs_valides = []
    slots_to_set = []
    
    logger.info(f"🔄 RÉINITIALISATION de la liste des validateurs. Nouvelle liste à valider: {noms_a_valider}")
    
    # Valider chaque nom
    for nom in noms_a_valider:
        try:
            results = user_service.search_user_by_name(nom, max_results=5)
            
            if not results:
                dispatcher.utter_message(
                    text=f"❌ Aucun utilisateur trouvé pour '{nom}'. "
                         f"Veuillez vérifier le nom du validateur."
                )
                logger.warning(f"Aucun utilisateur trouvé pour '{nom}'")
                continue
                
            elif len(results) == 1:
                user_trouve = results[0]
                full_name = user_trouve.get('FullName')
                matricule = user_trouve.get('Matricule')
                
                # Ajouter directement le validateur (pas de vérification de doublon car liste réinitialisée)
                validateurs_valides.append(full_name)
                
                dispatcher.utter_message(
                    text=f"✅ Validateur ajouté : **{full_name}** (Matricule: {matricule})"
                )
                logger.info(f"Validateur validé et ajouté: {full_name}")
                    
            else:
                top_results = results[:5]
                message = f"🔍 Plusieurs utilisateurs correspondent à '{nom}'. Voici les 5 plus probables :\n\n"
                messages_list = []
                
                for idx, user in enumerate(top_results, 1):
                    full_name = user.get('FullName')
                    matricule = user.get('Matricule')
                    user_message = f"{idx}. {full_name} (Matricule: {matricule})\n"
                    messages_list.append(user_message)
                
                escaped_messages = [m.replace('"', '\\"') for m in messages_list]
                message = '[ "' + '" , "'.join(escaped_messages) + '" ](Liste_validateur_possible)'
                message += f"\n\n💡 Veuillez préciser le nom exact du validateur '{nom}'."
                
                dispatcher.utter_message(text=message)
                logger.info(f"Plusieurs correspondances pour '{nom}', demande de clarification")
                
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ Erreur lors de la recherche du validateur '{nom}': {str(e)}"
            )
            logger.error(f"Erreur UserSearchService pour '{nom}': {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # ========== RECHERCHE AUTOMATIQUE DU FLUX (RECHERCHE STRICTE) ==========
    if validateurs_valides and len(validateurs_valides) > 0:
        try:
            flux_service = FluxSearchService(default_threshold=85, default_limit=5)
            
            logger.info(f"🔍 RECHERCHE STRICTE d'un flux avec EXACTEMENT ces validateurs: {validateurs_valides}")
            logger.info(f"   → Nombre de validateurs: {len(validateurs_valides)}")
            logger.info(f"   → Les positions V{len(validateurs_valides) + 1} à V5 doivent être VIDES")
            
            # ⭐ UTILISATION DE LA RECHERCHE STRICTE ⭐
            flux_result = flux_service.search_by_strict_validator_sequence(
                validators=validateurs_valides,
                threshold=85,  # Seuil ajustable selon vos besoins
                limit=5,
                search_type='full_name',
                typeflux='AUTRE'
            )
            
            # ========== CAS 1: UN SEUL FLUX TROUVÉ (dict) ==========
            if flux_result and isinstance(flux_result, dict):
                # Extraire le flux (peut avoir 'matched_positions' ou être direct)
                if 'matched_positions' in flux_result:
                    flux = flux_result['flux']
                    matched_positions = flux_result['matched_positions']
                else:
                    flux = flux_result
                    matched_positions = []
                
                flux_id = flux.get('IdFlux')
                flux_nom = flux.get('NomFluxMouvement')
                flux_type = flux.get('TypeFlux', 'N/A')
                
                # Mettre à jour les slots du flux
                slots_to_set.append(SlotSet("nom_flux", flux_nom))
                slots_to_set.append(SlotSet("nom_flux_id", flux_id))
                
                # Afficher le message de confirmation
                message = f"✅ Flux trouvé (séquence stricte) : **{flux_nom}**\n\n"
                message += "📋 **Séquence de validateurs :**\n"
                
                # Afficher les validateurs correspondants
                for i in range(1, len(validateurs_valides) + 1):
                    username = flux.get(f'V{i}')
                    full_name = flux.get(f'V{i}UserName')
                    if username and username != 'None':
                        message += f"   ✓ **V{i}** : {full_name} ({username})\n"
                
                # Indiquer les positions vides (important pour la compréhension)
                if len(validateurs_valides) < 5:
                    message += "\n📌 **Positions vides (comme requis) :**\n"
                    for i in range(len(validateurs_valides) + 1, 6):
                        message += f"   ○ V{i} : (vide)\n"
                
                dispatcher.utter_message(text=message)
                logger.info(f"✅ Flux stricte trouvé et enregistré: {flux_nom}")
            
            # ========== CAS 2: PLUSIEURS FLUX TROUVÉS (list) ==========
            elif flux_result and isinstance(flux_result, list) and len(flux_result) > 0:
                logger.info(f"📋 {len(flux_result)} flux trouvés avec séquence stricte correspondante")
                
                # Tous les résultats de search_by_strict_validator_sequence ont déjà
                # les positions vides vérifiées, donc on peut traiter directement
                
                if len(flux_result) == 1:
                    # Un seul flux, le sélectionner automatiquement
                    match = flux_result[0]
                    flux = match['flux']
                    flux_id = flux.get('IdFlux')
                    flux_nom = flux.get('NomFluxMouvement')
                    flux_type = flux.get('TypeFlux', 'N/A')
                    matched_positions = match.get('matched_positions', [])
                    
                    slots_to_set.append(SlotSet("nom_flux", flux_nom))
                    slots_to_set.append(SlotSet("nom_flux_id", flux_id))
                    
                    message = f"✅ Flux trouvé (séquence stricte) : **{flux_nom}**\n\n"
                    message += "📋 **Séquence de validateurs :**\n"
                    
                    for i in range(1, len(validateurs_valides) + 1):
                        username = flux.get(f'V{i}')
                        full_name = flux.get(f'V{i}UserName')
                        if username and username != 'None':
                            message += f"   ✓ **V{i}** : {full_name} ({username})\n"
                    
                    if len(validateurs_valides) < 5:
                        message += "\n📌 **Positions vides (comme requis) :**\n"
                        for i in range(len(validateurs_valides) + 1, 6):
                            message += f"   ○ V{i} : (vide)\n"
                    
                    dispatcher.utter_message(text=message)
                    logger.info(f"✅ Flux stricte unique enregistré: {flux_nom}")
                
                else:
                    # Plusieurs flux avec la même séquence stricte, demander à l'utilisateur de choisir
                    # NE PAS mettre à jour les slots nom_flux et nom_flux_id
                    slots_to_set.append(SlotSet("nom_flux", None))
                    slots_to_set.append(SlotSet("nom_flux_id", None))
                    
                    message = f"🔍 **{len(flux_result)} flux correspondent** à cette séquence stricte de validateurs :\n\n"
                    
                    for idx, match in enumerate(flux_result, 1):
                        flux = match['flux']
                        flux_nom = flux.get('NomFluxMouvement')
                        flux_id = flux.get('IdFlux')
                        
                        message += f"{idx}. **{flux_nom}**\n"
                        
                        # Afficher la séquence de validateurs de ce flux
                        validateurs_flux = []
                        for i in range(1, len(validateurs_valides) + 1):
                            username = flux.get(f'V{i}')
                            full_name = flux.get(f'V{i}UserName')
                            if username and username != 'None':
                                validateurs_flux.append(f"V{i}: {full_name}")
                        
                        if validateurs_flux:
                            message += f"   Validateurs : {', '.join(validateurs_flux)}"
                        
                        # Indiquer les positions vides
                        if len(validateurs_valides) < 5:
                            empty_positions = [f"V{i}" for i in range(len(validateurs_valides) + 1, 6)]
                            message += f", {', '.join(empty_positions)}: (vides)"
                        
                        message += "\n\n"
                    
                    message += "💡 **Veuillez préciser le nom du flux que vous souhaitez utiliser**."
                    
                    dispatcher.utter_message(text=message)
                    logger.info(f"Plusieurs flux stricts trouvés ({len(flux_result)}), demande de clarification")
            
            # ========== CAS 3: AUCUN FLUX TROUVÉ ==========
            else:
                # Aucun flux trouvé avec la séquence stricte - VIDER les slots
                slots_to_set.append(SlotSet("nom_flux", None))
                slots_to_set.append(SlotSet("nom_flux_id", None))
                
                message = "ℹ️ Aucun flux trouvé avec **EXACTEMENT** cette séquence de validateurs :\n\n"
                for idx, validateur in enumerate(validateurs_valides, 1):
                    message += f"   • V{idx} : {validateur}\n"
                
                if len(validateurs_valides) < 5:
                    message += f"\n   (Et V{len(validateurs_valides) + 1} à V5 doivent être vides)\n"
                
                message += "\n💡 **Options :**\n"
                message += "   • Ajouter plus de validateurs (exemple : \"V2 est [nom]\")\n"
                message += "   • Spécifier directement le nom du flux\n"
                message += "   • Vérifier que le flux existe avec exactement ces validateurs"
                
                dispatcher.utter_message(text=message)
                logger.info(f"❌ Aucun flux stricte trouvé pour les validateurs: {validateurs_valides}")
                logger.info("🔄 Slots nom_flux et nom_flux_id vidés (None)")
        
        except Exception as e:
            logger.error(f"❌ Erreur lors de la recherche stricte automatique du flux: {e}")
            import traceback
            traceback.print_exc()
            
            # En cas d'erreur, vider les slots
            slots_to_set.append(SlotSet("nom_flux", None))
            slots_to_set.append(SlotSet("nom_flux_id", None))
    
    # Mettre à jour le slot avec la liste complète des validateurs
    if validateurs_valides:
        slots_to_set.append(SlotSet("nom_validateur_list", validateurs_valides))
        logger.info(f"✅ Liste des validateurs mise à jour: {validateurs_valides}")
    
    return validateurs_valides, slots_to_set

# ========== ACTIONS EXISTANTES MODIFIÉES ==========

class ActionResetSlotsBeforeFlux(Action):
    def name(self) -> Text:
        return "action_reset_slots_before_flux"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        slots_to_keep = ["intention_demande", "role", "username", "session_started_metadata"]
        
        return [
            SlotSet(slot, None) 
            for slot in tracker.slots.keys() 
            if slot not in slots_to_keep
        ]
class ActionVerifyIfAllInformationFluxIsComplet(Action):
    def name(self) -> Text:
        return "action_verify_if_all_information_flux_is_complet"

    def extract_responsable_rh(self, text: str, entities: List[Dict]) -> str:
        """
        Extrait le nom complet du responsable RH depuis le texte
        en priorisant les noms complets (3+ mots)
        """
        # Chercher d'abord dans les entités
        rh_entities = [e for e in entities if e.get('entity') == 'responsable_rh']
        
        if rh_entities:
            # Trier par longueur décroissante pour prioriser les noms complets
            rh_entities.sort(key=lambda x: len(x.get('value', '')), reverse=True)
            best_match = rh_entities[0].get('value')
            logger.info(f"RH extrait des entités: '{best_match}'")
            return best_match
        
        # Fallback: recherche avec regex pour noms complets après "RH"
        patterns = [
            r'(?:RH|responsable RH|DRH|gestionnaire RH|Le RH)\s+(?:est|c\'est|:)?\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,})',
            r'([A-Z][A-Z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+)',  # Format NOM Prénom Prénom
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                extracted = match.group(1).strip()
                logger.info(f"RH extrait via regex: '{extracted}'")
                return extracted
        
        logger.warning(f"Aucun RH extrait du texte: '{text}'")
        return None

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
        
        # ========== TRAITER LES VALIDATEURS AVEC LA FONCTION RÉUTILISABLE ==========
        current_validateurs = tracker.get_slot("nom_validateur_list") or []
        validateurs_mis_a_jour, validateur_slots = extract_and_validate_validateurs(
            entities=entities,
            current_list=current_validateurs,
            dispatcher=dispatcher
        )
        
        # Mapper les entités vers des variables
        extracted_data = {}
        for entity in entities:
            entity_name = entity.get('entity')
            entity_value = entity.get('value')
            
            if entity_name in ['id_demande', 'type_demande', 'nom_flux']:
                extracted_data[entity_name] = entity_value
        
        # Extraction spéciale pour responsable_rh
        responsable_rh_extracted = self.extract_responsable_rh(user_message, entities)
        if responsable_rh_extracted:
            extracted_data['responsable_rh'] = responsable_rh_extracted
        
        # ⭐ CORRECTION PRINCIPALE : Récupérer d'abord depuis le tracker (slots persistants)
        # puis depuis extracted_data (nouvelles entités du message actuel)
        id_demande = tracker.get_slot("id_demande") or extracted_data.get('id_demande')
        type_demande = tracker.get_slot("type_demande") or extracted_data.get('type_demande')
        nom_flux = tracker.get_slot("nom_flux") or extracted_data.get('nom_flux')
        nom_flux_id = tracker.get_slot("nom_flux_id")
        responsable_rh = tracker.get_slot("responsable_rh") or extracted_data.get('responsable_rh')
        
        logger.info(f"Valeurs finales - ID: {id_demande}, Type: {type_demande}, Flux: {nom_flux}, Flux ID: {nom_flux_id}, RH: {responsable_rh}")
        logger.info(f"Validateurs: {validateurs_mis_a_jour}")
        
        # ========== VALIDATION ID DEMANDE ==========
        id_demande_valide = False
        
        if id_demande is not None and id_demande != "":
            try:
                demande_id_int = int(id_demande)
                searcher = DemandeSearchService()
                demande_result = searcher.search_with_details(demande_id_int)
                logger.info(f"Résultat recherche demande {demande_id_int}: {demande_result}")
                
                if demande_result:
                    statut_id = demande_result.get('StatutId')
                    
                    if statut_id == 1:
                        id_demande_valide = True
                        logger.info(f"Demande {id_demande} valide (statut 1)")
                    elif statut_id is None:
                        dispatcher.utter_message(
                            text=f"❌ La demande avec l'ID {id_demande} n'existe pas dans le système. "
                                 f"Veuillez vérifier le numéro de demande et réessayer."
                        )
                        id_demande = None
                    else:
                        dispatcher.utter_message(
                            text=f"⚠️ La demande avec l'ID {id_demande} existe mais est déjà en cours de traitement "
                                 f"(Statut: {statut_id}). Veuillez fournir un autre numéro de demande."
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
        
        # ========== VALIDATION NOM FLUX ==========
        nom_flux_valide = False
        flux_trouve = None
        
        # ⭐ Si le flux a déjà été trouvé via les validateurs (ID présent), le marquer comme valide
        if nom_flux_id is not None and nom_flux is not None:
            nom_flux_valide = True
            logger.info(f"✅ Flux déjà validé via validateurs: {nom_flux} (ID: {nom_flux_id})")
        
        # Sinon, valider le flux manuellement si fourni dans le message actuel
        elif extracted_data.get('nom_flux') is not None and extracted_data.get('nom_flux') != "":
            nom_flux_a_valider = extracted_data.get('nom_flux')
            try:
                flux_service = FluxSearchService(default_threshold=60, default_limit=3)
                result = flux_service.search_by_name(nom_flux_a_valider, typeflux="AUTRE")
                
                if result is None:
                    dispatcher.utter_message(
                        text=f"❌ Aucun flux trouvé correspondant à '{nom_flux_a_valider}'. "
                             f"Veuillez vérifier le nom du flux et réessayer."
                    )
                    nom_flux = None
                    nom_flux_id = None
                    
                elif isinstance(result, dict):
                    flux_trouve = result
                    nom_flux_original = result.get('NomFluxMouvement')
                    flux_id = result.get('IdFlux')
                    
                    message = f"✅ Flux trouvé : **{nom_flux_original}**\n\n"
                    message += "📋 **Validateurs du flux :**\n"
                    
                    for i in range(1, 6):
                        username = result.get(f'V{i}')
                        full_name = result.get(f'V{i}UserName')
                        if username and username != 'None':
                            message += f"   • **V{i}** : {full_name} ({username})\n"
                    
                    dispatcher.utter_message(text=message)
                    nom_flux = nom_flux_original
                    nom_flux_id = flux_id
                    nom_flux_valide = True
                    logger.info(f"Flux validé: {nom_flux_original} (ID: {flux_id})")
                    
                elif isinstance(result, list):
                    top_results = result[:3]
                    message = f"🔍 Plusieurs flux correspondent à '{nom_flux_a_valider}'. Voici les 3 plus probables :\n\n"
                    messages_list = []

                    for idx, match in enumerate(top_results, 1):
                        flux = match['flux']
                        flux_name = flux.get('NomFluxMouvement')
                        flux_message = f"{flux_name} :\nValidateurs :\n"

                        for i in range(1, 6):
                            username = flux.get(f'V{i}')
                            full_name = flux.get(f'V{i}UserName')
                            if username and username != 'None':
                                flux_message += f"V{i}: {full_name}\n"

                        messages_list.append(flux_message)

                    escaped_messages = [m.replace('"', '\\"') for m in messages_list]
                    message = '[ ' + ' , "'.join(escaped_messages) + '" ](Liste_nom_flux)'
                    message += "💡 Veuillez préciser le nom exact du flux que vous souhaitez utiliser."
                    
                    dispatcher.utter_message(text=message)
                    nom_flux = None
                    nom_flux_id = None
                    
            except Exception as e:
                dispatcher.utter_message(
                    text=f"❌ Erreur lors de la recherche du flux '{nom_flux_a_valider}': {str(e)}"
                )
                logger.error(f"Erreur FluxSearchService: {e}")
                import traceback
                traceback.print_exc()
                nom_flux = None
                nom_flux_id = None
        
        # ========== VALIDATION RESPONSABLE RH ==========
        responsable_rh_valide = False
        user_rh_trouve = None
        
        if responsable_rh is not None and responsable_rh != "":
            try:
                user_service = UserSearchService()
                results = user_service.search_user_by_name(responsable_rh, max_results=5)
                
                if not results:
                    dispatcher.utter_message(
                        text=f"❌ Aucun utilisateur trouvé correspondant à '{responsable_rh}'. "
                             f"Veuillez vérifier le nom du responsable RH et réessayer."
                    )
                    responsable_rh = None
                    
                elif len(results) == 1:
                    user_rh_trouve = results[0]
                    full_name = user_rh_trouve.get('FullName')
                    matricule = user_rh_trouve.get('Matricule')
                    
                    message = f"✅ Responsable RH trouvé : **{full_name}**\n\n"
                    dispatcher.utter_message(text=message)
                    
                    responsable_rh = full_name
                    responsable_rh_valide = True
                    logger.info(f"Responsable RH validé: {full_name} (Matricule: {matricule})")
                    
                else:
                    top_results = results[:5]
                    message = f"🔍 Plusieurs utilisateurs correspondent à '{responsable_rh}'. Voici les 5 plus probables :\n\n"
                    messages_list = []

                    for idx, user in enumerate(top_results, 1):
                        full_name = user.get('FullName')
                        matricule = user.get('Matricule')
                        user_message = f"{idx}. {full_name}\n"
                        messages_list.append(user_message)

                    escaped_messages = [m.replace('"', '\\"') for m in messages_list]
                    message = '[ "' + '" , "'.join(escaped_messages) + '" ](Liste_RH_possible)'
                    message += "💡 Veuillez préciser le nom exact du responsable RH que vous souhaitez assigner."
                    
                    dispatcher.utter_message(text=message)
                    responsable_rh = None
                    
            except Exception as e:
                dispatcher.utter_message(
                    text=f"❌ Erreur lors de la recherche du responsable RH '{responsable_rh}': {str(e)}"
                )
                logger.error(f"Erreur UserSearchService: {e}")
                import traceback
                traceback.print_exc()
                responsable_rh = None
        
        # ========== DÉFINIR LES SLOTS REQUIS ==========
        required_slots = {
            "type_demande": type_demande,
            "id_demande": id_demande,
            "nom_flux": nom_flux,
            "responsable_rh": responsable_rh
        }
        
        slot_labels = {
            "type_demande": "le type de demande",
            "id_demande": "l'ID de la demande",
            "nom_flux": "le nom du flux",
            "responsable_rh": "le responsable RH"
        }
        
        missing_slots = []
        slots_to_set = list(validateur_slots)  # Commencer avec les slots des validateurs
        
        # Vérifier les slots manquants et mettre à jour ceux qui sont valides
        for slot_name, slot_value in required_slots.items():
            if slot_value is None or slot_value == "":
                missing_slots.append(slot_labels.get(slot_name, slot_name))
            else:
                slots_to_set.append(SlotSet(slot_name, slot_value))
                logger.info(f"✅ Slot {slot_name} défini à: {slot_value}")
        
        # S'assurer que nom_flux_id est toujours défini si disponible
        if nom_flux_id is not None:
            slots_to_set.append(SlotSet("nom_flux_id", nom_flux_id))
            logger.info(f"✅ ID flux (nom_flux_id) enregistré: {nom_flux_id}")
        
        # Si tous les slots sont remplis
        if not missing_slots:
            # Afficher le récapitulatif avec les validateurs
            recap_message = "✅ Toutes les informations nécessaires ont été collectées."
            
            if validateurs_mis_a_jour:
                recap_message += f"\n\n👥 **Validateurs ajoutés ({len(validateurs_mis_a_jour)})** :\n"
                for idx, val in enumerate(validateurs_mis_a_jour, 1):
                    recap_message += f"   {idx}. {val}\n"
            
            dispatcher.utter_message(text=recap_message)
            logger.info("Tous les slots sont remplis, flux prêt à être lancé")
            return slots_to_set + [SlotSet("verify_flux", True), FollowupAction("action_demander_confirmation_flux")]
        
        # Si des informations manquent
        else:
            if len(missing_slots) == 1:
                message = f"Il manque l'information suivante : **{missing_slots[0]}**."
            else:
                missing_str = ", ".join(missing_slots[:-1]) + f" et **{missing_slots[-1]}**"
                message = f"Il manque les informations suivantes : {missing_str}."
            
            if "le type de demande" in missing_slots:
                message += "\n\n📋 Voici la liste de demande possible, veuillez en sélectionner une: [DDR, DMI, DRI, DMOE](demande_type_demande)"
            elif "l'ID de la demande" in missing_slots:
                if type_demande is not None:
                    message += f"\n\n🔢 Veuillez fournir le numéro de la {type_demande} associée au flux."
                else:
                    message += "\n\n🔢 Veuillez fournir le numéro de la demande associée au flux."
            elif "le nom du flux" in missing_slots:
                message += "\n\n🔄 Veuillez indiquer le nom du flux de validation souhaité."
            elif "le responsable RH" in missing_slots:
                message += "\n\n👤 Veuillez fournir le nom complet du responsable RH (ex: ANDRIANINA Manda Arolala)."
            
            message += "\n\n💡 Vous pouvez aussi donner toutes les informations d'un coup. 😉"
            
            dispatcher.utter_message(text=message)
            logger.info(f"Slots manquants: {missing_slots}")
            return slots_to_set + [SlotSet("verify_flux", False)]
        
class ActionDemanderConfirmationFlux(Action):
    def name(self) -> Text:
        return "action_demander_confirmation_flux"

    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Demander confirmation avant de soumettre le flux"""
        
        id_demande = tracker.get_slot("id_demande")
        nom_flux = tracker.get_slot("nom_flux")
        responsable_rh = tracker.get_slot("responsable_rh")
        validateurs = tracker.get_slot("nom_validateur_list") or []
        
        message = f"""
📋 **Récapitulatif du flux de recrutement**

🆔 **Demande** : DDR #{id_demande}
🔄 **Flux** : {nom_flux}
👤 **Responsable RH** : {responsable_rh}
"""
        
        if validateurs and len(validateurs) > 0:
            validateurs_liste = "\n".join([f"   • {v}" for v in validateurs])
            message += f"\n✅ **Validateurs supplémentaires** :\n{validateurs_liste}\n"
        
        message += "\n❓ **Voulez-vous lancer ce flux ?** [Oui,Non](confirmation)"
        
        dispatcher.utter_message(text=message)
        
        return []


class ActionSoumettreFluxRecrutement(Action):
    def name(self) -> Text:
        return "action_soumettre_flux_recrutement"

    @deduplicate_messages
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Soumettre le flux de recrutement en appelant l'API create_flux"""
        
        try:
            id_demande = tracker.get_slot("id_demande")
            nom_flux_id = tracker.get_slot("nom_flux_id")
            nom_flux = tracker.get_slot("nom_flux")
            responsable_rh = tracker.get_slot("responsable_rh")
            type_demande = tracker.get_slot("type_demande")
            validateurs = tracker.get_slot("nom_validateur_list") or []
            
            if not all([id_demande, nom_flux_id, responsable_rh]):
                dispatcher.utter_message(
                    text="❌ Impossible de soumettre le flux : des informations essentielles sont manquantes."
                )
                logger.error(f"Données manquantes - ID: {id_demande}, Flux ID: {nom_flux_id}, RH: {responsable_rh}")
                return []
            
            demande_id_int = int(id_demande)
            flux_id_int = int(nom_flux_id)
            
            backend_service = BackendService()
            searcher = DemandeSearchService()
            demande_data = searcher.search_with_details(demande_id_int)
            
            logger.info(f"Envoi flux - Demande: {demande_id_int}, Flux: {flux_id_int}, RH: {responsable_rh}, Validateurs: {validateurs}")
            result = backend_service.send_demande_to_validateur(
                demande_id=demande_id_int,
                nom_flux_id=flux_id_int,
                responsable_rh=responsable_rh,
                demande_data=demande_data,
            )
            
            success_message = f"""✅ **Flux de recrutement {type_demande} lancé avec succès !**

🆔 Demande #{id_demande} ({type_demande})
🔄 Flux : {nom_flux}
👤 Responsable RH : {responsable_rh}
"""
            
            success_message += "\n📬 Le flux a été transmis aux validateurs."
            
            dispatcher.utter_message(text=success_message)
            logger.info(f"Flux soumis avec succès pour la demande {id_demande}")
            
            return [
                SlotSet("id_demande", None),
                SlotSet("nom_flux_id", None),
                SlotSet("nom_flux", None),
                SlotSet("responsable_rh", None),
                SlotSet("type_demande", None),
                SlotSet("verify_flux", None),
                SlotSet("nom_validateur_list", None)
            ]
                
        except ValueError as ve:
            dispatcher.utter_message(
                text=f"❌ Erreur de validation : {str(ve)}\n\n"
                     f"Veuillez vérifier les informations saisies."
            )
            logger.error(f"Erreur de validation: {ve}")
            return []
            
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ Une erreur inattendue s'est produite lors de la soumission du flux.\n\n"
                     f"Erreur : {str(e)}\n\n"
                     f"Veuillez réessayer ou contacter le support technique."
            )
            logger.error(f"Erreur lors de la soumission du flux: {e}")
            import traceback
            traceback.print_exc()
            return []