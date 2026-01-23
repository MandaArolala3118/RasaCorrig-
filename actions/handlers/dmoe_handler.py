from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, EventType, FollowupAction
from datetime import datetime
import re
import logging
logger = logging.getLogger(__name__)

from actions.services.ddr_service import get_backend_service

class ActionSubmitFormAddDmoe(Action):
    """Action de soumission du formulaire DMOE avec upload des fichiers"""
    
    def name(self) -> Text:
        return "action_submit_form_add_dmoe"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Soumettre le formulaire DMOE et créer la demande via l'API"""
        
        try:
            # ============================================
            # 1. RÉCUPÉRATION DES SLOTS
            # ============================================
            
            nature_contrat = tracker.get_slot("nature_contrat")
            duree_contrat = tracker.get_slot("duree_contrat")
            nom_poste = tracker.get_slot("nom_poste")
            poste_id = tracker.get_slot("poste_id")
            effectif = tracker.get_slot("effectif")
            direction = tracker.get_slot("direction")
            direction_id = tracker.get_slot("direction_id")
            exploitation = tracker.get_slot("exploitation")
            exploitation_id = tracker.get_slot("exploitation_id")
            nom_encadreur = tracker.get_slot("nom_encadreur")
            poste_encadreur = tracker.get_slot("poste_encadreur")
            date_mise_en_service = tracker.get_slot("date_mise_en_service")
            motif = tracker.get_slot("motif")
            motif_id = tracker.get_slot("motif_id")
            situation_budget = tracker.get_slot("situation_budget")
            situation_budget_id = tracker.get_slot("situation_budget_id")
            justification = tracker.get_slot("justification")
            objectifs_list = tracker.get_slot("objectifs_list")
            piece_jointe = tracker.get_slot("piece_jointe")
            choix_heure_tonnage = tracker.get_slot("choix_heure_tonnage")
            
            # Récupérer le username du demandeur
            username = tracker.get_slot("username")
            if not username:
                username = tracker.sender_id
            
            logger.info(f"📋 Soumission DMOE pour l'utilisateur: {username}")
            
            # ============================================
            # 2. VALIDATION FINALE AVEC DÉTAILS
            # ============================================
            
            # Dictionnaire des champs obligatoires avec leurs noms conviviaux
            required_fields = {
                'poste_id': 'Poste',
                'effectif': 'Effectif',
                'nature_contrat': 'Nature du contrat',
                'nom_encadreur': 'Nom de l\'encadreur',
                'date_mise_en_service': 'Date de mise en service',
                'direction_id': 'Direction',
                'exploitation_id': 'Exploitation',
                'motif_id': 'Motif',
                'situation_budget_id': 'Situation budgétaire',
                'justification': 'Justification',
                'objectifs_list': 'Objectifs',
                'piece_jointe': 'Pièce jointe'
            }
            
            # Vérifier quels champs sont manquants
            missing_fields = []
            for field_name, field_label in required_fields.items():
                field_value = locals().get(field_name)
                if not field_value:
                    missing_fields.append(field_label)
            
            # Si des champs sont manquants, afficher le message d'erreur détaillé
            if missing_fields:
                error_msg = "❌ Erreur: Les informations suivantes sont manquantes :\n\n"
                error_msg += "\n".join([f"  • {field}" for field in missing_fields])
                error_msg += "\n\nVeuillez fournir ces informations pour continuer."
                
                dispatcher.utter_message(text=error_msg)
                logger.error(f"❌ Validation échouée - Champs manquants: {', '.join(missing_fields)}")
                return []
            
            # Si validation OK, continuer avec la création de la demande
            
            if nature_contrat.upper() != "CDI" and not duree_contrat:
                error_msg = "❌ Erreur: La durée du contrat est obligatoire pour un CDD."
                dispatcher.utter_message(text=error_msg)
                logger.error("❌ Validation échouée - Durée CDD manquante")
                return []
            
            # ============================================
            # 3. UPLOAD DES FICHIERS
            # ============================================
            
            backend = get_backend_service()
            uploaded_files = []
            
            # Récupérer les métadonnées contenant les fichiers
            session_metadata = tracker.get_slot("session_started_metadata") or {}
            latest_metadata = tracker.latest_message.get("metadata", {})
            all_metadata = {**session_metadata, **latest_metadata}
            attachments = all_metadata.get("attachments", [])
            
            logger.info(f"📎 Traitement de {len(attachments)} fichier(s) à uploader")
            
            if attachments:
                dispatcher.utter_message(text="⏳ Upload des fichiers en cours...")
                
                for i, attachment in enumerate(attachments, 1):
                    filename = attachment.get('name', 'unknown')
                    logger.info(f"📤 Upload {i}/{len(attachments)}: {filename}")
                    
                    uploaded_filename = backend.upload_file_from_metadata(attachment)
                    
                    if uploaded_filename:
                        uploaded_files.append(uploaded_filename)
                        logger.info(f"✅ Fichier {i}/{len(attachments)} uploadé: {uploaded_filename}")
                    else:
                        logger.error(f"❌ Échec upload {i}/{len(attachments)}: {filename}")
                        dispatcher.utter_message(
                            text=f"⚠️ Attention: Le fichier '{filename}' n'a pas pu être uploadé."
                        )
                
                if len(uploaded_files) > 0:
                    dispatcher.utter_message(
                        text=f"✅ {len(uploaded_files)} fichier(s) uploadé(s) avec succès"
                    )
                    logger.info(f"✅ Total fichiers uploadés: {uploaded_files}")
                else:
                    error_msg = (
                        f"❌ **Erreur : Aucun fichier n'a pu être uploadé**\n\n"
                        f"Les {len(attachments)} fichier(s) ont échoué lors de l'upload.\n\n"
                        f"**Causes possibles** :\n"
                        f"• Problème de connexion avec le serveur\n"
                        f"• Format de fichier non supporté\n"
                        f"• Taille de fichier trop importante\n\n"
                        f"Veuillez réessayer ou contacter le support technique."
                    )
                    dispatcher.utter_message(text=error_msg)
                    logger.error(f"❌ Échec upload de tous les fichiers")
                    return []
            else:
                logger.warning("⚠️ Aucun fichier détecté dans les métadonnées")
                
                if piece_jointe and piece_jointe.strip():
                    logger.warning(f"⚠️ Utilisation des noms du slot (fichiers NON uploadés): {piece_jointe}")
                    uploaded_files = [f.strip() for f in piece_jointe.split(',') if f.strip()]
                else:
                    error_msg = "❌ Aucun fichier joint. Veuillez joindre au moins un document."
                    dispatcher.utter_message(text=error_msg)
                    return []
            
            # Joindre les noms de fichiers uploadés pour le payload
            piece_jointe_finale = ','.join(uploaded_files)
            
            # ✅ VALIDATION : Vérifier la longueur totale (limite SQL)
            MAX_LENGTH_PIECE_JOINTE = 255
            
            if len(piece_jointe_finale) > MAX_LENGTH_PIECE_JOINTE:
                error_msg = (
                    f"❌ **Erreur : Noms de fichiers trop longs**\n\n"
                    f"La longueur totale des noms de fichiers ({len(piece_jointe_finale)} caractères) "
                    f"dépasse la limite autorisée ({MAX_LENGTH_PIECE_JOINTE} caractères).\n\n"
                    f"**Solutions** :\n"
                    f"• Renommer vos fichiers avec des noms plus courts\n"
                    f"• Réduire le nombre de fichiers joints\n\n"
                    f"**Fichiers actuels** :\n" + 
                    "\n".join([f"  • {f} ({len(f)} chars)" for f in uploaded_files])
                )
                dispatcher.utter_message(text=error_msg)
                logger.error(f"❌ Longueur PieceJointes trop grande: {len(piece_jointe_finale)} chars")
                return []
            
            # ============================================
            # 4. PRÉPARATION DES OBJECTIFS
            # ============================================
            
            mp_objectif_demandes = []
            
            if objectifs_list:
                for obj in objectifs_list:
                    if isinstance(obj, dict):
                        objectif_dto = {
                            "Objectif": str(obj.get("objectif", "") or obj.get("Objectif", "")),
                            "Poids": int(obj.get("poids", 0) or obj.get("Poids", 0)),
                            "ResultatAttendu": str(obj.get("resultat", "") or obj.get("ResultatAttendu", ""))
                        }
                        mp_objectif_demandes.append(objectif_dto)
                        logger.info(f"✓ Objectif ajouté: {objectif_dto['Objectif']} (Poids: {objectif_dto['Poids']}%)")
                    else:
                        logger.warning(f"⚠️ Objectif ignoré (format invalide): {obj}")
            
            # ============================================
            # 5. FORMATAGE DE LA DATE
            # ============================================
            
            try:
                if isinstance(date_mise_en_service, str):
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            dt = datetime.strptime(date_mise_en_service, fmt)
                            date_formatted = dt.strftime('%Y-%m-%dT00:00:00')
                            break
                        except ValueError:
                            continue
                    else:
                        date_formatted = datetime.now().strftime('%Y-%m-%dT00:00:00')
                        logger.warning(f"⚠️ Format de date invalide, utilisation de la date actuelle")
                else:
                    date_formatted = datetime.now().strftime('%Y-%m-%dT00:00:00')
            except Exception as e:
                logger.error(f"❌ Erreur de formatage de date: {e}")
                date_formatted = datetime.now().strftime('%Y-%m-%dT00:00:00')
            
            logger.info(f"📅 Date formatée: {date_formatted}")
            
            # ============================================
            # 6. CONSTRUCTION DU PAYLOAD DMOE (sans dotations)
            # ============================================
            
            demande_data = {
                "IdDdr": 0,
                "NatureContrat": nature_contrat,
                "Duree": duree_contrat if nature_contrat.upper() != "CDI" else None,
                "Effectif": int(effectif),
                "Encadreur": nom_encadreur,
                "DateMiseEnService": date_formatted,
                "Justification": justification,
                "PieceJointes": piece_jointe_finale,
                "Demandeur": username,
                "ResponsableRh": None,
                "PosteId": int(poste_id),
                "PosteEncadreur": poste_encadreur,
                "DirectionId": int(direction_id),
                "ExploitationId": int(exploitation_id) if exploitation_id else None,
                "SituationBudgetId": int(situation_budget_id),
                "MotifId": int(motif_id),
                "StatutId": 1,
                "Username": username,
                "MpObjectifDemandes": mp_objectif_demandes,
                "MpLiaisonDdrdotations": [],  # DMOE n'a pas de dotations
                "ChoixHeureTonnage": choix_heure_tonnage  # Ajout du choix heure/tonnage
            }
            
            logger.info("📦 Payload DMOE construit:")
            logger.info(f"   - Encadreur: {nom_encadreur}")
            logger.info(f"   - Poste Encadreur: {poste_encadreur}")
            logger.info(f"   - Fichiers uploadés: {piece_jointe_finale}")
            logger.info(f"   - Objectifs: {len(mp_objectif_demandes)}")
            logger.info(f"   - Choix Heure/Tonnage: {choix_heure_tonnage}")
            
            # ============================================
            # 7. APPEL API BACKEND
            # ============================================
            
            dispatcher.utter_message(text="⏳ Création de la demande DMOE en cours...")
            print("------------------------------------------------------------------------------------------------Data envoyé a la base : ", demande_data)
            response = backend.create_demande(demande_data)
            print("------------------------------------------------------------------------------------------------Response de la base : ", response)
            demande_id = 'N/A'

            if response and isinstance(response, dict): 
                # Vérifier d'abord au niveau racine du response
                if 'IdDdr' in response:
                    demande_id = response['IdDdr']
                else:
                    # Sinon vérifier dans le nested 'demande' key (pour compatibilité rétroactive)
                    demande = response.get('demande', {})
                    if isinstance(demande, dict):
                        for key, value in demande.items():
                            if key.lower() == 'idddr':
                                demande_id = value
                                break

                # ============================================
                # 8. MESSAGE DE SUCCÈS
                # ============================================
                
                success_message = f"""✅ **Demande DMOE créée avec succès !**

📋 **Numéro de demande** : #{demande_id}

**Récapitulatif** :
━━━━━━━━━━━━━━━━━━━━
**Informations générales**
- Poste : {nom_poste}
- Nature : {nature_contrat}
{f'• Durée : {duree_contrat} mois' if nature_contrat.upper() != 'CDI' else ''}
- Effectif : {effectif} personne(s)
- Encadreur : {nom_encadreur}{f' ({poste_encadreur})' if poste_encadreur else ''}
- Date de mise en service : {date_mise_en_service}
{f'• Choix Heure/Tonnage : {choix_heure_tonnage}' if choix_heure_tonnage else ''}

**Organisation**
- Direction : {direction}
- Exploitation : {exploitation}
- Situation budgétaire : {situation_budget}

**Motif & Justification**
- Motif : {motif}
- Justification : {justification[:150]}{'...' if len(justification) > 150 else ''}

**Objectifs** ({len(objectifs_list)})
"""
                for i, obj in enumerate(objectifs_list, 1):
                    success_message += f"  {i}. {obj.get('objectif')} ({obj.get('poids')}%)\n"
                
                success_message += f"\n**Fichiers joints** : {len(uploaded_files)} fichier(s)\n"
                if uploaded_files:
                    success_message += "  " + "\n  ".join([f"• {f}" for f in uploaded_files]) + "\n"
                success_message += "\n━━━━━━━━━━━━━━━━━━━━\n"
                success_message += "Votre demande DMOE sera traitée dans les plus brefs délais.\n"
                success_message += "Vous recevrez une notification dès qu'elle sera validée."
                
                dispatcher.utter_message(text=success_message)
                
                logger.info(f"✅ Demande DMOE créée avec succès - ID: {demande_id}")
                logger.info(f"🧹 Nettoyage des métadonnées et fichiers uploadés")
                
                # ============================================
                # 9. RÉINITIALISATION DES SLOTS + NETTOYAGE DES MÉTADONNÉES
                # ============================================
                
                return [
                    SlotSet("id_demande", demande_id),
                    SlotSet("add_ddr_is_complet", False),
                    SlotSet("nature_contrat", None),
                    SlotSet("duree_contrat", None),
                    SlotSet("nom_poste", None),
                    SlotSet("poste_id", None),
                    SlotSet("effectif", None),
                    SlotSet("direction", None),
                    SlotSet("direction_id", None),
                    SlotSet("exploitation", None),
                    SlotSet("exploitation_id", None),
                    SlotSet("nom_encadreur", None),
                    SlotSet("poste_encadreur", None),
                    SlotSet("date_mise_en_service", None),
                    SlotSet("motif", None),
                    SlotSet("motif_id", None),
                    SlotSet("situation_budget", None),
                    SlotSet("situation_budget_id", None),
                    SlotSet("justification", None),
                    SlotSet("objectifs_list", None),
                    SlotSet("piece_jointe", None),
                    SlotSet("choix_heure_tonnage", None),
                    # 🧹 NETTOYAGE DES MÉTADONNÉES CONTENANT LES FICHIERS
                    SlotSet("session_started_metadata", None)
                ]
            
            else:
                # ============================================
                # 10. GESTION DES ERREURS API
                # ============================================
                
                error_message = """❌ **Erreur lors de la création de la demande DMOE**

Une erreur s'est produite lors de la communication avec le serveur.

**Actions possibles** :
- Vérifier que toutes les informations sont correctes
- Réessayer dans quelques instants
- Contacter le support technique si le problème persiste

Voulez-vous réessayer ?"""
                
                dispatcher.utter_message(text=error_message)
                logger.error("❌ Échec de création de la demande DMOE - Réponse API vide")
                
                return []
        
        except Exception as e:
            # ============================================
            # 11. GESTION DES EXCEPTIONS
            # ============================================
            
            error_message = f"""❌ **Erreur inattendue**

Une erreur s'est produite : {str(e)}

Veuillez réessayer ou contacter le support technique."""
            
            dispatcher.utter_message(text=error_message)
            logger.error(f"❌ Exception dans action_submit_form_add_dmoe: {e}", exc_info=True)
            
            return []

