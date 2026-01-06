from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import logging

# Importer les services nécessaires
from actions.services.Calculate.DDR_calcul import DemandeSearchService
from actions.services.ddr_service import get_backend_service

logger = logging.getLogger(__name__)


class ActionAfficherStatutDemande(Action):
    """
    Action pour afficher le statut détaillé d'une demande spécifique
    Gère uniquement les DDR
    """
    
    def name(self) -> Text:
        return "action_afficher_statut_demande"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ========== 1. RÉCUPÉRATION DES INFORMATIONS ==========
        
        # Récupérer l'ID de la demande depuis les entités ou le slot
        entities = tracker.latest_message.get('entities', [])
        id_demande = None
        
        for entity in entities:
            if entity.get('entity') == 'id_demande':
                id_demande = entity.get('value')
                break
        
        # Si pas dans les entités, vérifier le slot
        if not id_demande:
            id_demande = tracker.get_slot("id_demande")
        
        # Vérifier le type de demande depuis le slot uniquement
        type_demande_slot = tracker.get_slot("type_demande")
        
        logger.info(f"Recherche statut demande - ID: {id_demande}, Type slot: {type_demande_slot}")
        
        # Si le type n'est pas DDR, informer que seules les DDR sont disponibles
        if type_demande_slot and type_demande_slot.upper() != "DDR":
            dispatcher.utter_message(
                text=f"ℹ️ **Type de demande non disponible**\n\n"
                     f"La consultation des demandes de type **{type_demande_slot.upper()}** n'est pas encore disponible.\n\n"
                     f"Seules les **DDR** (Demandes de Recrutement) sont actuellement prises en charge.\n\n"
                     f"💡 Pour voir une DDR : \"Affiche le statut de la demande [numéro]\""
            )
            logger.info(f"Type de demande {type_demande_slot} non supporté")
            return []
        
        # ========== 2. VALIDATION DE L'ID ==========
        
        if not id_demande:
            dispatcher.utter_message(
                text="⚠️ **ID de demande manquant**\n\n"
                     "Veuillez indiquer le numéro de la demande que vous souhaitez consulter.\n\n"
                     "Exemple : \"Quel est le statut de la demande 1234 ?\""
            )
            logger.warning("ID de demande non fourni")
            return []
        
        try:
            demande_id_int = int(id_demande)
        except ValueError:
            dispatcher.utter_message(
                text=f"⚠️ **ID invalide**\n\n"
                     f"L'ID '{id_demande}' n'est pas un numéro valide.\n\n"
                     f"Veuillez fournir un numéro de demande valide."
            )
            logger.error(f"ID de demande invalide: {id_demande}")
            return []
        
        # ========== 3. RECHERCHE DE LA DEMANDE DDR ==========
        
        try:
            backend = get_backend_service()
            
            # Rechercher uniquement les DDR
            logger.info(f"Recherche DDR ID {demande_id_int}")
            searcher = DemandeSearchService()
            demande_data = searcher.search_with_details(demande_id_int)
            
            # ========== 4. VÉRIFICATION DE L'EXISTENCE ==========
            
            if not demande_data:
                dispatcher.utter_message(
                    text=f"❌ **Demande introuvable**\n\n"
                         f"Aucune demande DDR trouvée avec l'ID **#{demande_id_int}**.\n\n"
                         f"**Vérifications possibles :**\n"
                         f"• Le numéro est-il correct ?\n"
                         f"• Avez-vous les droits pour consulter cette demande ?\n\n"
                         f"💡 Pour voir vos demandes : \"Affiche mes demandes\""
                )
                logger.warning(f"Demande DDR {demande_id_int} introuvable")
                return [SlotSet("id_demande", None)]
            
            # ========== 5. RÉCUPÉRATION DES DÉTAILS ==========
            
            # Informations communes
            statut_id = demande_data.get('StatutId')
            demandeur = demande_data.get('Demandeur')
            responsable_rh = demande_data.get('ResponsableRh')
            
            # Mapping des statuts
            statut_labels = {
                1: "📝 Brouillon",
                2: "⏳ En cours de validation",
                3: "✅ Validée",
                4: "❌ Rejetée",
                5: "🔄 En attente de complément",
                6: "✅ Approuvée par RH",
                7: "📋 En traitement RH"
            }
            
            statut_label = statut_labels.get(statut_id, f"Statut {statut_id}")
            
            # ========== 6. CONSTRUCTION DU MESSAGE POUR DDR ==========
            
            poste_id = demande_data.get('PosteId')
            direction_id = demande_data.get('DirectionId')
            effectif = demande_data.get('Effectif', 'N/A')
            nature_contrat = demande_data.get('NatureContrat', 'N/A')
            duree = demande_data.get('Duree')
            encadreur = demande_data.get('Encadreur', 'N/A')
            poste_encadreur = demande_data.get('PosteEncadreur', 'N/A')
            date_mise_service_raw = demande_data.get('DateMiseEnService', 'N/A')
            date_mise_service = str(date_mise_service_raw) if date_mise_service_raw and date_mise_service_raw != 'N/A' else 'N/A'
            justification = demande_data.get('Justification', 'N/A')
            
            # Récupérer les noms depuis les IDs
            poste_nom = "N/A"
            if poste_id:
                poste = backend.get_poste_by_id(poste_id)
                if poste:
                    poste_nom = poste.get('NomPoste', 'N/A')
            
            direction_nom = "N/A"
            if direction_id:
                directions = backend.get_directions()
                direction = next((d for d in directions if d.get('IdDir') == direction_id), None)
                if direction:
                    direction_nom = direction.get('NomDirection', 'N/A')
            
            # Objectifs - supporter plusieurs formats de données
            objectifs_raw = demande_data.get('objectifs') or demande_data.get('MpObjectifDemandes', [])
            objectifs_text = ""
            
            # Normaliser en liste
            if isinstance(objectifs_raw, dict):
                objectifs = [objectifs_raw]
            elif isinstance(objectifs_raw, list):
                objectifs = objectifs_raw
            else:
                objectifs = []
            
            if objectifs and len(objectifs) > 0:
                objectifs_text = f"\n\n🎯 **Objectifs ({len(objectifs)}) :**\n"
                for idx, obj in enumerate(objectifs, 1):
                    # Vérifier que obj est un dictionnaire
                    if not isinstance(obj, dict):
                        logger.warning(f"Objectif item is not a dict: {type(obj)} - {obj}")
                        continue
                    objectif = obj.get('Objectif', 'N/A')
                    poids = obj.get('Poids', 0)
                    objectifs_text += f"{idx}. {objectif} ({poids}%)\n"
            
            # Dotations - supporter plusieurs formats
            dotations_raw = demande_data.get('dotations') or demande_data.get('liaisons_dotation') or demande_data.get('MpLiaisonDdrdotations', [])
            dotations_text = ""
            
            # Normaliser en liste
            if isinstance(dotations_raw, dict):
                dotations = [dotations_raw]
            elif isinstance(dotations_raw, list):
                dotations = dotations_raw
            else:
                dotations = []
            
            if dotations and len(dotations) > 0:
                dotations_text = f"\n💼 **Dotations ({len(dotations)}) :**\n"
                for dotation in dotations[:3]:  # Limiter à 3
                    # Vérifier que dotation est un dictionnaire
                    if not isinstance(dotation, dict):
                        logger.warning(f"Dotation item is not a dict: {type(dotation)} - {dotation}")
                        continue
                    # Supporter DotationOption ou NomDotation
                    nom = dotation.get('NomDotation') or dotation.get('DotationOption', 'N/A')
                    dotations_text += f"• {nom}\n"
                if len(dotations) > 3:
                    dotations_text += f"• ... et {len(dotations) - 3} autre(s)\n"
            
            # Flux de validation - Gérer à la fois dict unique et liste
            flux_taches_raw = demande_data.get('flux_taches') or demande_data.get('MpFluxTaches', [])
            flux_text = ""
            
            # Normaliser en liste
            if isinstance(flux_taches_raw, dict):
                flux_taches = [flux_taches_raw]
            elif isinstance(flux_taches_raw, list):
                flux_taches = flux_taches_raw
            else:
                flux_taches = []
            
            if flux_taches and len(flux_taches) > 0:
                flux_text = f"\n\n📋 **Flux de validation :**\n"
                for flux in flux_taches:
                    # Vérifier que flux est bien un dictionnaire
                    if not isinstance(flux, dict):
                        logger.warning(f"Flux item is not a dict: {type(flux)} - {flux}")
                        continue
                    
                    # Gérer les différents noms de champs
                    validateur = flux.get('Validateur') or flux.get('NomValidateur', 'N/A')
                    etat = flux.get('EtatValidation') or flux.get('Validation')
                    date_val_raw = flux.get('DateValidation', '')
                    date_val = str(date_val_raw) if date_val_raw else ''
                    
                    # Si pas de validateur, vérifier si la tâche est active
                    if not validateur or validateur == 'N/A':
                        etat_tache = flux.get('Etat')
                        if not etat_tache:
                            continue  # Tâche non activée, on l'ignore
                    
                    if etat == 1 or etat is True:
                        etat_icon = "✅"
                        etat_label = "Validé"
                    elif etat == 0 or etat is False:
                        etat_icon = "❌"
                        etat_label = "Rejeté"
                    else:
                        etat_icon = "⏳"
                        etat_label = "En attente"
                    
                    flux_text += f"{etat_icon} {validateur} - {etat_label}"
                    if date_val:
                        try:
                            flux_text += f" ({date_val[:10]})"
                        except:
                            flux_text += f" ({date_val})"
                    flux_text += "\n"
            
            # Message final
            message = f"""📋 **Demande de Recrutement (DDR) #{demande_id_int}**

━━━━━━━━━━━━━━━━━━━━━━━━
📊 **Statut actuel**
{statut_label}

━━━━━━━━━━━━━━━━━━━━━━━━
👤 **Informations générales**
- Demandeur : {demandeur}
- Responsable RH : {responsable_rh or 'Non assigné'}

━━━━━━━━━━━━━━━━━━━━━━━━
💼 **Détails du poste**
- Poste : {poste_nom}
- Direction : {direction_nom}
- Effectif : {effectif}
- Contrat : {nature_contrat}{f' ({duree} mois)' if duree else ''}
- Encadreur : {encadreur} ({poste_encadreur})
- Mise en service : {date_mise_service[:10] if date_mise_service != 'N/A' else 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━━━
📄 **Justification**
{justification[:200]}{'...' if len(justification) > 200 else ''}
{objectifs_text}
{dotations_text}
{flux_text}
━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            dispatcher.utter_message(text=message)
            logger.info(f"Statut DDR {demande_id_int} affiché avec succès")
            
            # ========== 7. RETOUR ==========
            
            return [
                SlotSet("id_demande", demande_id_int),
                SlotSet("type_demande", "DDR")
            ]
        
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ **Erreur lors de la consultation**\n\n"
                     f"Une erreur s'est produite lors de la récupération des informations de la demande.\n\n"
                     f"Erreur : {str(e)}\n\n"
                     f"Veuillez réessayer ou contacter le support technique."
            )
            logger.error(f"Erreur lors de l'affichage du statut de la demande {id_demande}: {e}")
            import traceback
            traceback.print_exc()
            return []


class ActionAfficherListeDemandes(Action):
    """
    Action pour afficher la liste des demandes de l'utilisateur
    Affiche uniquement les DDR
    """
    
    def name(self) -> Text:
        return "action_afficher_liste_demandes"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ========== 1. RÉCUPÉRATION DU USERNAME ==========
        
        username = tracker.get_slot("username")
        if not username:
            username = tracker.sender_id
        
        logger.info(f"Affichage liste demandes pour l'utilisateur: {username}")
        
        # Vérifier le type de demande depuis le slot uniquement
        type_demande_slot = tracker.get_slot("type_demande")
        
        # Si le type n'est pas DDR, informer que seules les DDR sont disponibles
        if type_demande_slot and type_demande_slot.upper() != "DDR":
            dispatcher.utter_message(
                text=f"ℹ️ **Type de demande non disponible**\n\n"
                     f"La consultation des demandes de type **{type_demande_slot.upper()}** n'est pas encore disponible.\n\n"
                     f"Seules les **DDR** (Demandes de Recrutement) sont actuellement prises en charge.\n\n"
                     f"💡 Pour voir vos DDR : \"Affiche mes demandes\""
            )
            logger.info(f"Type de demande {type_demande_slot} non supporté pour la liste")
            return []
        
        # ========== 2. RÉCUPÉRATION DES DEMANDES DDR ==========
        
        try:
            backend = get_backend_service()
            
            # Récupérer uniquement les DDR
            demandes_ddr = backend.get_demandes_by_username(username) or []
            logger.info(f"DDR récupérées: {len(demandes_ddr)}")
            
            total_demandes = len(demandes_ddr)
            
            # ========== 3. VÉRIFICATION S'IL Y A DES DEMANDES ==========
            
            if total_demandes == 0:
                message = "📋 **Aucune demande trouvée**\n\n"
                message += "Vous n'avez aucune demande DDR en cours.\n\n"
                message += "💡 Pour créer une nouvelle demande :\n"
                message += "\"Je veux créer une demande de recrutement\""
                
                dispatcher.utter_message(text=message)
                logger.info(f"Aucune demande DDR trouvée pour {username}")
                return []
            
            # ========== 4. CONSTRUCTION DU MESSAGE ==========
            
            # Mapping des statuts
            statut_labels = {
                1: "📝 Brouillon",
                2: "⏳ En validation",
                3: "✅ Validée",
                4: "❌ Rejetée",
                5: "🔄 Complément requis",
                6: "✅ Approuvée RH",
                7: "📋 En traitement RH"
            }
            
            message = f"📋 **Mes Demandes de Recrutement ({total_demandes})**\n\n"
            message += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # ========== 5. AFFICHAGE DES DDR ==========
            
            # Limiter à 10 demandes
            for demande in demandes_ddr[:10]:
                id_ddr = demande.get('IdDdr')
                statut_id = demande.get('StatutId')
                statut = statut_labels.get(statut_id, f"Statut {statut_id}")
                
                # Récupérer le nom du poste
                poste_id = demande.get('PosteId')
                poste_nom = "N/A"
                if poste_id:
                    poste = backend.get_poste_by_id(poste_id)
                    if poste:
                        poste_nom = poste.get('NomPoste', 'N/A')
                
                effectif = demande.get('Effectif', 'N/A')
                nature_contrat = demande.get('NatureContrat', 'N/A')
                
                message += f"**#{id_ddr}** - {statut}\n"
                message += f"   • Poste : {poste_nom}\n"
                message += f"   • Effectif : {effectif} | Contrat : {nature_contrat}\n\n"
            
            if len(demandes_ddr) > 10:
                message += f"*... et {len(demandes_ddr) - 10} autre(s) DDR*\n\n"
            
            message += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            message += "💡 Pour plus de détails : \"Affiche le statut de la demande [numéro]\""
            
            dispatcher.utter_message(text=message)
            logger.info(f"{total_demandes} demande(s) DDR affichée(s) pour {username}")
            
            return []
        
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ **Erreur lors de la récupération**\n\n"
                     f"Une erreur s'est produite lors de la récupération de vos demandes.\n\n"
                     f"Erreur : {str(e)}\n\n"
                     f"Veuillez réessayer ou contacter le support technique."
            )
            logger.error(f"Erreur lors de l'affichage de la liste des demandes pour {username}: {e}")
            import traceback
            traceback.print_exc()
            return []


class ActionAfficherDemandesATraiter(Action):
    """
    Action pour afficher les demandes en attente de validation par l'utilisateur
    Utilise get_demandes_for_validateur pour récupérer les demandes à traiter
    Affiche uniquement les DDR
    """
    
    def name(self) -> Text:
        return "action_afficher_demandes_a_traiter"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ========== 1. RÉCUPÉRATION DU USERNAME ==========
        
        username = tracker.get_slot("username")
        if not username:
            username = tracker.sender_id
        
        logger.info(f"Affichage demandes à traiter pour: {username}")
        
        # Vérifier le type de demande depuis le slot uniquement
        type_demande_slot = tracker.get_slot("type_demande")
        
        # Si le type n'est pas DDR, informer que seules les DDR sont disponibles
        if type_demande_slot and type_demande_slot.upper() != "DDR":
            dispatcher.utter_message(
                text=f"ℹ️ **Type de demande non disponible**\n\n"
                     f"La consultation des demandes de type **{type_demande_slot.upper()}** à traiter n'est pas encore disponible.\n\n"
                     f"Seules les **DDR** (Demandes de Recrutement) sont actuellement prises en charge.\n\n"
                     f"💡 Pour voir vos DDR à traiter : \"Lister mes demandes à traiter\""
            )
            logger.info(f"Type de demande {type_demande_slot} non supporté pour les demandes à traiter")
            return []
        
        # ========== 2. RÉCUPÉRATION DES DEMANDES À TRAITER ==========
        
        try:
            backend = get_backend_service()
            
            # Récupérer les demandes en attente de validation par l'utilisateur
            demandes_raw = backend.get_demandes_for_validateur(username) or []
            
            # Vérifier et normaliser la structure des données
            if isinstance(demandes_raw, str):
                logger.warning(f"demandes_raw est une chaîne: {demandes_raw[:100]}")
                demandes_a_traiter = []
            elif isinstance(demandes_raw, dict):
                demandes_a_traiter = [demandes_raw]
            elif isinstance(demandes_raw, list):
                # Filtrer les éléments qui ne sont pas des dictionnaires
                demandes_a_traiter = [d for d in demandes_raw if isinstance(d, dict)]
                if len(demandes_a_traiter) != len(demandes_raw):
                    logger.warning(f"Certains éléments de demandes_raw ne sont pas des dictionnaires. Filtré de {len(demandes_raw)} à {len(demandes_a_traiter)}")
            else:
                logger.warning(f"Type inattendu pour demandes_raw: {type(demandes_raw)}")
                demandes_a_traiter = []
            
            # Filtrer uniquement les DDR (celles qui ont un IdDdr)
            demandes_a_traiter = [d for d in demandes_a_traiter if 'IdDdr' in d]
            
            logger.info(f"Demandes DDR à traiter: {len(demandes_a_traiter)}")
            
            total_a_traiter = len(demandes_a_traiter)
            
            # ========== 3. VÉRIFICATION S'IL Y A DES DEMANDES À TRAITER ==========
            
            if total_a_traiter == 0:
                message = "✅ **Aucune demande en attente**\n\n"
                message += "Vous n'avez aucune demande DDR en attente de validation.\n\n"
                message += "🎉 Votre file de validation est vide !"
                
                dispatcher.utter_message(text=message)
                logger.info(f"Aucune demande DDR à traiter pour {username}")
                return []
            
            # ========== 4. CONSTRUCTION DU MESSAGE ==========
            
            # Mapping des statuts
            statut_labels = {
                1: "📝 Brouillon",
                2: "⏳ En validation",
                3: "✅ Validée",
                4: "❌ Rejetée",
                5: "🔄 Complément requis",
                6: "✅ Approuvée RH",
                7: "📋 En traitement RH"
            }
            
            message = f"📬 **Demandes de Recrutement en attente de ma validation ({total_a_traiter})**\n\n"
            message += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # ========== 5. AFFICHAGE DES DEMANDES À TRAITER ==========
            
            # Limiter à 10 demandes
            for demande in demandes_a_traiter[:10]:
                demande_id = demande.get('IdDdr')
                statut_id = demande.get('StatutId')
                statut = statut_labels.get(statut_id, f"Statut {statut_id}")
                
                demandeur = demande.get('Demandeur', 'N/A')
                
                # Récupérer les informations du poste
                poste_id = demande.get('PosteId')
                poste_nom = "N/A"
                if poste_id:
                    poste = backend.get_poste_by_id(poste_id)
                    if poste:
                        poste_nom = poste.get('NomPoste', 'N/A')
                
                effectif = demande.get('Effectif', 'N/A')
                nature_contrat = demande.get('NatureContrat', 'N/A')
                
                message += f"**📝 DDR #{demande_id}** - {statut}\n"
                message += f"   • Demandeur : {demandeur}\n"
                message += f"   • Poste : {poste_nom}\n"
                message += f"   • Effectif : {effectif} | Contrat : {nature_contrat}\n\n"
            
            if len(demandes_a_traiter) > 10:
                message += f"*... et {len(demandes_a_traiter) - 10} autre(s) demande(s)*\n\n"
            
            # ========== 6. FOOTER ==========
            
            message += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            message += "💡 Pour consulter une demande : \"Affiche le statut de la demande [numéro]\"\n"
            message += "💡 Pour valider : \"Je veux valider la demande [numéro]\""
            
            dispatcher.utter_message(text=message)
            logger.info(f"{total_a_traiter} demande(s) DDR à traiter affichée(s) pour {username}")
            
            return []
        
        except Exception as e:
            dispatcher.utter_message(
                text=f"❌ **Erreur lors de la récupération**\n\n"
                     f"Une erreur s'est produite lors de la récupération des demandes à traiter.\n\n"
                     f"Erreur : {str(e)}\n\n"
                     f"Veuillez réessayer ou contacter le support technique."
            )
            logger.error(f"Erreur lors de l'affichage des demandes à traiter pour {username}: {e}")
            import traceback
            traceback.print_exc()
            return []