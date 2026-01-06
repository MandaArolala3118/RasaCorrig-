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

class ActionVerificationPieceJointe(Action):
    """Valide et enregistre les pièces jointes multiples avec sauvegarde automatique des métadonnées"""
    
    def name(self) -> Text:
        return "verification_piece_jointe"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        events = []
        
        # ==========================================
        # ÉTAPE 0 : CAPTURER ET FUSIONNER LES MÉTADONNÉES
        # ==========================================
        latest_metadata = tracker.latest_message.get("metadata", {})
        stored_metadata = tracker.get_slot("session_started_metadata") or {}
        
        latest_attachments = latest_metadata.get("attachments", [])
        stored_attachments = stored_metadata.get("attachments", [])
        
        logger.info(f"🔍 ========== VÉRIFICATION PIÈCE JOINTE ==========")
        logger.info(f"📨 Latest attachments: {len(latest_attachments)}")
        logger.info(f"💾 Stored attachments: {len(stored_attachments)}")
        
        # 🔧 FUSIONNER les métadonnées (éviter les doublons)
        if latest_attachments and len(latest_attachments) > 0:
            logger.info(f"✅ NOUVEAUX FICHIERS DÉTECTÉS dans latest_metadata")
            
            # Créer un set des noms de fichiers existants
            existing_names = {att.get('name') for att in stored_attachments}
            
            # Filtrer uniquement les nouveaux fichiers
            new_attachments_only = [
                att for att in latest_attachments 
                if att.get('name') not in existing_names
            ]
            
            if new_attachments_only:
                logger.info(f"📎 {len(new_attachments_only)} NOUVEAU(X) fichier(s) à ajouter")
                for att in new_attachments_only:
                    logger.info(f"   • {att.get('name')} ({att.get('size')} bytes)")
                
                # Fusionner
                all_attachments = stored_attachments + new_attachments_only
                
                # Mettre à jour les métadonnées stockées
                updated_metadata = {
                    **stored_metadata,
                    "attachments": all_attachments
                }
                
                logger.info(f"💾 SAUVEGARDE: {len(all_attachments)} fichier(s) au total dans session_metadata")
                events.append(SlotSet("session_started_metadata", updated_metadata))
                
                # Utiliser les métadonnées fusionnées pour la validation
                all_metadata = updated_metadata
            else:
                logger.info(f"⏭️ Tous les fichiers sont déjà dans stored_metadata")
                all_metadata = stored_metadata
        else:
            # Pas de nouveaux fichiers, utiliser les métadonnées stockées
            logger.info(f"💾 Utilisation des métadonnées stockées")
            all_metadata = stored_metadata
        
        # ==========================================
        # ÉTAPE 1 : RÉCUPÉRER LES ATTACHMENTS FUSIONNÉS
        # ==========================================
        attachments = all_metadata.get("attachments", [])
        
        logger.info(f"📊 TOTAL d'attachments à traiter: {len(attachments)}")
        if attachments:
            for i, att in enumerate(attachments, 1):
                logger.info(f"   [{i}] {att.get('name')}")
        
        # ==========================================
        # ÉTAPE 2 : RÉCUPÉRER LES FICHIERS DÉJÀ ENREGISTRÉS
        # ==========================================
        piece_jointe_actuelle = tracker.get_slot("piece_jointe") or ""
        fichiers_actuels = [f.strip() for f in piece_jointe_actuelle.split(",") if f.strip()] if piece_jointe_actuelle else []
        
        logger.info(f"📋 Fichiers déjà enregistrés dans le slot: {len(fichiers_actuels)}")
        if fichiers_actuels:
            for f in fichiers_actuels:
                logger.info(f"   • {f}")
        
        # ==========================================
        # ÉTAPE 3 : VALIDER ET ENREGISTRER LES FICHIERS
        # ==========================================
        
        # CAS 1: Fichiers uploadés détectés
        if attachments and len(attachments) > 0:
            nouveaux_fichiers = []
            fichiers_rejetes = []
            fichiers_dupliques = []
            
            # Types de fichiers acceptés
            types_acceptes = [
                'application/pdf',
                'image/jpeg', 'image/jpg', 'image/png',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ]
            
            max_size = 10 * 1024 * 1024  # 10 MB
            
            # Traiter chaque fichier
            for attachment in attachments:
                nom_fichier = attachment.get("name", "fichier_inconnu")
                type_fichier = attachment.get("type", "application/octet-stream")
                taille = attachment.get("size", 0)
                
                logger.info(f"📎 Traitement: {nom_fichier} ({type_fichier}, {taille} bytes)")
                
                # Vérifier si déjà enregistré dans le slot
                if nom_fichier in fichiers_actuels:
                    logger.info(f"⏭️ Fichier déjà enregistré dans le slot: {nom_fichier}")
                    fichiers_dupliques.append(nom_fichier)
                    continue
                
                # Valider le type
                if type_fichier not in types_acceptes:
                    logger.warning(f"❌ Type non accepté: {type_fichier}")
                    fichiers_rejetes.append({
                        'nom': nom_fichier,
                        'raison': f"Type non pris en charge: {type_fichier}"
                    })
                    continue
                
                # Valider la taille
                if taille > max_size:
                    logger.warning(f"❌ Fichier trop volumineux: {taille / 1024 / 1024:.2f} MB")
                    fichiers_rejetes.append({
                        'nom': nom_fichier,
                        'raison': f"Trop volumineux: {taille / 1024 / 1024:.2f} MB (max: 10 MB)"
                    })
                    continue
                
                # Fichier valide
                nouveaux_fichiers.append({
                    'nom': nom_fichier,
                    'type': type_fichier,
                    'taille': taille
                })
                logger.info(f"✅ Fichier valide: {nom_fichier}")
            
            # ==========================================
            # ÉTAPE 4 : CONSTRUIRE LE MESSAGE ET METTRE À JOUR LE SLOT
            # ==========================================
            messages = []
            
            if nouveaux_fichiers:
                # Ajouter les nouveaux fichiers à la liste
                tous_les_fichiers = fichiers_actuels + [f['nom'] for f in nouveaux_fichiers]
                
                # ✅ VALIDATION : Vérifier la longueur totale
                piece_jointe_test = ','.join(tous_les_fichiers)
                MAX_LENGTH = 255
                
                if len(piece_jointe_test) > MAX_LENGTH:
                    logger.warning(f"⚠️ Longueur totale trop grande ({len(piece_jointe_test)} chars)")
                    
                    # Calculer combien on peut en ajouter
                    longueur_actuelle = len(','.join(fichiers_actuels))
                    fichiers_ajoutes = []
                    
                    for fichier in nouveaux_fichiers:
                        nom = fichier['nom']
                        longueur_ajout = len(nom) + 1  # +1 pour la virgule
                        
                        if longueur_actuelle + longueur_ajout <= MAX_LENGTH:
                            fichiers_ajoutes.append(fichier)
                            longueur_actuelle += longueur_ajout
                        else:
                            fichiers_rejetes.append({
                                'nom': nom,
                                'raison': f"Limite de longueur atteinte ({MAX_LENGTH} caractères max)"
                            })
                    
                    nouveaux_fichiers = fichiers_ajoutes
                    tous_les_fichiers = fichiers_actuels + [f['nom'] for f in nouveaux_fichiers]
                
                if nouveaux_fichiers:
                    recap_nouveaux = "\n".join([
                        f"  📎 {f['nom']}\n"
                        f"     • Type: {f['type']}\n"
                        f"     • Taille: {f['taille'] / 1024:.2f} KB"
                        for f in nouveaux_fichiers
                    ])
                    
                    messages.append(
                        f"✅ **{len(nouveaux_fichiers)} fichier(s) enregistré(s)**\n\n{recap_nouveaux}"
                    )
                    
                    # Résumé total
                    messages.append(
                        f"\n📊 **Total: {len(tous_les_fichiers)} fichier(s) joint(s)**"
                    )
                    
                    # Assembler les noms avec des virgules
                    piece_jointe_finale = ','.join(tous_les_fichiers)
                    
                    # Envoyer le message
                    dispatcher.utter_message(text="\n".join(messages))
                    
                    logger.info(f"✅ Slot piece_jointe mis à jour: {piece_jointe_finale}")
                    events.append(SlotSet("piece_jointe", piece_jointe_finale))
            
            # Gérer les fichiers dupliqués
            if fichiers_dupliques:
                messages.append(
                    f"\nℹ️ **{len(fichiers_dupliques)} fichier(s) déjà enregistré(s):**\n" +
                    "\n".join([f"  • {f}" for f in fichiers_dupliques])
                )
            
            # Gérer les fichiers rejetés
            if fichiers_rejetes:
                recap_rejetes = "\n".join([
                    f"  ❌ {f['nom']}\n     → {f['raison']}"
                    for f in fichiers_rejetes
                ])
                
                messages.append(
                    f"\n⚠️ **{len(fichiers_rejetes)} fichier(s) rejeté(s)**\n\n{recap_rejetes}\n\n"
                    f"📋 Types acceptés: PDF, Word, Excel, Images (JPEG, PNG)\n"
                    f"📏 Taille maximale: 10 MB par fichier\n"
                    f"📏 Longueur totale des noms: {MAX_LENGTH} caractères max"
                )
            
            # Si aucun nouveau fichier mais des messages d'info
            if messages and not nouveaux_fichiers:
                dispatcher.utter_message(text="\n".join(messages))
            
            logger.info(f"==========================================\n")
            return events
        
        # CAS 2: Vérifier si déjà enregistré
        if fichiers_actuels:
            logger.info(f"✅ Pièces jointes déjà enregistrées: {','.join(fichiers_actuels)}")
            logger.info(f"==========================================\n")
            return events
        
        # CAS 3: Utilisateur mentionne qu'il a une pièce jointe
        user_message = tracker.latest_message.get('text', '').lower()
        
        mots_cles_fichier = [
            'fichier', 'document', 'pièce jointe', 'piece jointe',
            'joint', 'jointe', 'attaché', 'attachée', 'ci-joint',
            'voici le', 'voilà le', 'je joins', "j'ai joint", "j'envoie"
        ]
        
        if any(kw in user_message for kw in mots_cles_fichier):
            logger.info(f"⚠️ Mention de pièce jointe détectée dans le message mais aucun fichier reçu")
            dispatcher.utter_message(
                text="📎 Vous avez mentionné une pièce jointe, mais je n'ai pas reçu de fichier.\n\n"
                     "💡 Veuillez utiliser le bouton d'upload (📎) pour joindre vos fichiers."
            )
            logger.info(f"==========================================\n")
            events.append(SlotSet("piece_jointe", None))
            return events
        
        # CAS 4: Aucune pièce jointe détectée
        logger.info("ℹ️ Aucune pièce jointe détectée")
        logger.info(f"==========================================\n")
        return events
    