class ActionVerifyIfAllInformationIsCompletAddDmoe(Action):
    """Vérifie si toutes les informations DMOE sont complètes et guide l'utilisateur"""
                        
    def name(self) -> Text:
        return "verify_if_all_information_is_complet_add_dmoe"
    
    def __init__(self):
        super().__init__()
        from actions.services.ddr_service import get_backend_service
        self.backend = get_backend_service()
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # ============================================
        # 1. AFFICHAGE DES DONNÉES DÉJÀ ENTRÉES
        # ============================================
        
        donnees_entrees = self._get_donnees_entrees(tracker)
        
        if donnees_entrees:
            message_recap = "📋 **Données déjà enregistrées :**\n\n"
            message_recap += donnees_entrees
            message_recap += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
            dispatcher.utter_message(text=message_recap)
            logger.info("📋 Affichage des données déjà entrées")
        
        # ============================================
        # 2. DÉFINITION DES CHAMPS REQUIS (sauf objectifs et pièce jointe)
        # ============================================
        
        required_fields = {
            "nom_poste": "le nom du poste",
            "nom_encadreur": "le nom de l'encadreur",
            "effectif": "l'effectif",
            "nature_contrat": "la nature du contrat",
            "date_mise_en_service": "la date de mise en service",
            "direction": "la direction",
            "exploitation": "l'exploitation",
            "motif": "le motif",
            "situation_budget": "la situation budgétaire",
            "justification": "la justification",
        }
        
        # Ajouter champ durée pour tous les contrats sauf CDI
        nature_contrat = tracker.get_slot("nature_contrat")
        if nature_contrat and nature_contrat.upper() not in ["CDI"]:
            if nature_contrat.upper() == "CDD":
                required_fields["duree_contrat"] = "la durée du contrat CDD"
            elif nature_contrat.upper() == "STAGE":
                required_fields["duree_contrat"] = "la durée du stage"
            elif nature_contrat.upper() in ["EXTERNALISE", "EXTERNALISÉ"]:
                required_fields["duree_contrat"] = "la durée du contrat externalisé"
            else:
                required_fields["duree_contrat"] = "la durée du contrat"
        
        # ============================================
        # 3. VÉRIFICATION DES CHAMPS STANDARDS (PRIORITÉ 1)
        # ============================================
        
        missing_fields = []
        
        for field, display_name in required_fields.items():
            value = tracker.get_slot(field)
            
            if not value or value == "":
                missing_fields.append({
                    "slot_name": field,
                    "display_name": display_name
                })
                logger.info(f"⚠️ Champ manquant: {field}")
            else:
                logger.info(f"✓ Champ OK: {field} → '{value}'")
        
        # ❌ SI DES CHAMPS STANDARDS MANQUENT → VÉRIFIER AUSSI OBJECTIFS ET PIÈCES JOINTES
        if len(missing_fields) > 0:
            # ✅ VÉRIFICATION DES OBJECTIFS POUR L'AJOUTER À LA LISTE DES MANQUANTS
            objectifs_list = tracker.get_slot("objectifs_list") or []
            
            if not objectifs_list or len(objectifs_list) == 0:
                missing_fields.append({
                    "slot_name": "objectifs",
                    "display_name": "les objectifs (minimum 3)"
                })
                logger.info("⚠️ Champ manquant: objectifs")
            else:
                # Vérifier si les objectifs sont complets
                objectifs_incomplets = self._valider_objectifs(objectifs_list)
                if objectifs_incomplets:
                    missing_fields.append({
                        "slot_name": "objectifs",
                        "display_name": "les objectifs (compléter ou corriger)"
                    })
                    logger.info("⚠️ Objectifs incomplets détectés")
            
            # ✅ VÉRIFICATION DES PIÈCES JOINTES POUR L'AJOUTER À LA LISTE DES MANQUANTS
            piece_jointe = tracker.get_slot("piece_jointe")
            
            if not piece_jointe or str(piece_jointe).strip() == "":
                missing_fields.append({
                    "slot_name": "piece_jointe",
                    "display_name": "les pièces jointes (minimum 1 fichier)"
                })
                logger.info("⚠️ Champ manquant: pièce jointe")
            
            first_missing = missing_fields[0]
            all_missing_names = [f["display_name"] for f in missing_fields]
            
            # ✅ AMÉLIORATION : Afficher les options disponibles pour motif et situation_budget
            message = f"⚠️ **Informations manquantes:**\n\n{', '.join(all_missing_names)}.\n\n"
            
            if first_missing['slot_name'] == 'motif':
                motifs = self.backend.get_motif_demandes() or []
                if motifs:
                    motifs_list = ', '.join([m.get('Motif', '') for m in motifs if m.get('Motif')])
                    message += f"📋 **Motifs disponibles:**\n[{motifs_list}](verification_motif)\n\n"
                message += f"💬 Veuillez indiquer le motif de la demande."
            
            elif first_missing['slot_name'] == 'situation_budget':
                situations = self.backend.get_situation_budgets() or []
                if situations:
                    situations_list = ', '.join([s.get('SituationBudget', '') for s in situations if s.get('SituationBudget')])
                    message += f"📋 **Situations budgétaires disponibles:**\n[{situations_list}](verification_situation_budget)\n\n"
                message += f"💬 Veuillez indiquer la situation budgétaire."
            
            elif first_missing['slot_name'] == 'objectifs':
                message += f"💬 Veuillez fournir vos objectifs (minimum 3, maximum 5)."
            
            elif first_missing['slot_name'] == 'piece_jointe':
                message += f"📎 Veuillez joindre au moins un fichier justificatif.\n"
                message += f"📋 Formats acceptés: PDF, Word, Excel, Images\n"
                message += f"📏 Taille max: 10 MB"
            
            else:
                message += f"Pouvez-vous me donner {first_missing['display_name']} ?"
            message+= "\n\nNB: Vous pouvez donner tous les information ou une partie ou suivre les etapes à la quelle je vous guide."
            dispatcher.utter_message(text=message)
            logger.warning(f"⚠️ {len(missing_fields)} champ(s) standard(s) manquant(s) - Arrêt de la validation")
            
            return [
                SlotSet("add_ddr_is_complet", False),
                FollowupAction("action_listen")
            ]
        
        logger.info("✅ Tous les champs standards sont complets")
        
        # ============================================
        # 4. VÉRIFICATION DES OBJECTIFS (PRIORITÉ 2)
        # ============================================
        
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        logger.info(f"📊 Vérification objectifs: {len(objectifs_list)} enregistré(s)")
        
        # 🔥 VALIDATION COMPLÈTE DES OBJECTIFS
        objectifs_incomplets = self._valider_objectifs(objectifs_list)
        
        if objectifs_incomplets:
            # ❌ Les objectifs ne sont pas complets
            message = self._generer_message_objectifs_incomplets(objectifs_list, objectifs_incomplets)
            dispatcher.utter_message(text=message)
            
            logger.warning(f"⚠️ Objectifs incomplets: {objectifs_incomplets}")
            
            return [
                SlotSet("add_ddr_is_complet", False),
                SlotSet("is_complet_objectifs", False),
                FollowupAction("action_listen")
            ]
        
        # ✅ Objectifs complets
        logger.info("✅ Objectifs validés avec succès")
        
        # ============================================
        # 5. VÉRIFICATION DE LA PIÈCE JOINTE (PRIORITÉ 3)
        # ============================================
        
        piece_jointe = tracker.get_slot("piece_jointe")
        
        if not piece_jointe:
            # Demander la pièce jointe
            dispatcher.utter_message(
                text="✅ Toutes les informations sont complètes!\n\n"
                     "📎 **Il ne manque plus que la pièce jointe**\n\n"
                     "Merci de joindre un document justificatif.\n\n"
                     "📋 Formats acceptés: PDF, Word, Excel, Images\n"
                     "📏 Taille max: 10 MB"
            )
            logger.info("⚠️ Pièce jointe manquante - En attente")
            
            return [
                SlotSet("add_ddr_is_complet", False),
                SlotSet("is_complet_objectifs", True),
                FollowupAction("action_listen")
            ]
        
        # ============================================
        # 6. VÉRIFICATION DU CHOIX HEURE TONNAGE (PRIORITÉ 4 - optionnel)
        # ============================================
        
        choix_heure_tonnage = tracker.get_slot("choix_heure_tonnage")
        
        if not choix_heure_tonnage:
            # Demander le choix heure/tonnage (optionnel)
            dispatcher.utter_message(
                text="✅ Presque terminé!\n\n"
                     "⏰ **Voulez-vous spécifier un choix heure/tonnage ?**\n\n"
                     "Ceci est optionnel. Vous pouvez répondre avec:\n"
                     "• 'heure' pour un suivi par heures\n"
                     "• 'tonnage' pour un suivi par tonnage\n"
                     "• 'non' pour passer cette étape"
            )
            logger.info("ℹ️ Choix heure/tonnage manquant - En attente (optionnel)")
            
            return [
                SlotSet("add_ddr_is_complet", False),
                SlotSet("is_complet_objectifs", True),
                FollowupAction("action_listen")
            ]
        
        # ============================================
        # 7. RÉSULTAT FINAL - TOUT EST COMPLET ✅
        # ============================================
        
        logger.info(f"🔍 Récapitulatif validation DMOE:")
        logger.info(f"   Champs requis: {len(required_fields)} ✅")
        logger.info(f"   Objectifs: ✅ Complets")
        logger.info(f"   Pièce jointe: ✅")
        logger.info(f"   Choix heure/tonnage: ✅ ({choix_heure_tonnage})")
        
        success_message = "✅ Toutes les informations sont complètes!"
        
        dispatcher.utter_message(text=success_message)
        logger.info("✅ Validation complète réussie - DMOE prête")
        
        return [
            SlotSet("add_ddr_is_complet", True),
            SlotSet("is_complet_objectifs", True),
            FollowupAction("action_confirmer_enregistrement_ddr")
        ]
    
    def _get_donnees_entrees(self, tracker: Tracker) -> str:
        """
        Récupère et formate les données déjà entrées par l'utilisateur.
        
        Returns:
            String formaté avec les données ou string vide si aucune donnée
        """
        donnees = []
        
        # Mapping des slots avec leurs labels
        slots_mapping = {
            "nom_poste": ("📌 Poste", None),
            "effectif": ("👥 Effectif", lambda v: f"{v} personne(s)"),
            "nature_contrat": ("📝 Nature du contrat", None),
            "duree_contrat": ("⏱️ Durée", lambda v: f"{v} mois"),
            "date_mise_en_service": ("📅 Date de mise en service", None),
            "nom_encadreur": ("👤 Encadreur", None),
            "direction": ("🏢 Direction", None),
            "exploitation": ("📍 Exploitation", None),
            "motif": ("🎯 Motif", None),
            "situation_budget": ("💰 Situation budgétaire", None),
            "justification": ("📝 Justification", lambda v: f"{v[:100]}{'...' if len(v) > 100 else ''}"),
            "choix_heure_tonnage": ("⏰ Choix heure/tonnage", None)
        }
        
        for slot_name, (label, formatter) in slots_mapping.items():
            value = tracker.get_slot(slot_name)
            if value and str(value).strip():
                if formatter:
                    value = formatter(value)
                donnees.append(f"• {label}: {value}")
        
        # Ajouter les objectifs
        objectifs_list = tracker.get_slot("objectifs_list") or []
        if objectifs_list:
            donnees.append(f"🎯 Objectifs ({len(objectifs_list)}):")
            for i, obj in enumerate(objectifs_list[:3], 1):  # Limiter à 3 pour l'affichage
                if isinstance(obj, dict):
                    objectif_text = obj.get('objectif', obj.get('Objectif', ''))
                    poids = obj.get('poids', obj.get('Poids', 0))
                    donnees.append(f"  {i}. {objectif_text} ({poids}%)")
            if len(objectifs_list) > 3:
                donnees.append(f"  ... et {len(objectifs_list) - 3} autre(s)")
        
        # Ajouter les pièces jointes
        piece_jointe = tracker.get_slot("piece_jointe")
        if piece_jointe and str(piece_jointe).strip():
            fichiers = [f.strip() for f in str(piece_jointe).split(',') if f.strip()]
            donnees.append(f"📎 Pièces jointes ({len(fichiers)}):")
            for fichier in fichiers[:3]:  # Limiter à 3 pour l'affichage
                donnees.append(f"  • {fichier}")
            if len(fichiers) > 3:
                donnees.append(f"  ... et {len(fichiers) - 3} autre(s)")
        
        return "\n".join(donnees) if donnees else ""
    
    def _valider_objectifs(self, objectifs_list: List) -> List[str]:
        """
        Valide la complétude des objectifs.
        
        Args:
            objectifs_list: Liste des objectifs à valider
            
        Returns:
            Liste des erreurs trouvées (vide si tout est valide)
        """
        erreurs = []
        
        if not objectifs_list or len(objectifs_list) == 0:
            erreurs.append("Aucun objectif fourni")
            return erreurs
        
        if len(objectifs_list) < 3:
            erreurs.append("Moins de 3 objectifs fournis")
        
        if len(objectifs_list) > 5:
            erreurs.append("Plus de 5 objectifs fournis")
        
        for i, obj in enumerate(objectifs_list, 1):
            if not isinstance(obj, dict):
                erreurs.append(f"Objectif {i}: format invalide")
                continue
            
            objectif = obj.get('objectif') or obj.get('Objectif', '')
            poids = obj.get('poids') or obj.get('Poids', 0)
            resultat = obj.get('resultat') or obj.get('ResultatAttendu', '')
            
            if not objectif or str(objectif).strip() == "":
                erreurs.append(f"Objectif {i}: description vide")
            
            try:
                poids_int = int(poids)
                if poids_int <= 0:
                    erreurs.append(f"Objectif {i}: poids doit être positif")
                if poids_int > 100:
                    erreurs.append(f"Objectif {i}: poids ne peut dépasser 100%")
            except (ValueError, TypeError):
                erreurs.append(f"Objectif {i}: poids invalide")
        
        return erreurs
    
    def _generer_message_objectifs_incomplets(self, objectifs_list: List, erreurs: List[str]) -> str:
        """
        Génère un message d'erreur détaillé pour les objectifs incomplets.
        
        Args:
            objectifs_list: Liste des objectifs actuels
            erreurs: Liste des erreurs trouvées
            
        Returns:
            Message formaté pour l'utilisateur
        """
        message = "⚠️ **Objectifs incomplets ou invalides**\n\n"
        
        if objectifs_list:
            message += "**Objectifs actuels :**\n"
            for i, obj in enumerate(objectifs_list, 1):
                if isinstance(obj, dict):
                    objectif = obj.get('objectif', obj.get('Objectif', 'Non spécifié'))
                    poids = obj.get('poids', obj.get('Poids', 0))
                    message += f"  {i}. {objectif} ({poids}%)\n"
                else:
                    message += f"  {i}. [Format invalide]\n"
            message += "\n"
        
        message += "**Erreurs à corriger :**\n"
        for erreur in erreurs:
            message += f"  ❌ {erreur}\n"
        
        message += "\n**Format attendu :**\n"
        message += "• Description claire de l'objectif\n"
        message += "• Poids en pourcentage (ex: 25%)\n"
        message += "• Résultat attendu (optionnel)\n\n"
        message += "Veuillez corriger ou ajouter des objectifs."
        
        return message