"""
Actions personnalisées pour le système d'aide Rasa DDR
"""
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet


class ActionAideGenerale(Action):
    """
    Action pour fournir l'aide générale dynamique.
    Vous pouvez modifier le texte ici selon vos besoins.
    """

    def name(self) -> Text:
        return "action_aide_generale"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ===== TEXTE MODIFIABLE ICI =====
        message = """
🤖 **Bienvenue dans l'assistant DDR !**

Voici ce que je peux faire pour vous :

📝 **Gestion des Demandes de Recrutement (DDR)**
• Créer une nouvelle DDR

ℹ️ **Pour plus d'aide sur une action spécifique**, dites :
"Aide pour créer une DDR" ou "Comment ajouter une DDR ?"

💡 **Exemple rapide** :
"Je veux créer une DDR pour un développeur web à la DSI"
        """
        
        # Envoi du message
        dispatcher.utter_message(text=message)
        
        return []


class ActionFournirAideAction(Action):
    """
    Action pour fournir de l'aide contextuelle selon l'action demandée.
    """

    def name(self) -> Text:
        return "action_fournir_aide_action"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        
        action_type = tracker.get_slot("intention_demande")
        action_demandee = tracker.get_slot("action_demandee")
        
        print("DEBUG - ActionFournirAideAction - action_type:", action_type)
        print("DEBUG - ActionFournirAideAction - action_demandee:", action_demandee)
        # Fournir l'aide appropriée
        if action_type == "ajouter" and action_demandee == "DDR":
            dispatcher.utter_message(response="utter_aide_ajout_ddr")
        elif action_type == "modifier" and action_demandee == "DDR":
            dispatcher.utter_message(response="utter_aide_non_disponible")
        elif action_type == "supprimer" and action_demandee == "DDR":
            dispatcher.utter_message(response="utter_aide_non_disponible")
        elif action_type == "voir":
            dispatcher.utter_message(response="utter_aide_non_disponible")
        else:
            # Si aucune action spécifique n'est détectée
            dispatcher.utter_message(response="utter_demander_precisions_aide")
        
        return []


class ActionTraiterDDR(Action):
    """
    Action exemple pour traiter une DDR.
    (À adapter selon votre implémentation existante)
    """

    def name(self) -> Text:
        return "action_traiter_ddr"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Récupérer les entités
        intention = None
        entities = tracker.latest_message.get("entities", [])
        
        entity_dict = {}
        for entity in entities:
            entity_name = entity.get("entity")
            entity_value = entity.get("value")
            entity_dict[entity_name] = entity_value
            
            if entity_name == "intention_demande":
                intention = entity_value
        
        # Logique selon l'intention
        if intention in ["ajouter", "créer", "enregistrer", "soumettre", "faire"]:
            # Vérifier si on a les informations minimales
            required_fields = ["nom_poste", "direction", "nature_contrat", "exploitation"]
            missing_fields = [field for field in required_fields if field not in entity_dict]
            
            if missing_fields:
                message = f"""
📋 **Création de DDR en cours...**

⚠️ Il me manque quelques informations :
{', '.join(missing_fields)}

💡 Pouvez-vous me les fournir ? Ou tapez "aide" pour voir un exemple complet.
                """
            else:
                message = f"""
✅ **DDR créée avec succès !**

📌 Récapitulatif :
• Poste : {entity_dict.get('nom_poste', 'N/A')}
• Direction : {entity_dict.get('direction', 'N/A')}
• Contrat : {entity_dict.get('nature_contrat', 'N/A')}
• Lieu : {entity_dict.get('exploitation', 'N/A')}
{f"• Durée : {entity_dict.get('duree_contrat')}" if 'duree_contrat' in entity_dict else ""}
{f"• Encadreur : {entity_dict.get('nom_encadreur')}" if 'nom_encadreur' in entity_dict else ""}
{f"• Date de mise en service : {entity_dict.get('date_mise_en_service')}" if 'date_mise_en_service' in entity_dict else ""}
{f"• Motif : {entity_dict.get('motif')}" if 'motif' in entity_dict else ""}
{f"• Budget : {entity_dict.get('situation_budget')}" if 'situation_budget' in entity_dict else ""}

📝 Votre demande a été enregistrée.
                """
            
            dispatcher.utter_message(text=message)
        
        else:
            dispatcher.utter_message(
                text="Je n'ai pas compris votre demande. Tapez 'aide' pour plus d'informations."
            )
        
        return []