class ActionSupprimerPieceJointe(Action):
    """
    Supprime UN SEUL fichier de la liste des pièces jointes
    Exemples : 
    - "supprime le fichier CV.pdf"
    - "retire le document rapport.docx"
    - "efface la pièce jointe contrat.pdf"
    """
    
    def name(self) -> Text:
        return "action_supprimer_piece_jointe"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Récupérer les fichiers actuels
        piece_jointe_actuelle = tracker.get_slot("piece_jointe") or ""
        fichiers_actuels = [f.strip() for f in piece_jointe_actuelle.split(",") if f.strip()]
        
        if not fichiers_actuels:
            dispatcher.utter_message(
                text="❌ **Aucune pièce jointe à supprimer.**\n\nLa liste est vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION D'UNE PIÈCE JOINTE")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Fichiers actuels: {len(fichiers_actuels)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE LE NOM DU FICHIER
        # ==========================================
        nom_fichier = self._extraire_nom_fichier(user_message, fichiers_actuels)
        
        if not nom_fichier:
            dispatcher.utter_message(
                text="❓ **Quel fichier souhaitez-vous supprimer ?**\n\n"
                     f"📎 **Pièces jointes actuelles ({len(fichiers_actuels)}) :**\n" +
                     "\n".join([f"  • {f}" for f in fichiers_actuels]) +
                     "\n\n💡 **Exemple :** *'Supprime le fichier CV.pdf'*"
            )
            return []
        
        logger.info(f"🎯 Fichier à supprimer: '{nom_fichier}'")
        
        # ==========================================
        # ÉTAPE 2 : VÉRIFIER L'EXISTENCE
        # ==========================================
        fichier_trouve = None
        
        for fichier in fichiers_actuels:
            if self._match_fichier(nom_fichier, fichier):
                fichier_trouve = fichier
                break
        
        if not fichier_trouve:
            suggestions = self._get_suggestions_fichier(nom_fichier, fichiers_actuels)
            
            message_erreur = f"❌ **Le fichier '{nom_fichier}' n'a pas été trouvé.**\n\n"
            
            if suggestions:
                message_erreur += (
                    f"💡 **Fichiers similaires :**\n" +
                    "\n".join([f"  • {s}" for s in suggestions])
                )
            else:
                message_erreur += (
                    f"📎 **Fichiers disponibles :**\n" +
                    "\n".join([f"  • {f}" for f in fichiers_actuels])
                )
            
            dispatcher.utter_message(text=message_erreur)
            return []
        
        # ==========================================
        # ÉTAPE 3 : SUPPRIMER LE FICHIER
        # ==========================================
        fichiers_actuels.remove(fichier_trouve)
        
        logger.info(f"✅ Fichier '{fichier_trouve}' supprimé")
        logger.info(f"📊 Fichiers restants: {len(fichiers_actuels)}")
        
        # ==========================================
        # ÉTAPE 4 : METTRE À JOUR LES MÉTADONNÉES
        # ==========================================
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        stored_attachments = session_metadata.get("attachments", [])
        
        # Supprimer aussi des métadonnées
        updated_attachments = [
            att for att in stored_attachments 
            if att.get('name') != fichier_trouve
        ]
        
        session_metadata["attachments"] = updated_attachments
        
        # ==========================================
        # ÉTAPE 5 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Fichier supprimé avec succès !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"🗑️ **Fichier supprimé :** {fichier_trouve}\n\n"
        message += f"{'─' * 50}\n\n"
        
        if fichiers_actuels:
            message += f"📎 **Pièces jointes restantes ({len(fichiers_actuels)}) :**\n"
            message += "\n".join([f"  • {f}" for f in fichiers_actuels])
        else:
            message += "⚠️ **Toutes les pièces jointes ont été supprimées.**"
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 6 : METTRE À JOUR LES SLOTS
        # ==========================================
        nouvelle_valeur = ','.join(fichiers_actuels) if fichiers_actuels else None
        
        return [
            SlotSet("piece_jointe", nouvelle_valeur),
            SlotSet("session_started_metadata", session_metadata),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _extraire_nom_fichier(self, message: str, fichiers_existants: List[str]) -> Optional[str]:
        """Extrait le nom du fichier à supprimer"""
        
        message_lower = message.lower()
        
        # Pattern 1 : "supprime/retire/efface [le/la] fichier/document X"
        patterns = [
            r"(?:supprime|retire|efface|enlève|enleve)\s+(?:le|la|l')?\s*(?:fichier|document|pièce\s+jointe|piece\s+jointe)?\s+(.+?)(?:\s|$)",
            r"(?:fichier|document|pièce\s+jointe|piece\s+jointe)\s+(.+?)(?:\s+à\s+supprimer|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                nom = match.group(1).strip()
                # Nettoyer
                nom = re.sub(r'\s+(s\'il\s+te\s+plaît|s\'il\s+vous\s+plaît|stp|svp)$', '', nom)
                if len(nom) >= 3:
                    return nom
        
        # Pattern 2 : Chercher directement un nom de fichier existant dans le message
        for fichier in fichiers_existants:
            if fichier.lower() in message_lower:
                return fichier
        
        # Pattern 3 : Extensions de fichiers courantes
        extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.png', '.jpg', '.jpeg']
        for ext in extensions:
            match = re.search(rf'(\S+{re.escape(ext)})', message_lower)
            if match:
                return match.group(1)
        
        return None
    
    def _match_fichier(self, nom_recherche: str, nom_fichier: str) -> bool:
        """Vérifie si deux noms de fichiers correspondent"""
        
        nom_recherche_clean = nom_recherche.lower().strip()
        nom_fichier_clean = nom_fichier.lower().strip()
        
        # Correspondance exacte
        if nom_recherche_clean == nom_fichier_clean:
            return True
        
        # Le nom recherché est contenu dans le nom du fichier
        if nom_recherche_clean in nom_fichier_clean:
            return True
        
        # Le nom du fichier est contenu dans la recherche
        if nom_fichier_clean in nom_recherche_clean:
            return True
        
        # Comparer sans extension
        nom_recherche_sans_ext = re.sub(r'\.[^.]+$', '', nom_recherche_clean)
        nom_fichier_sans_ext = re.sub(r'\.[^.]+$', '', nom_fichier_clean)
        
        if nom_recherche_sans_ext == nom_fichier_sans_ext:
            return True
        
        return False
    
    def _get_suggestions_fichier(self, nom_recherche: str, fichiers: List[str]) -> List[str]:
        """Retourne des suggestions de fichiers similaires"""
        
        from difflib import SequenceMatcher
        
        suggestions = []
        nom_recherche_clean = nom_recherche.lower().strip()
        
        for fichier in fichiers:
            fichier_clean = fichier.lower().strip()
            ratio = SequenceMatcher(None, nom_recherche_clean, fichier_clean).ratio()
            
            if ratio > 0.4:  # Seuil de similarité
                suggestions.append((fichier, ratio))
        
        # Trier par score décroissant
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in suggestions[:3]]


# ==================== SUPPRESSION DE PLUSIEURS PIÈCES JOINTES ====================

class ActionSupprimerPiecesJointesMultiples(Action):
    """
    Supprime PLUSIEURS fichiers de la liste
    Exemples :
    - "supprime CV.pdf et lettre.docx"
    - "retire les fichiers rapport.pdf, facture.xlsx"
    """
    
    def name(self) -> Text:
        return "action_supprimer_pieces_jointes_multiples"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        piece_jointe_actuelle = tracker.get_slot("piece_jointe") or ""
        fichiers_actuels = [f.strip() for f in piece_jointe_actuelle.split(",") if f.strip()]
        
        if not fichiers_actuels:
            dispatcher.utter_message(
                text="❌ **Aucune pièce jointe à supprimer.**"
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE PLUSIEURS PIÈCES JOINTES")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Fichiers actuels: {len(fichiers_actuels)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE TOUS LES NOMS
        # ==========================================
        noms_fichiers = self._extraire_noms_multiples(user_message, fichiers_actuels)
        
        if not noms_fichiers or len(noms_fichiers) < 2:
            dispatcher.utter_message(
                text="❓ **Quels fichiers souhaitez-vous supprimer ?**\n\n"
                     f"📎 **Pièces jointes disponibles ({len(fichiers_actuels)}) :**\n" +
                     "\n".join([f"  • {f}" for f in fichiers_actuels]) +
                     "\n\n💡 **Exemples :**\n"
                     "  • *'Supprime CV.pdf et lettre.docx'*\n"
                     "  • *'Retire rapport.pdf, facture.xlsx'*"
            )
            return []
        
        logger.info(f"🎯 Fichiers à supprimer: {noms_fichiers}")
        
        # ==========================================
        # ÉTAPE 2 : MATCHER AVEC LES FICHIERS EXISTANTS
        # ==========================================
        fichiers_a_supprimer = []
        fichiers_non_trouves = []
        
        for nom in noms_fichiers:
            trouve = False
            for fichier in fichiers_actuels:
                if self._match_fichier(nom, fichier):
                    if fichier not in fichiers_a_supprimer:
                        fichiers_a_supprimer.append(fichier)
                    trouve = True
                    break
            
            if not trouve:
                fichiers_non_trouves.append(nom)
        
        if not fichiers_a_supprimer:
            dispatcher.utter_message(
                text=f"❌ **Aucun des fichiers mentionnés n'a été trouvé.**\n\n"
                     f"❌ Non trouvés : {', '.join(fichiers_non_trouves)}\n\n"
                     f"📎 Fichiers disponibles :\n" +
                     "\n".join([f"  • {f}" for f in fichiers_actuels])
            )
            return []
        
        # ==========================================
        # ÉTAPE 3 : SUPPRIMER
        # ==========================================
        for fichier in fichiers_a_supprimer:
            fichiers_actuels.remove(fichier)
        
        logger.info(f"✅ {len(fichiers_a_supprimer)} fichier(s) supprimé(s)")
        logger.info(f"📊 Fichiers restants: {len(fichiers_actuels)}")
        
        # ==========================================
        # ÉTAPE 4 : METTRE À JOUR LES MÉTADONNÉES
        # ==========================================
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        stored_attachments = session_metadata.get("attachments", [])
        
        updated_attachments = [
            att for att in stored_attachments 
            if att.get('name') not in fichiers_a_supprimer
        ]
        
        session_metadata["attachments"] = updated_attachments
        
        # ==========================================
        # ÉTAPE 5 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **{len(fichiers_a_supprimer)} fichier(s) supprimé(s) !**\n\n"
        
        if fichiers_non_trouves:
            message += (
                f"⚠️ **Fichiers non trouvés :** {', '.join(fichiers_non_trouves)}\n\n"
            )
        
        message += f"{'─' * 50}\n\n"
        message += "🗑️ **Fichiers supprimés :**\n"
        message += "\n".join([f"  ❌ {f}" for f in fichiers_a_supprimer])
        message += f"\n\n{'─' * 50}\n\n"
        
        if fichiers_actuels:
            message += f"📎 **Pièces jointes restantes ({len(fichiers_actuels)}) :**\n"
            message += "\n".join([f"  • {f}" for f in fichiers_actuels])
        else:
            message += "⚠️ **Toutes les pièces jointes ont été supprimées.**"
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 6 : METTRE À JOUR LES SLOTS
        # ==========================================
        nouvelle_valeur = ','.join(fichiers_actuels) if fichiers_actuels else None
        
        return [
            SlotSet("piece_jointe", nouvelle_valeur),
            SlotSet("session_started_metadata", session_metadata),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _extraire_noms_multiples(self, message: str, fichiers_existants: List[str]) -> List[str]:
        """Extrait plusieurs noms de fichiers"""
        
        noms = []
        message_lower = message.lower()
        
        # Pattern 1 : Chercher tous les fichiers existants mentionnés
        for fichier in fichiers_existants:
            if fichier.lower() in message_lower:
                noms.append(fichier)
        
        # Pattern 2 : Extensions de fichiers
        extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.png', '.jpg', '.jpeg']
        for ext in extensions:
            matches = re.findall(rf'(\S+{re.escape(ext)})', message_lower)
            for match in matches:
                if match not in noms:
                    noms.append(match)
        
        # Pattern 3 : Séparateurs "et", ","
        # Diviser par "et" ou ","
        segments = re.split(r'\s+et\s+|,\s*', message)
        
        for segment in segments:
            segment_clean = segment.strip()
            # Chercher un nom de fichier dans chaque segment
            for fichier in fichiers_existants:
                if fichier.lower() in segment_clean.lower():
                    if fichier not in noms:
                        noms.append(fichier)
        
        return noms
    
    def _match_fichier(self, nom_recherche: str, nom_fichier: str) -> bool:
        """Vérifie si deux noms de fichiers correspondent"""
        
        nom_recherche_clean = nom_recherche.lower().strip()
        nom_fichier_clean = nom_fichier.lower().strip()
        
        if nom_recherche_clean == nom_fichier_clean:
            return True
        
        if nom_recherche_clean in nom_fichier_clean or nom_fichier_clean in nom_recherche_clean:
            return True
        
        # Sans extension
        nom_recherche_sans_ext = re.sub(r'\.[^.]+$', '', nom_recherche_clean)
        nom_fichier_sans_ext = re.sub(r'\.[^.]+$', '', nom_fichier_clean)
        
        return nom_recherche_sans_ext == nom_fichier_sans_ext


# ==================== SUPPRESSION DE TOUTES LES PIÈCES JOINTES ====================

class ActionSupprimerToutesPiecesJointes(Action):
    """
    Supprime TOUS les fichiers avec confirmation
    Exemples :
    - "supprime toutes les pièces jointes"
    - "efface tous les fichiers"
    """
    
    def name(self) -> Text:
        return "action_supprimer_toutes_pieces_jointes"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        piece_jointe_actuelle = tracker.get_slot("piece_jointe") or ""
        fichiers_actuels = [f.strip() for f in piece_jointe_actuelle.split(",") if f.strip()]
        
        if not fichiers_actuels:
            dispatcher.utter_message(
                text="ℹ️ **Aucune pièce jointe à supprimer.**\n\nLa liste est déjà vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE TOUTES LES PIÈCES JOINTES")
        logger.info(f"📊 Fichiers actuels: {len(fichiers_actuels)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # VÉRIFICATION : CONFIRMATION EXPLICITE
        # ==========================================
        patterns_confirmation = [
            r"\btous\s+les\s+fichiers?\b",
            r"\btoutes\s+les\s+pièces?\s+jointes?\b",
            r"\btout\b",
            r"\btoutes?\b",
            r"\bl'ensemble\b",
        ]
        
        confirmation_explicite = any(
            re.search(pattern, user_message) 
            for pattern in patterns_confirmation
        )
        
        if not confirmation_explicite:
            dispatcher.utter_message(
                text=f"⚠️ **Êtes-vous sûr(e) de vouloir supprimer TOUTES les pièces jointes ?**\n\n"
                     f"📊 **{len(fichiers_actuels)} fichier(s) seront supprimés :**\n" +
                     "\n".join([f"  • {f}" for f in fichiers_actuels]) +
                     "[Oui supprime tout, Annuler la suppression](action_supprimer_toutes_pieces_jointes)\n\n"
            )
            return []
        
        # ==========================================
        # SAUVEGARDER POUR LE MESSAGE
        # ==========================================
        nb_fichiers = len(fichiers_actuels)
        fichiers_supprimes = fichiers_actuels.copy()
        
        # ==========================================
        # SUPPRESSION TOTALE
        # ==========================================
        fichiers_actuels = []
        
        # Métadonnées
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        session_metadata["attachments"] = []
        
        # ==========================================
        # MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Toutes les pièces jointes ont été supprimées !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"🗑️ **{nb_fichiers} fichier(s) supprimé(s) :**\n\n"
        message += "\n".join([f"  ❌ {f}" for f in fichiers_supprimes])
        message += f"\n\n{'─' * 50}\n\n"
        message += "⚠️ **La liste des pièces jointes est maintenant vide.**"
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"✅ Tous les fichiers supprimés")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # METTRE À JOUR LES SLOTS
        # ==========================================
        return [
            SlotSet("piece_jointe", None),
            SlotSet("session_started_metadata", session_metadata),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]


# ==================== MODIFICATION/REMPLACEMENT D'UNE PIÈCE JOINTE ====================
class ActionRemplacerPieceJointe(Action):
    """
    Remplace un fichier par un autre
    Détecte automatiquement le nouveau fichier uploadé
    """
    
    def name(self) -> Text:
        return "action_remplacer_piece_jointe"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        piece_jointe_actuelle = tracker.get_slot("piece_jointe") or ""
        fichiers_actuels = [f.strip() for f in piece_jointe_actuelle.split(",") if f.strip()]
        
        if not fichiers_actuels:
            dispatcher.utter_message(
                text="❌ **Aucune pièce jointe à remplacer.**\n\nLa liste est vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔄 REMPLACEMENT D'UNE PIÈCE JOINTE")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Fichiers actuels: {fichiers_actuels}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : RÉCUPÉRER LES MÉTADONNÉES
        # ==========================================
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        latest_metadata = tracker.latest_message.get("metadata", {})
        
        # ✅ CORRECTION : Récupérer les attachments stockés ET le nouveau
        stored_attachments = session_metadata.get("attachments", [])
        latest_attachments = latest_metadata.get("attachments", [])
        
        logger.info(f"📊 Stored attachments: {len(stored_attachments)}")
        logger.info(f"📨 Latest attachments: {len(latest_attachments)}")
        
        # ==========================================
        # ÉTAPE 2 : DÉTECTER LE NOUVEAU FICHIER UPLOADÉ
        # ==========================================
        nouveau_fichier_uploade = None
        nouveau_fichier_metadata = None
        
        if latest_attachments and len(latest_attachments) > 0:
            # Prendre le dernier fichier uploadé (le plus récent)
            nouveau_fichier_metadata = latest_attachments[-1]
            nouveau_fichier_uploade = nouveau_fichier_metadata.get('name')
            logger.info(f"✅ Nouveau fichier détecté: '{nouveau_fichier_uploade}'")
        
        # ==========================================
        # ÉTAPE 3 : EXTRAIRE L'ANCIEN FICHIER
        # ==========================================
        ancien_fichier = self._extraire_ancien_fichier(user_message, fichiers_actuels)
        
        if not ancien_fichier:
            dispatcher.utter_message(
                text="❓ **Quel fichier souhaitez-vous remplacer ?**\n\n"
                     f"📎 **Fichiers disponibles :**\n" +
                     "\n".join([f"  • {f}" for f in fichiers_actuels]) +
                     "\n\n💡 **Exemples :**\n"
                     "  • *'Remplace CV.pdf par le nouveau'*\n"
                     "  • *'Modifie memoire.pdf par ceci'* (avec upload)"
            )
            return []
        
        logger.info(f"🎯 Fichier à remplacer: '{ancien_fichier}'")
        
        # ==========================================
        # ÉTAPE 4 : VÉRIFIER L'EXISTENCE
        # ==========================================
        fichier_trouve = None
        index_fichier = None
        
        for i, fichier in enumerate(fichiers_actuels):
            if self._match_fichier(ancien_fichier, fichier):
                fichier_trouve = fichier
                index_fichier = i
                break
        
        if not fichier_trouve:
            suggestions = self._get_suggestions_fichier(ancien_fichier, fichiers_actuels)
            
            message_erreur = f"❌ **Le fichier '{ancien_fichier}' n'a pas été trouvé.**\n\n"
            
            if suggestions:
                message_erreur += (
                    f"💡 **Fichiers similaires :**\n" +
                    "\n".join([f"  • {s}" for s in suggestions]) +
                    "\n\n"
                )
            
            message_erreur += (
                f"📎 **Fichiers disponibles :**\n" +
                "\n".join([f"  • {f}" for f in fichiers_actuels])
            )
            
            dispatcher.utter_message(text=message_erreur)
            return []
        
        # ==========================================
        # ÉTAPE 5 : VÉRIFIER SI UN NOUVEAU FICHIER EST DISPONIBLE
        # ==========================================
        if not nouveau_fichier_uploade or not nouveau_fichier_metadata:
            dispatcher.utter_message(
                text=f"📎 **Remplacement du fichier : {fichier_trouve}**\n\n"
                     f"⚠️ Aucun nouveau fichier détecté.\n\n"
                     f"💡 Veuillez uploader le nouveau fichier via le bouton 📎, puis répétez votre demande."
            )
            return []
        
        # ==========================================
        # ÉTAPE 6 : REMPLACER LE FICHIER DANS LA LISTE
        # ==========================================
        fichiers_actuels[index_fichier] = nouveau_fichier_uploade
        
        logger.info(f"✅ Remplacement effectué:")
        logger.info(f"   Ancien: '{fichier_trouve}'")
        logger.info(f"   Nouveau: '{nouveau_fichier_uploade}'")
        
        # ==========================================
        # ✅ ÉTAPE 7 : METTRE À JOUR LES MÉTADONNÉES (CORRIGÉ)
        # ==========================================
        updated_attachments = []
        ancien_fichier_remplace = False
        
        # Parcourir les attachments stockés
        for att in stored_attachments:
            if att.get('name') == fichier_trouve:
                # ✅ Remplacer par le nouveau fichier
                updated_attachments.append(nouveau_fichier_metadata)
                ancien_fichier_remplace = True
                logger.info(f"   ✅ Métadonnées remplacées: {fichier_trouve} → {nouveau_fichier_uploade}")
            else:
                # ✅ CONSERVER tous les autres fichiers
                updated_attachments.append(att)
                logger.info(f"   ✓ Conservé: {att.get('name')}")
        
        # Si l'ancien fichier n'était pas dans stored_attachments, ajouter le nouveau
        if not ancien_fichier_remplace:
            updated_attachments.append(nouveau_fichier_metadata)
            logger.info(f"   ✅ Nouveau fichier ajouté: {nouveau_fichier_uploade}")
        
        # ✅ Mettre à jour session_metadata
        session_metadata["attachments"] = updated_attachments
        
        logger.info(f"📊 Métadonnées mises à jour:")
        logger.info(f"   Total fichiers: {len(updated_attachments)}")
        for att in updated_attachments:
            logger.info(f"   • {att.get('name')}")
        
        # ==========================================
        # ÉTAPE 8 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Fichier remplacé avec succès !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"❌ **Ancien fichier :** {fichier_trouve}\n"
        message += f"✅ **Nouveau fichier :** {nouveau_fichier_uploade}\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"📎 **Liste mise à jour ({len(fichiers_actuels)}) :**\n"
        message += "\n".join([f"  • {f}" for f in fichiers_actuels])
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 9 : METTRE À JOUR LES SLOTS
        # ==========================================
        nouvelle_valeur = ','.join(fichiers_actuels)
        
        return [
            SlotSet("piece_jointe", nouvelle_valeur),
            SlotSet("session_started_metadata", session_metadata),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _extraire_ancien_fichier(self, message: str, fichiers_existants: List[str]) -> Optional[str]:
        """
        Extrait le nom de l'ancien fichier à remplacer
        Patterns flexibles pour "modifier X par Y", "remplace X par ceci", etc.
        """
        
        message_lower = message.lower()
        
        logger.info(f"🔍 Extraction ancien fichier...")
        logger.info(f"   Message: '{message}'")
        
        # ==========================================
        # PATTERN 1 : "remplace/modifie X par [Y/ceci/nouveau]"
        # ==========================================
        patterns_remplacement = [
            # "modifier le fichier X par Y"
            r"(?:modifier|modifie|remplacer|remplace|changer|change)\s+(?:le\s+)?fichier\s+(.+?)\s+par\s+(?:ceci|le\s+nouveau|un\s+nouveau|celui-ci|ce\s+fichier)",
            
            # "modifier X par Y"
            r"(?:modifier|modifie|remplacer|remplace|changer|change)\s+(.+?)\s+par\s+(?:ceci|le\s+nouveau|un\s+nouveau|celui-ci|ce\s+fichier)",
            
            # "remplace le fichier X"
            r"(?:remplace|modifier|change)\s+(?:le\s+|la\s+)?(?:fichier|document|pièce\s+jointe)?\s*(.+?)(?:\s+par|\s*$)",
        ]
        
        for pattern_idx, pattern in enumerate(patterns_remplacement, 1):
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                nom_extrait = match.group(1).strip()
                
                # Nettoyer
                nom_extrait = re.sub(r'\s+(par|avec|de)$', '', nom_extrait)
                
                logger.info(f"  ✓ Pattern {pattern_idx} match: '{nom_extrait}'")
                
                # Vérifier si ce nom correspond à un fichier existant
                for fichier in fichiers_existants:
                    if self._match_fichier(nom_extrait, fichier):
                        logger.info(f"  ✅ Fichier trouvé: '{fichier}'")
                        return fichier
                
                # Si pas de correspondance exacte, retourner quand même le nom extrait
                if len(nom_extrait) >= 3:
                    logger.info(f"  ⚠️ Pas de correspondance exacte, retour: '{nom_extrait}'")
                    return nom_extrait
        
        # ==========================================
        # PATTERN 2 : Chercher un fichier existant dans le message
        # ==========================================
        for fichier in fichiers_existants:
            if fichier.lower() in message_lower:
                logger.info(f"  ✅ Fichier trouvé directement: '{fichier}'")
                return fichier
        
        # ==========================================
        # PATTERN 3 : Extensions de fichiers
        # ==========================================
        extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.png', '.jpg', '.jpeg']
        for ext in extensions:
            match = re.search(rf'(\S+{re.escape(ext)})', message_lower)
            if match:
                nom_fichier = match.group(1)
                logger.info(f"  ✓ Extension trouvée: '{nom_fichier}'")
                
                # Vérifier si correspond à un fichier existant
                for fichier in fichiers_existants:
                    if self._match_fichier(nom_fichier, fichier):
                        logger.info(f"  ✅ Correspondance: '{fichier}'")
                        return fichier
                
                # Retourner quand même
                return nom_fichier
        
        logger.warning("  ❌ Aucun fichier détecté")
        return None
    
    def _match_fichier(self, nom_recherche: str, nom_fichier: str) -> bool:
        """Vérifie si deux noms de fichiers correspondent (avec fuzzy matching)"""
        
        from difflib import SequenceMatcher
        
        nom_recherche_clean = nom_recherche.lower().strip()
        nom_fichier_clean = nom_fichier.lower().strip()
        
        # Correspondance exacte
        if nom_recherche_clean == nom_fichier_clean:
            return True
        
        # Contenu
        if nom_recherche_clean in nom_fichier_clean or nom_fichier_clean in nom_recherche_clean:
            return True
        
        # Sans extension
        nom_recherche_sans_ext = re.sub(r'\.[^.]+$', '', nom_recherche_clean)
        nom_fichier_sans_ext = re.sub(r'\.[^.]+$', '', nom_fichier_clean)
        
        if nom_recherche_sans_ext == nom_fichier_sans_ext:
            return True
        
        # Fuzzy matching (80% de similarité)
        ratio = SequenceMatcher(None, nom_recherche_clean, nom_fichier_clean).ratio()
        if ratio > 0.8:
            return True
        
        return False
    
    def _get_suggestions_fichier(self, nom_recherche: str, fichiers: List[str]) -> List[str]:
        """Retourne des suggestions de fichiers similaires"""
        
        from difflib import SequenceMatcher
        
        suggestions = []
        nom_recherche_clean = nom_recherche.lower().strip()
        
        for fichier in fichiers:
            fichier_clean = fichier.lower().strip()
            ratio = SequenceMatcher(None, nom_recherche_clean, fichier_clean).ratio()
            
            if ratio > 0.3:  # Seuil bas pour capturer plus de suggestions
                suggestions.append((fichier, ratio))
        
        # Trier par score décroissant
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in suggestions[:3]]