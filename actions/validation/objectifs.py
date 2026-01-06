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

from actions.services.ddr_service import get_backend_service

class ActionVerificationObjectif(Action):
    """Valide et enregistre les objectifs progressivement (même incomplets)"""
    
    def name(self) -> Text:
        return "verification_objectif"
    
    def _nettoyer_poids(self, poids_str: str) -> float:
        """Nettoie et convertit un poids en nombre"""
        poids_clean = re.sub(r'[^\d.]', '', str(poids_str))
        return float(poids_clean) if poids_clean else 0.0
    def _extraire_objectifs_manuel(self, message_text: str) -> List[Dict]:
        """
        ✅ CORRECTION MAJEURE : Support complet de tous les formats d'objectifs
        Nouveauté : Gère "L'objectif N est X pour une poids de Y% afin de Z"
        """
        objectifs = []

        print(f"\n{'='*80}")
        print(f"📄 MESSAGE À ANALYSER:")
        print(f"{message_text[:500]}...")
        print(f"📊 Longueur: {len(message_text)} caractères")
        print(f"{'='*80}\n")

        # ==========================================
        # ✅ STRATÉGIE 0A : Format "L'objectif N est X pour un/une poids de Y% afin de Z"
        # ==========================================
        pattern_objectif_numero = r"l'objectif\s+(\d+)\s+est\s+(.+?)(?:,?\s*pour\s+(?:un|une|le|la)\s+poids\s+(?:de\s+)?(\d+)\s*%)"
    
        match_avec_numero = re.search(pattern_objectif_numero, message_text, re.IGNORECASE | re.DOTALL)
    
        if match_avec_numero:
            numero = int(match_avec_numero.group(1))
            description_brute = match_avec_numero.group(2).strip()
            poids = float(match_avec_numero.group(3))
        
            # Nettoyer la description
            description = re.sub(r',?\s*pour\s+(?:un|une|le|la)\s+poids.*$', '', description_brute, flags=re.IGNORECASE).strip()
        
            # Chercher le résultat après le poids
            reste_texte = message_text[match_avec_numero.end():]
        
            resultat_patterns = [
                r'afin\s+de\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r"afin\s+d'(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))",
                r'pour\s+(?:que|garantir)\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r'en\s+vue\s+de\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r'(?:,|;)?\s*(.{15,}?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',  # Fallback
            ]
        
            resultat = None
            for pattern_idx, pattern in enumerate(resultat_patterns, 1):
                match_res = re.search(pattern, reste_texte, re.IGNORECASE | re.DOTALL)
                if match_res:
                    resultat = match_res.group(1).strip()
                    # Nettoyer les préfixes parasites
                    resultat = re.sub(r'^(?:et\s+le\s+résultat\s+attendu\s+est\s+|,\s*)', '', resultat, flags=re.IGNORECASE)
                    resultat = resultat.strip('.,; ')
                
                    if len(resultat) >= 10:
                        print(f"  ✅ Résultat extrait (pattern {pattern_idx}): '{resultat[:60]}...'")
                        break
                    else:
                        resultat = None
        
            # Si aucun résultat trouvé, prendre tout ce qui suit
            if not resultat:
                resultat = reste_texte[:300].strip()
                resultat = re.sub(r'\s+', ' ', resultat).strip('.,; ')
        
            print(f"✅ PATTERN 'L'objectif N est' détecté:")
            print(f"  • Numéro: {numero}")
            print(f"  • Description: {description}")
            print(f"  • Poids: {poids}%")
            print(f"  • Résultat: {resultat[:100] if resultat else 'NON TROUVÉ'}...")
        
            objectifs.append({
                'numero': numero,
                'objectif': description,
                'poids': poids,
                'resultat': resultat or ""
            })
        
            print(f"\n✅ TOTAL EXTRAIT: 1 objectif (format 'L'objectif N est')")
            return objectifs
    
        # ==========================================
        # ✅ STRATÉGIE 0B : Format "L'objectif est d'avoir..." (SANS numéro)
        # ==========================================
        pattern_avoir = r"l'objectif\s+est\s+d'(?:avoir|être|assurer|garantir)\s+(.+?)(?:,?\s*pour\s+(?:un|une|le|la)\s+poids\s+(?:de\s+)?(\d+)\s*%)"

        match_avoir = re.search(pattern_avoir, message_text, re.IGNORECASE | re.DOTALL)
        if match_avoir:
            description_brute = match_avoir.group(1).strip()
            poids = float(match_avoir.group(2))
    
            # Nettoyer la description (enlever ", pour" à la fin si présent)
            description = re.sub(r',?\s*pour\s+(?:un|une|le|la)\s+poids.*$', '', description_brute, flags=re.IGNORECASE).strip()
    
            # Chercher le résultat après le poids
            reste_texte = message_text[match_avoir.end():]
    
            resultat_patterns = [
                r'afin\s+de\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r'pour\s+(?:que|garantir)\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r'en\s+vue\s+de\s+(.+?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',
                r'(?:,|;)?\s*(.{15,}?)(?=\s*(?:\n|objectif\s+\d+|dotation|pièce|$))',  # Fallback : tout après
            ]
    
            resultat = None
            for pattern_idx, pattern in enumerate(resultat_patterns, 1):
                match_res = re.search(pattern, reste_texte, re.IGNORECASE | re.DOTALL)
                if match_res:
                    resultat = match_res.group(1).strip()
                    # Nettoyer les préfixes parasites
                    resultat = re.sub(r'^(?:et\s+le\s+résultat\s+attendu\s+est\s+|,\s*)', '', resultat, flags=re.IGNORECASE)
                    resultat = resultat.strip('.,; ')
            
                    if len(resultat) >= 10:
                        print(f"  ✅ Résultat extrait (pattern {pattern_idx}): '{resultat[:60]}...'")
                        break
                    else:
                        resultat = None
    
            # Si aucun résultat trouvé, prendre tout ce qui suit le poids
            if not resultat:
                resultat = reste_texte[:300].strip()
                resultat = re.sub(r'\s+', ' ', resultat).strip('.,; ')
    
            print(f"✅ PATTERN 'L'objectif est d'avoir' détecté:")
            print(f"  • Description: {description}")
            print(f"  • Poids: {poids}%")
            print(f"  • Résultat: {resultat[:100] if resultat else 'NON TROUVÉ'}...")
    
            objectifs.append({
                'numero': 1,
                'objectif': description,
                'poids': poids,
                'resultat': resultat or ""
            })
    
            print(f"\n✅ TOTAL EXTRAIT: 1 objectif (format 'L'objectif est d'avoir')")
            return objectifs

        # ==========================================
        # STRATÉGIE 1: Détection format "ajoute objectif N avec..."
        # ==========================================
        text_norm = message_text.lower()
        pattern_ajout = r'(?:ajoute|ajouter|créer|créé|nouveau)\s+(?:l\'|le\s+)?objectif\s+(\d+)\s+avec\s+(?:la\s+)?description\s*:\s*(.+?)\s+avec\s+un\s+poids\s+de\s+(\d+)\s*%?\s*,?\s*résultats?\s+attendus?\s*:\s*(.+?)(?=\s*(?:objectif|dotation|pièce|$))'

        for match in re.finditer(pattern_ajout, text_norm, re.IGNORECASE | re.DOTALL):
            numero = int(match.group(1))
            description = match.group(2).strip()
            poids = float(match.group(3))
            resultat = match.group(4).strip()
    
            # Récupérer avec la casse originale
            start_desc = match.start(2)
            end_desc = match.end(2)
            start_result = match.start(4)
            end_result = match.end(4)
    
            description_original = message_text[start_desc:end_desc].strip()
            resultat_original = message_text[start_result:end_result].strip()
    
            print(f"✅ PATTERN AJOUT détecté:")
            print(f"  • Numéro: {numero}")
            print(f"  • Description: {description_original}")
            print(f"  • Poids: {poids}%")
            print(f"  • Résultat: {resultat_original}")
    
            if description_original and poids and resultat_original:
                objectifs.append({
                    'numero': numero,
                    'objectif': description_original,
                    'poids': poids,
                    'resultat': resultat_original
                })
        
                print(f"\n✅ TOTAL EXTRAIT: 1 objectif (format ajout direct)")
                return objectifs

        # ==========================================
        # STRATÉGIE 2: Détection des positions d'objectifs
        # ==========================================
        positions_objectifs = []

        # Normaliser pour la recherche (mais garder l'original pour l'extraction)
        text_norm = message_text.lower()

        # Pattern: "Objectif N :" (avec ou SANS espace après :)
        for match in re.finditer(r'objectif\s+(\d+)\s*:\s*', text_norm):
            numero = int(match.group(1))
            if not any(p['numero'] == numero for p in positions_objectifs):
                positions_objectifs.append({
                    'numero': numero,
                    'start': match.start(),
                    'end': match.end(),
                    'format': 'explicite_numero'
                })
                print(f"  ✓ Pattern 'Objectif {numero} :' détecté à position {match.start()}")

        # Pattern: "l'objectif N est de" ou "objectif N est de"
        for match in re.finditer(r"l'?objectif\s+(\d+)\s+est\s+de\s+", text_norm):
            numero = int(match.group(1))
            if not any(p['numero'] == numero for p in positions_objectifs):
                positions_objectifs.append({
                    'numero': numero,
                    'start': match.start(),
                    'end': match.end(),
                    'format': 'est_de'
                })
                print(f"  ✓ Pattern 'objectif {numero} est de' détecté à position {match.start()}")

        # Pattern: "Objectif N est de" ou "Objectif N consiste à"
        for match in re.finditer(
            r'objectif\s+(\d+)(?:\s+(?:est\s+de|consiste\s+[àa]|vise\s+[àa]))',
            text_norm
        ):
            numero = int(match.group(1))
            if not any(p['numero'] == numero for p in positions_objectifs):
                positions_objectifs.append({
                    'numero': numero,
                    'start': match.start(),
                    'end': match.end(),
                    'format': 'explicite_verbe'
                })
                print(f"  ✓ Pattern 'Objectif {numero} est de...' détecté")

        # Pattern: Ordinaux
        ordinaux = {
            'premier': 1, 'première': 1, '1er': 1, '1ère': 1, '1ere': 1,
            'deuxième': 2, 'deuxieme': 2, 'second': 2, 'seconde': 2, '2ème': 2, '2eme': 2, '2e': 2,
            'troisième': 3, 'troisieme': 3, '3ème': 3, '3eme': 3, '3e': 3,
            'quatrième': 4, 'quatrieme': 4, '4ème': 4, '4eme': 4, '4e': 4,
            'cinquième': 5, 'cinquieme': 5, '5ème': 5, '5eme': 5
        }

        for ordinal, numero in ordinaux.items():
            pattern = rf'\b(?:le|la|l\'|un|une)\s+{ordinal}\s+objectif(?:\s+(?:est\s+de|consiste\s+[àa]|vise\s+[àa]))?'
            for match in re.finditer(pattern, text_norm):
                if not any(p['numero'] == numero and abs(p['start'] - match.start()) < 20 for p in positions_objectifs):
                    positions_objectifs.append({
                        'numero': numero,
                        'start': match.start(),
                        'end': match.end(),
                        'format': 'ordinal'
                    })
                    print(f"  ✓ Ordinal '{ordinal}' détecté (Objectif {numero})")

        print(f"\n🔍 POSITIONS DÉTECTÉES: {len(positions_objectifs)} objectif(s)")

        # Trier et dédupliquer
        positions_obj = sorted(positions_objectifs, key=lambda x: x['start'])
        positions_uniques = {}
        for pos in positions_obj:
            if pos['numero'] not in positions_uniques:
                positions_uniques[pos['numero']] = pos

        positions_obj = sorted(positions_uniques.values(), key=lambda x: x['start'])

        # ==========================================
        # EXTRACTION DES BLOCS
        # ==========================================
        for i, pos_info in enumerate(positions_obj):
            numero = pos_info['numero']
            start = pos_info['end']
    
            if i + 1 < len(positions_obj):
                end = positions_obj[i + 1]['start']
            else:
                end = len(message_text)
        
                # Chercher des marqueurs de fin
                marqueurs_fin = [
                    r'\n\s*je\s+souhaite\s+(?:un|une|des)\s+(?:smartphone|ordinateur|badge|équipement)',
                    r'\n\s*dotations?\s*:\s*',
                    r'\n\s*(?:pièces?|documents?)\s+joint(?:e|s)?\s*:\s*',
                ]
        
                texte_fin = message_text[start:]
                for marqueur in marqueurs_fin:
                    match = re.search(marqueur, texte_fin, re.IGNORECASE | re.MULTILINE)
                    if match:
                        potential_end = start + match.start()
                        if potential_end < end:
                            end = potential_end
    
            bloc_raw = message_text[start:end]
    
            print(f"\n{'─'*80}")
            print(f"📄 BLOC OBJECTIF {numero} BRUT ({len(bloc_raw)} chars):")
            print(f"{bloc_raw[:300]}{'...' if len(bloc_raw) > 300 else ''}")
            print(f"{'─'*80}")
    
            # ==========================================
            # EXTRACTION DESCRIPTION
            # ==========================================
            description = None
    
            desc_patterns = [
                r'^[\s:]*(.+?)(?=\s*,?\s*pour\s+(?:un|une|le|la)\s+poids\s+)',
                r'^[\s:]*(.+?)(?=\s*,\s*avec\s+(?:un\s+|comme\s+)?poids)',
                r'^[\s:]*(.+?)(?=\s+avec\s+(?:comme\s+)?poids\s+)',
                r'^[\s:]*(.+?)(?=\s*poids\s*[:=])',
                r'^[\s:]*(.+?)(?=\s+\d+\s*%)',
                r'^[\s:]*(.+?)(?=\s*,\s*en\s+(?:veillant|assurant|garantissant|s\'assurant))',
                r'^[\s:]*([A-ZÀ-ŸÉÈÊËÏÎÔÖÙÛÜŸŒÆÇ][^\n]{10,}?)(?=\s*(?:poids|avec\s+un\s+poids|le\s+poids))',
            ]
    
            for pattern_idx, pattern in enumerate(desc_patterns, 1):
                match = re.search(pattern, bloc_raw, re.IGNORECASE | re.DOTALL)
                if match:
                    desc_candidate = match.group(1).strip()
            
                    desc_candidate = re.sub(
                        r'^(de\s+|est\s+de\s+|d\'avoir\s+|d\'être\s+|d\'assurer\s+|consiste\s+[àa]\s+|vise\s+[àa]\s+)', 
                        '', 
                        desc_candidate, 
                        flags=re.IGNORECASE
                    )
            
                    if len(desc_candidate) >= 5:
                        description = desc_candidate
                        print(f"  ✅ Description retenue (pattern {pattern_idx}): '{description[:80]}'")
                        break
    
            if not description or len(description) < 5:
                description = bloc_raw[:100].strip()
                if description:
                    description = re.sub(r'\s+', ' ', description).strip('.,;:')
    
            if description:
                description = re.sub(r'\s+', ' ', description).strip('.,;')
                if description:
                    description = description[0].upper() + description[1:]
    
            print(f"  ✅ Description finale: {description if description else 'NON TROUVÉE'}")
    
            # ==========================================
            # EXTRACTION POIDS
            # ==========================================
            poids = None
    
            poids_patterns = [
                r'pour\s+(?:un|une|le|la)\s+poids\s+(?:de\s+)?(\d+)\s*%',
                r'avec\s+(?:comme\s+)?poids\s+(\d+)\s*%',
                r'poids\s*(?::|de|est\s+de)?\s*(\d+)\s*%',
                r'avec\s+un\s+poids\s+de\s+(\d+)\s*%',
                r',?\s*poids\s*:\s*(\d+)\s*%',
                r'pondéré\s+(?:à|de)\s+(\d+)\s*%',
                r'\(\s*poids\s*:\s*(\d+)\s*%?\s*\)',
                r'(\d+)\s*%',
            ]
    
            for pattern_idx, pattern in enumerate(poids_patterns, 1):
                match = re.search(pattern, bloc_raw, re.IGNORECASE)
                if match:
                    poids = float(match.group(1))
                    print(f"  ✅ Poids détecté (pattern {pattern_idx}): {poids}%")
                    break
    
            if not poids:
                print(f"  ⚠️ Poids non trouvé, valeur par défaut: 0%")
                poids = 0
    
            # ==========================================
            # EXTRACTION RÉSULTAT
            # ==========================================
            resultat = None
    
            resultat_patterns = [
                r'afin\s+de\s+(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r"afin\s+d'(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))",
                r'et\s+le\s+r[ée]sultat\s+attendu\s+est\s+(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r'r[ée]sultats?\s+attendus?\s*:\s*(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r'pour\s+que\s+(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r'pour\s+(?:garantir|assurer)\s+(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r',\s*en\s+(?:veillant|assurant|garantissant|s\'assurant|maintenant)\s+(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
                r'indicateurs?\s*:\s*(.+?)(?=\s*(?:\n\n+|objectif\s+\d+|dotation|pièce|$))',
            ]
    
            for pattern_idx, pattern in enumerate(resultat_patterns, 1):
                match = re.search(pattern, bloc_raw, re.IGNORECASE | re.DOTALL)
                if match:
                    resultat = match.group(1).strip()
                    print(f"  ✅ Résultat détecté (pattern {pattern_idx}): '{resultat[:60]}...'")
                    break
    
            # Fallback : chercher après le poids
            if not resultat:
                poids_match = None
                for pattern in poids_patterns:
                    poids_match = re.search(pattern, bloc_raw, re.IGNORECASE)
                    if poids_match:
                        break
        
                if poids_match:
                    texte_apres_poids = bloc_raw[poids_match.end():].strip()
                    texte_apres_poids = re.sub(r'^\s*et\s+le\s+r[ée]sultat\s+attendu\s+est\s+', '', texte_apres_poids, flags=re.IGNORECASE)
                    texte_apres_poids = re.sub(r'^[,.\s:]+', '', texte_apres_poids)
            
                    match_participe = re.search(
                        r'(?:afin\s+de|afin\s+d\'|pour\s+(?:que|garantir)|en\s+(?:veillant|assurant|garantissant))\s+(.+)',
                        texte_apres_poids,
                        re.IGNORECASE | re.DOTALL
                    )
            
                    if match_participe:
                        resultat = match_participe.group(1).strip()
                    else:
                        match_fin_resultat = re.search(r'\n\n+|(?:^|\n)\s*[Oo]bjectif\s+\d+\s*[:.]', texte_apres_poids, re.MULTILINE)
                        if match_fin_resultat:
                            resultat = texte_apres_poids[:match_fin_resultat.start()].strip()
                        else:
                            resultat = texte_apres_poids.strip()
                
                    print(f"  ✅ Résultat extrait après poids: '{resultat[:60]}...'")
    
            if not resultat or len(resultat) < 10:
                print(f"  ⚠️ Résultat non trouvé ou trop court")
                resultat = ""
            else:
                resultat = re.sub(r'\s+', ' ', resultat).strip('.,; ')
    
            print(f"  ✅ Résultat final: {resultat[:80] if resultat else 'NON TROUVÉ'}...")
    
            # ==========================================
            # ENREGISTREMENT (MÊME SI INCOMPLET)
            # ==========================================
            objectifs.append({
                'numero': numero,
                'objectif': description or "",
                'poids': poids if poids else 0,
                'resultat': resultat or ""
            })
            print(f"  ✅ Objectif {numero} ENREGISTRÉ")

        objectifs.sort(key=lambda x: x['numero'])

        print(f"\n{'='*80}")
        print(f"✅ EXTRACTION TERMINÉE")
        print(f"📊 TOTAL EXTRAIT: {len(objectifs)} objectif(s)")
        print(f"{'='*80}\n")

        return objectifs
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # ==========================================
        # NORMALISATION DU MESSAGE
        # ==========================================
        current_message = tracker.latest_message.get('text', '')
        
        current_message_normalized = re.sub(r':([^\s])', r': \1', current_message)
        current_message_normalized = re.sub(r'([^\s]):(\s)', r'\1: \2', current_message_normalized)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔍 VERIFICATION_OBJECTIF - DÉMARRAGE")
        logger.info(f"📋 Message original: '{current_message}'")
        if current_message != current_message_normalized:
            logger.info(f"✏️ Message normalisé: '{current_message_normalized}'")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # PROTECTION ANTI-DOUBLE TRAITEMENT
        # ==========================================
        session_metadata = tracker.get_slot("session_started_metadata") or {}
        last_processed_message = session_metadata.get("last_processed_objectif_message", "")
        
        if last_processed_message == current_message_normalized:
            logger.info("⏭️ Message déjà traité, validation ignorée")
            return []
        
        # ==========================================
        # RÉCUPÉRATION DE LA LISTE EXISTANTE
        # ==========================================
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        print(f"\n{'='*80}")
        print(f"📥 MESSAGE REÇU:")
        print(f"{current_message_normalized}")
        print(f"\n📊 ÉTAT ACTUEL:")
        print(f"  • Objectifs déjà enregistrés: {len(objectifs_list)}")
        print(f"{'='*80}")
        
        # ==========================================
        # EXTRACTION
        # ==========================================
        nouveaux_objectifs = self._extraire_objectifs_manuel(current_message_normalized)
        
        print(f"\n{'='*80}")
        print(f"📋 RÉSULTAT DE L'EXTRACTION: {len(nouveaux_objectifs)} objectif(s)")
        print(f"{'='*80}\n")
        
        # ==========================================
        # FILTRAGE DES DOUBLONS
        # ==========================================
        objectifs_uniques = []
        
        for nouvel_obj in nouveaux_objectifs:
            est_doublon = False
            desc_nouvelle = nouvel_obj.get('objectif', '').lower().strip()
            
            # Ignorer les objectifs sans description (vraiment vides)
            if not desc_nouvelle or len(desc_nouvelle) < 3:
                logger.info(f"⏭️ Objectif ignoré (description trop courte)")
                continue
            
            for obj_existant in objectifs_list:
                desc_existante = obj_existant.get('objectif', '').lower().strip()
                ratio = SequenceMatcher(None, desc_existante, desc_nouvelle).ratio()
                
                if ratio > 0.80:
                    logger.info(f"⏭️ Objectif doublon détecté (similarité: {ratio:.2%})")
                    est_doublon = True
                    break
            
            for obj_deja_ajoute in objectifs_uniques:
                desc_deja_ajoute = obj_deja_ajoute.get('objectif', '').lower().strip()
                ratio = SequenceMatcher(None, desc_deja_ajoute, desc_nouvelle).ratio()
                
                if ratio > 0.80:
                    logger.info(f"⏭️ Doublon interne détecté (similarité: {ratio:.2%})")
                    est_doublon = True
                    break
            
            if not est_doublon:
                objectifs_uniques.append(nouvel_obj)
                logger.info(f"✅ Objectif unique validé")
        
        nouveaux_objectifs = objectifs_uniques
        
        # ==========================================
        # VALIDATION 1 : Au moins 1 objectif détecté
        # ==========================================
        if not nouveaux_objectifs:
            logger.info("ℹ️ Aucun objectif détecté dans le message")
            return []
        
        # ==========================================
        # VALIDATION 2 : Maximum 5 objectifs
        # ==========================================
        nb_nouveaux = len(nouveaux_objectifs)
        nb_total = len(objectifs_list) + nb_nouveaux
        
        if nb_total > 5:
            dispatcher.utter_message(
                text=f"⚠️ **Trop d'objectifs**\n\n"
                    f"• Objectifs déjà enregistrés : **{len(objectifs_list)}**\n"
                    f"• Nouveaux objectifs détectés : **{nb_nouveaux}**\n"
                    f"• Total : **{nb_total}** (maximum : **5**)\n\n"
                    f"❌ Veuillez retirer **{nb_total - 5}** objectif(s)."
            )
            return []
        
        # ==========================================
        # ✅ IDENTIFIER LES OBJECTIFS INCOMPLETS
        # ==========================================
        objectifs_incomplets = []
        
        for obj in nouveaux_objectifs:
            problemes = []
            
            if not obj.get('objectif') or len(obj['objectif']) < 10:
                problemes.append("**description manquante ou trop courte**")
            
            if not obj.get('poids') or obj['poids'] < 5 or obj['poids'] > 100:
                problemes.append("**poids invalide (doit être entre 5% et 100%)**")
            
            if not obj.get('resultat') or len(obj['resultat']) < 10:
                problemes.append("**indicateur de résultat manquant**")
            
            if problemes:
                obj_desc = obj.get('objectif', 'Non spécifié')[:50]
                objectifs_incomplets.append({
                    'numero': obj['numero'],
                    'description': obj_desc,
                    'problemes': problemes,
                    'objectif': obj
                })
        
        # ==========================================
        # RENUMÉROTER ET AJOUTER (MÊME SI INCOMPLETS)
        # ==========================================
        for i, obj in enumerate(nouveaux_objectifs):
            obj['numero'] = len(objectifs_list) + i + 1
        
        objectifs_list.extend(nouveaux_objectifs)
        
        somme_poids = sum(obj["poids"] for obj in objectifs_list)
        
        # ==========================================
        # MESSAGE DE CONFIRMATION
        # ==========================================
        confirmation = (
            f"📊 **Progression : {len(objectifs_list)}/3 minimum (5 maximum)**\n"
            f"📊 **Total des poids : {somme_poids:.0f}%**\n\n"
            f"{'─' * 50}\n\n"
        )
        
        for obj in objectifs_list:
            is_new = any(nobj['numero'] == obj['numero'] for nobj in nouveaux_objectifs)
            marqueur = "🆕" if is_new else "✓"
            
            # Vérifier si l'objectif est complet
            est_complet = (
                obj.get('objectif') and len(obj['objectif']) >= 10 and
                obj.get('poids') and 5 <= obj['poids'] <= 100 and
                obj.get('resultat') and len(obj['resultat']) >= 10
            )
            
            statut = "✅" if est_complet else "⚠️"
            
            confirmation += (
                f"{marqueur} {statut} **Objectif {obj['numero']} :** {obj['objectif'] or '(Non spécifié)'}\n"
                f"   📊 **Poids :** {obj['poids']:.0f}%\n"
                f"   📈 **Résultat attendu :** {obj['resultat'] or '(Non spécifié)'}\n\n"
            )
        
        confirmation += f"{'─' * 50}\n\n"
        
        # ==========================================
        # AFFICHER LES PROBLÈMES
        # ==========================================
        if objectifs_incomplets:
            confirmation += "⚠️ **Objectifs incomplets détectés !**\n\n"
            
            for obj_incomplet in objectifs_incomplets:
                confirmation += (
                    f"**Objectif {obj_incomplet['numero']}** : {obj_incomplet['description']}...\n"
                    f"   ❌ Problèmes : {', '.join(obj_incomplet['problemes'])}\n\n"
                )
            
            confirmation += (
                f"{'─' * 50}\n\n"
                f"📝 **Veuillez corriger ces objectifs avant de continuer.**\n\n"
                f"💡 Utilisez la commande **'modifier l'objectif X'** pour chaque objectif incomplet."
            )
        
        # ==========================================
        # VÉRIFICATION FINALE
        # ==========================================
        session_metadata["last_processed_objectif_message"] = current_message_normalized
        
        tous_complets = len(objectifs_incomplets) == 0
        
        if len(objectifs_list) < 3:
            objectifs_manquants = 3 - len(objectifs_list)
            confirmation += (
                f"\n⚠️ **Il manque encore {objectifs_manquants} objectif(s)**\n\n"
                f"Veuillez fournir {objectifs_manquants} objectif(s) supplémentaire(s)."
            )
            
            dispatcher.utter_message(text=confirmation)
            
            return [
                SlotSet("session_started_metadata", session_metadata),
                SlotSet("objectifs_list", objectifs_list),
                SlotSet("is_complet_objectifs", False)
            ]
        
        elif not tous_complets:
            dispatcher.utter_message(text=confirmation)
            
            return [
                SlotSet("session_started_metadata", session_metadata),
                SlotSet("objectifs_list", objectifs_list),
                SlotSet("is_complet_objectifs", False)
            ]
        
        elif abs(somme_poids - 100) > 0.1:
            confirmation += (
                f"\n⚠️ **Attention : Somme des poids = {somme_poids:.0f}%**\n\n"
                f"La somme doit être **100%** pour finaliser.\n"
                f"Différence : **{100 - somme_poids:+.0f}%**\n\n"
                f"Vous pouvez :\n"
                f"• Ajuster les poids existants\n"
                f"• Ajouter d'autres objectifs (maximum {5 - len(objectifs_list)} restant(s))"
            )
            
            dispatcher.utter_message(text=confirmation)
            
            return [
                SlotSet("session_started_metadata", session_metadata),
                SlotSet("objectifs_list", objectifs_list),
                SlotSet("is_complet_objectifs", False)
            ]
        
        else:
            confirmation += (
                f"\n✅ **Tous les objectifs sont complets et validés !**\n"
                f"✅ **Somme des poids : {somme_poids:.0f}% (parfait !)**\n\n"
                f"🎉 Vous pouvez maintenant passer à l'étape suivante."
            )
            
            dispatcher.utter_message(text=confirmation)
            
            return [
                SlotSet("session_started_metadata", session_metadata),
                SlotSet("objectifs_list", objectifs_list),
                SlotSet("is_complet_objectifs", True)
            ]

# [Le reste du code reste identique - ActionModifierObjectif, etc.]
class ActionModifierObjectif(Action):
    """Permet de modifier un ou plusieurs champs d'un objectif existant"""
    
    def name(self) -> Text:
        return "action_modifier_objectif"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Récupérer la liste actuelle
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        if not objectifs_list:
            dispatcher.utter_message(
                text="❌ Aucun objectif à modifier. Veuillez d'abord créer des objectifs."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        # ==========================================
        # ÉTAPE 1 : DÉTECTER QUEL OBJECTIF MODIFIER
        # ==========================================
        numero_a_modifier = self._extraire_numero_objectif(user_message)
        
        if not numero_a_modifier:
            dispatcher.utter_message(
                text="❓ Quel objectif souhaitez-vous modifier ?\n\n"
                     f"📋 Objectifs actuels :\n" +
                     "\n".join([
                         f"  • **Objectif {obj['numero']}** : {obj['objectif'][:60]}..."
                         for obj in objectifs_list
                     ]) +
                     "\n\n💬 Exemple : *'Je veux modifier l'objectif 2'*"
            )
            return []
        
        # Vérifier que le numéro existe
        objectif_trouve = None
        index_objectif = None
        
        for i, obj in enumerate(objectifs_list):
            if obj['numero'] == numero_a_modifier:
                objectif_trouve = obj
                index_objectif = i
                break
        
        if not objectif_trouve:
            dispatcher.utter_message(
                text=f"❌ L'objectif **{numero_a_modifier}** n'existe pas.\n\n"
                     f"📋 Objectifs disponibles : {', '.join([str(obj['numero']) for obj in objectifs_list])}"
            )
            return []
        
        # ==========================================
        # ÉTAPE 2 : DÉTECTER CE QUI DOIT ÊTRE MODIFIÉ
        # ==========================================
        modifications = self._extraire_modifications(user_message, objectif_trouve)
        
        if not modifications:
            # Aucune modification détectée : demander ce qu'il faut changer
            dispatcher.utter_message(
                text=f"🔍 **Objectif {numero_a_modifier} actuel :**\n\n"
                     f"📝 **Description :** {objectif_trouve['objectif']}\n"
                     f"📊 **Poids :** {objectif_trouve['poids']}%\n"
                     f"📈 **Résultat :** {objectif_trouve['resultat']}\n\n"
                     f"{'─' * 50}\n\n"
                     f"Que souhaitez-vous modifier ?\n\n"
                     f"💡 **Exemples :**\n"
                     f"  • *'Change le poids à 30%'*\n"
                     f"  • *'Modifie la description en : ...'*\n"
                     f"  • *'Change le résultat attendu : ...'*\n"
                     f"  • *'Modifie tout : description X, poids Y%, résultat Z'*"
            )
            return []
        
        # ==========================================
        # ÉTAPE 3 : APPLIQUER LES MODIFICATIONS
        # ==========================================
        ancien_objectif = objectif_trouve.copy()
        
        if 'objectif' in modifications:
            objectif_trouve['objectif'] = modifications['objectif']
        
        if 'poids' in modifications:
            objectif_trouve['poids'] = modifications['poids']
        
        if 'resultat' in modifications:
            objectif_trouve['resultat'] = modifications['resultat']
        
        # Remplacer dans la liste
        objectifs_list[index_objectif] = objectif_trouve
        
        # ==========================================
        # ÉTAPE 4 : VALIDATION DE LA SOMME DES POIDS
        # ==========================================
        somme_poids = sum(obj['poids'] for obj in objectifs_list)
        
        # ==========================================
        # ÉTAPE 5 : AFFICHER LE RÉSUMÉ
        # ==========================================
        message_confirmation = f"✅ **Objectif {numero_a_modifier} modifié avec succès !**\n\n"
        
        # Comparaison avant/après
        changements = []
        
        if 'objectif' in modifications:
            changements.append(
                f"📝 **Description**\n"
                f"   Avant : *{ancien_objectif['objectif'][:60]}...*\n"
                f"   Après : *{objectif_trouve['objectif'][:60]}...*"
            )
        
        if 'poids' in modifications:
            changements.append(
                f"📊 **Poids**\n"
                f"   Avant : {ancien_objectif['poids']}%\n"
                f"   Après : {objectif_trouve['poids']}%"
            )
        
        if 'resultat' in modifications:
            changements.append(
                f"📈 **Résultat attendu**\n"
                f"   Avant : *{ancien_objectif['resultat'][:60]}...*\n"
                f"   Après : *{objectif_trouve['resultat'][:60]}...*"
            )
        
        message_confirmation += "\n\n".join(changements)
        message_confirmation += f"\n\n{'─' * 50}\n\n"
        
        # État global
        message_confirmation += f"📊 **Nouvelle somme des poids : {somme_poids:.0f}%**\n\n"
        
        if abs(somme_poids - 100) > 0.1:
            message_confirmation += (
                f"⚠️ La somme n'est pas égale à 100%.\n"
                f"Différence : **{100 - somme_poids:+.0f}%**\n\n"
                f"Vous pouvez ajuster les autres objectifs si nécessaire."
            )
        else:
            message_confirmation += "✅ La somme des poids est correcte (100%) !"
        
        dispatcher.utter_message(text=message_confirmation)
        
        # Mettre à jour le slot
        return [
            SlotSet("objectifs_list", objectifs_list),
            SlotSet("is_complet_objectifs", abs(somme_poids - 100) < 0.1 and len(objectifs_list) >= 3),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _extraire_numero_objectif(self, message: str) -> Optional[int]:
        """Extrait le numéro de l'objectif à modifier avec une flexibilité maximale"""
        
        patterns = [
            # Patterns directs avec "objectif"
            r"objectif\s+(?:numéro\s+|n°\s+|#|numero\s+)?(\d+)",
            r"(?:l'|le\s+)?objectif\s+(\d+)",
            r"obj\s+(\d+)",  # Abréviation
            
            # Patterns avec ordinaux + objectif
            r"(?:le|l')\s+(\d+)(?:ème|eme|er|ère|ere)\s+objectif",
            
            # Patterns avec verbes d'action + objectif
            r"(?:modifier|changer|éditer|corriger|change|modifie|édite|corrige|mettre à jour|update|maj)\s+(?:le\s+|l')?(?:poids|description|résultat|texte)?\s*(?:de\s+|du\s+|d')?(?:l'|le\s+)?objectif\s+(\d+)",
            
            # Patterns inversés (numéro avant "objectif")
            r"(?:modifier|changer|éditer|corriger|change|modifie|édite|corrige)\s+(?:le\s+|l')?(\d+)(?:ème|eme|er)?\s*(?:objectif)?",
            
            # Patterns avec prépositions
            r"(?:pour|sur|dans)\s+(?:l'|le\s+)?objectif\s+(\d+)",
            r"objectif\s+(?:n|numéro|numero|number)?\s*[°#:]?\s*(\d+)",
            
            # Patterns très courts et naturels
            r"(?:^|\s)(?:le|l')?\s*(\d+)(?:\s|$)",  # Juste "le 2", "l'1", "3"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                numero = int(match.group(1))
                # Validation: le numéro doit être raisonnable (1-20)
                if 1 <= numero <= 20:
                    return numero
        
        # Détecter les ordinaux en toutes lettres
        ordinaux = {
            'premier': 1, 'première': 1, '1er': 1, '1ère': 1, '1ere': 1,
            'deuxième': 2, 'deuxieme': 2, 'second': 2, 'seconde': 2, '2ème': 2, '2eme': 2,
            'troisième': 3, 'troisieme': 3, '3ème': 3, '3eme': 3,
            'quatrième': 4, 'quatrieme': 4, '4ème': 4, '4eme': 4,
            'cinquième': 5, 'cinquieme': 5, '5ème': 5, '5eme': 5,
            'sixième': 6, 'sixieme': 6, '6ème': 6, '6eme': 6,
            'septième': 7, 'septieme': 7, '7ème': 7, '7eme': 7,
            'huitième': 8, 'huitieme': 8, '8ème': 8, '8eme': 8,
            'neuvième': 9, 'neuvieme': 9, '9ème': 9, '9eme': 9,
            'dixième': 10, 'dixieme': 10, '10ème': 10, '10eme': 10,
        }
        
        for ordinal, numero in ordinaux.items():
            if ordinal in message.lower():
                return numero
        
        return None
    
    def _extraire_modifications(
        self,
        message: str,
        objectif_actuel: Dict
    ) -> Dict[str, Any]:
        """
        Extrait les modifications demandées
        Retourne un dict avec les clés : 'objectif', 'poids', 'resultat'
        """
        
        modifications = {}
        message_norm = message.lower()
        
        # ==========================================
        # 1. DÉTECTER MODIFICATION DU POIDS
        # ==========================================
        poids_patterns = [
            # Patterns avec verbes d'action + poids
            r"(?:change|modifie|met|mettre|modifier|changer|remplace|remplacer|passe|passer|fixe|fixer|définir|ajuste|ajuster)\s+(?:le\s+|la\s+)?poids\s+(?:à|de|en|par|sur|:|=)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            
            # Patterns directs poids + préposition
            r"poids\s+(?:à|de|en|par|sur|:|=)\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"(?:à|de|en|par|avec|sur)\s+(\d+(?:[.,]\d+)?)\s*%\s+(?:de\s+)?poids",
            
            # Patterns avec "un/le poids de"
            r"(?:avec|à)\s+un\s+poids\s+(?:de|à|par)\s+(\d+(?:[.,]\d+)?)\s*%?",
            r"(?:le|un)\s+poids\s+(?:de|à|est|sera|devient)\s+(\d+(?:[.,]\d+)?)\s*%?",
            
            # Patterns avec pourcentage avant "poids"
            r"(\d+(?:[.,]\d+)?)\s*%\s+(?:de\s+|pour\s+le\s+|comme\s+)?poids",
            
            # Patterns très flexibles (ordre inversé)
            r"pondération\s+(?:à|de|en|par|:|=)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"(\d+(?:[.,]\d+)?)\s*%\s+(?:de\s+)?pondération",
            
            # Pattern simple: juste le nombre avec %
            r"(?:^|\s)(?:à|en|de|par)?\s*(\d+(?:[.,]\d+)?)\s*%(?:\s|$)",
        ]
        
        for pattern in poids_patterns:
            match = re.search(pattern, message_norm)
            if match:
                try:
                    poids_str = match.group(1).replace(',', '.')
                    nouveau_poids = float(poids_str)
                    if 1 <= nouveau_poids <= 100:
                        modifications['poids'] = nouveau_poids
                        break
                except (ValueError, IndexError):
                    continue
        
        # ==========================================
        # 2. DÉTECTER MODIFICATION DE LA DESCRIPTION
        # ==========================================
        desc_patterns = [
            # Patterns avec verbes d'action
            r"(?:change|modifie|remplace|modifier|changer|remplacer|met|mettre|définis|définir|transforme|transformer)\s+(?:la\s+|l')?description\s+(?:en|par|à|:|de|avec|pour)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|avec|et\s+(?:poids|résultat)|$))",
            
            # Patterns directs "description :"
            r"description\s*[:=]\s*[\"']?(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|$))",
            r"(?:nouvelle|nouveau)\s+description\s*:?\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|$))",
            
            # Patterns avec "objectif" comme synonyme
            r"(?:change|modifie|remplace|modifier|changer)\s+(?:l'|le\s+)?objectif\s+(?:en|par|à|:|de|pour)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|avec|et\s+(?:poids|résultat)|$))",
            r"(?:nouvel|nouveau)\s+objectif\s*:?\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|$))",
            
            # Pattern "devient"
            r"(?:description|objectif)\s+devient\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|$))",
            
            # Pattern "texte" comme synonyme
            r"(?:change|modifie|remplace)\s+(?:le\s+)?texte\s+(?:en|par|à|:|de)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|résultat|pondération|$))",
            
            # Pattern inversé (description après le contenu)
            r"[:\"](.{15,}?)[:\"](?:\s+comme\s+|\s+pour\s+la\s+)?(?:description|objectif)",
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, message_norm, re.DOTALL)
            if match:
                nouvelle_desc = match.group(1).strip()
                nouvelle_desc = re.sub(r'\s+', ' ', nouvelle_desc)
                nouvelle_desc = nouvelle_desc.strip('"\',.:;')
                
                if len(nouvelle_desc) >= 10:
                    # Reconstruire avec la casse originale
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouvelle_desc_original = message[start_pos:end_pos].strip()
                    nouvelle_desc_original = nouvelle_desc_original.strip('"\',.:;')
                    
                    modifications['objectif'] = nouvelle_desc_original
                    break
        
        # ==========================================
        # 3. DÉTECTER MODIFICATION DU RÉSULTAT
        # ==========================================
        result_patterns = [
            # Patterns avec verbes d'action
            r"(?:change|modifie|remplace|modifier|changer|remplacer|met|mettre|définis|définir)\s+(?:le\s+|l')?résultat\s+(?:attendu)?\s*(?:en|par|à|:|de|avec|pour)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|pondération|$))",
            
            # Patterns directs "résultat :"
            r"résultat\s+(?:attendu)?\s*[:=]\s*[\"']?(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|pondération|$))",
            r"(?:nouveau|nouvelle)\s+résultat\s+(?:attendu)?\s*:?\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|pondération|$))",
            
            # Patterns avec "indicateur"
            r"(?:change|modifie|remplace|modifier|changer)\s+(?:l'|le\s+)?indicateur\s*(?:en|par|à|:|de|pour)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|$))",
            r"indicateur\s*[:=]\s*[\"']?(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|$))",
            
            # Pattern "devient"
            r"(?:résultat|indicateur)\s+devient\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|$))",
            
            # Patterns avec "mesure" ou "KPI"
            r"(?:mesure|kpi|metric|métrique)\s*[:=]\s*[\"']?(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|$))",
            r"(?:change|modifie)\s+(?:la\s+)?(?:mesure|métrique)\s+(?:en|par|à|:)\s*[:\"]?\s*(.+?)(?=\s*(?:,\s*)?(?:poids|objectif|description|$))",
            
            # Pattern inversé
            r"[:\"](.{15,}?)[:\"](?:\s+comme\s+|\s+pour\s+le\s+)?(?:résultat|indicateur)",
        ]
        
        for pattern in result_patterns:
            match = re.search(pattern, message_norm, re.DOTALL)
            if match:
                nouveau_resultat = match.group(1).strip()
                nouveau_resultat = re.sub(r'\s+', ' ', nouveau_resultat)
                nouveau_resultat = nouveau_resultat.strip('"\',.:;')
                
                if len(nouveau_resultat) >= 10:
                    # Reconstruire avec la casse originale
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouveau_resultat_original = message[start_pos:end_pos].strip()
                    nouveau_resultat_original = nouveau_resultat_original.strip('"\',.:;')
                    
                    modifications['resultat'] = nouveau_resultat_original
                    break
        
        return modifications
class ActionModifierMultipleObjectifs(Action):
    """Permet de modifier plusieurs objectifs en une seule commande"""
    
    def name(self) -> Text:
        return "action_modifier_multiple_objectifs"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        if not objectifs_list:
            dispatcher.utter_message(
                text="❌ Aucun objectif à modifier. Veuillez d'abord créer des objectifs."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '')
        
        # ==========================================
        # ÉTAPE 1 : DÉTECTER SI MULTI-MODIFICATION
        # ==========================================
        is_multiple = self._est_modification_multiple(user_message)
        
        if not is_multiple:
            # Si une seule modification, rediriger vers l'action simple
            return [FollowupAction("action_modifier_objectif")]
        
        # ==========================================
        # ÉTAPE 2 : EXTRAIRE TOUTES LES MODIFICATIONS
        # ==========================================
        modifications_list = self._extraire_toutes_modifications(
            user_message, 
            objectifs_list
        )
        
        if not modifications_list:
            dispatcher.utter_message(
                text="❓ Je n'ai pas pu comprendre quels objectifs modifier.\n\n")
            return []
        
        # ==========================================
        # ÉTAPE 3 : VALIDER LES NUMÉROS D'OBJECTIFS
        # ==========================================
        numeros_valides = [obj['numero'] for obj in objectifs_list]
        modifications_valides = []
        modifications_invalides = []
        
        for modif in modifications_list:
            if modif['numero'] in numeros_valides:
                modifications_valides.append(modif)
            else:
                modifications_invalides.append(modif['numero'])
        
        if not modifications_valides:
            dispatcher.utter_message(
                text=f"❌ Aucun des objectifs mentionnés n'existe.\n\n"
                     f"📋 Objectifs disponibles : {', '.join([str(n) for n in numeros_valides])}"
            )
            return []
        
        # ==========================================
        # ÉTAPE 4 : APPLIQUER TOUTES LES MODIFICATIONS
        # ==========================================
        objectifs_modifies = []
        
        for modif in modifications_valides:
            # Trouver l'objectif correspondant
            for i, obj in enumerate(objectifs_list):
                if obj['numero'] == modif['numero']:
                    ancien_objectif = obj.copy()
                    
                    # Appliquer les changements
                    if 'objectif' in modif['changements']:
                        obj['objectif'] = modif['changements']['objectif']
                    
                    if 'poids' in modif['changements']:
                        obj['poids'] = modif['changements']['poids']
                    
                    if 'resultat' in modif['changements']:
                        obj['resultat'] = modif['changements']['resultat']
                    
                    objectifs_list[i] = obj
                    
                    objectifs_modifies.append({
                        'numero': modif['numero'],
                        'ancien': ancien_objectif,
                        'nouveau': obj,
                        'changements': modif['changements']
                    })
                    break
        
        # ==========================================
        # ÉTAPE 5 : CALCULER LA NOUVELLE SOMME
        # ==========================================
        somme_poids = sum(obj['poids'] for obj in objectifs_list)
        
        # ==========================================
        # ÉTAPE 6 : GÉNÉRER LE MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **{len(objectifs_modifies)} objectif(s) modifié(s) avec succès !**\n\n"
        
        # Avertissement si certains objectifs n'existent pas
        if modifications_invalides:
            message += (
                f"⚠️ Objectifs ignorés (inexistants) : "
                f"{', '.join([str(n) for n in modifications_invalides])}\n\n"
            )
        
        message += "{'─' * 50}\n\n"
        
        # Détails des modifications
        for idx, modif_info in enumerate(objectifs_modifies, 1):
            numero = modif_info['numero']
            ancien = modif_info['ancien']
            nouveau = modif_info['nouveau']
            changements = modif_info['changements']
            
            message += f"**📝 Objectif {numero}**\n\n"
            
            if 'objectif' in changements:
                message += (
                    f"  • Description\n"
                    f"    Avant : *{ancien['objectif'][:50]}...*\n"
                    f"    Après : *{nouveau['objectif'][:50]}...*\n\n"
                )
            
            if 'poids' in changements:
                message += (
                    f"  • Poids : {ancien['poids']}% → **{nouveau['poids']}%**\n\n"
                )
            
            if 'resultat' in changements:
                message += (
                    f"  • Résultat\n"
                    f"    Avant : *{ancien['resultat'][:50]}...*\n"
                    f"    Après : *{nouveau['resultat'][:50]}...*\n\n"
                )
            
            if idx < len(objectifs_modifies):
                message += f"{'─' * 50}\n\n"
        
        # ==========================================
        # ÉTAPE 7 : VALIDATION DE LA SOMME DES POIDS
        # ==========================================
        message += f"\n📊 **Nouvelle somme des poids : {somme_poids:.0f}%**\n\n"
        
        if abs(somme_poids - 100) > 0.1:
            message += (
                f"⚠️ La somme n'est pas égale à 100%.\n"
                f"Différence : **{100 - somme_poids:+.0f}%**\n\n"
                f"Vous pouvez ajuster les objectifs si nécessaire."
            )
        else:
            message += "✅ La somme des poids est correcte (100%) !"
        
        dispatcher.utter_message(text=message)
        
        return [
            SlotSet("objectifs_list", objectifs_list),
            SlotSet("is_complet_objectifs", abs(somme_poids - 100) < 0.1 and len(objectifs_list) >= 3),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _est_modification_multiple(self, message: str) -> bool:
        """Détecte si l'utilisateur veut modifier plusieurs objectifs"""
        
        message_lower = message.lower()
        
        # Compter le nombre de références à "objectif"
        patterns = [
            r"objectif\s+\d+",
            r"(?:le|l')\s+\d+(?:ème|eme|er)?\s*(?:objectif)?",
            r"obj\s+\d+",
        ]
        
        total_references = 0
        for pattern in patterns:
            matches = re.findall(pattern, message_lower)
            total_references += len(matches)
        
        # Chercher des mots de liaison
        mots_liaison = ['et', 'puis', 'aussi', 'également', ',']
        a_liaison = any(mot in message_lower for mot in mots_liaison)
        
        return total_references >= 2 or (total_references >= 1 and a_liaison)
    def _extraire_toutes_modifications(
            self, 
            message: str, 
            objectifs_list: List[Dict]
        ) -> List[Dict]:
            """
            Extrait toutes les modifications demandées pour tous les objectifs
            VERSION CORRIGÉE - Détecte mieux les segments multiples
            """
            
            modifications = []
            message_lower = message.lower()
            
            logger.info(f"\n{'='*80}")
            logger.info(f"🔍 EXTRACTION MODIFICATIONS MULTIPLES (VERSION CORRIGÉE)")
            logger.info(f"📋 Message: '{message}'")
            logger.info(f"{'='*80}\n")
            
            # ==========================================
            # STRATÉGIE AMÉLIORÉE : DÉCOUPAGE INTELLIGENT
            # ==========================================
            
            # Pattern amélioré qui capture TOUS les cas :
            # "et l'objectif 2", "et objectif 3", "et le 2ème objectif"
            split_pattern = r'\s+et\s+(?=(?:l\'|le\s+|l\s+)?(?:objectif\s+)?\d)'
            segments_raw = re.split(split_pattern, message, flags=re.IGNORECASE)
            
            logger.info(f"📊 SPLIT INITIAL: {len(segments_raw)} segment(s)")
            for idx, seg in enumerate(segments_raw, 1):
                logger.info(f"  [{idx}] '{seg[:120]}'")
            
            # Nettoyer les segments
            segments = []
            for s in segments_raw:
                s_clean = s.strip()
                # Accepter les segments plus courts pour capturer "l'objectif 2 avec comme description X"
                if s_clean and len(s_clean) >= 5:
                    segments.append(s_clean)
            
            logger.info(f"\n📊 SEGMENTS NETTOYÉS: {len(segments)} segment(s)")
            
            # ==========================================
            # TRAITER CHAQUE SEGMENT
            # ==========================================
            for idx, segment in enumerate(segments, 1):
                logger.info(f"\n{'─'*80}")
                logger.info(f"  SEGMENT [{idx}/{len(segments)}]")
                logger.info(f"  Contenu: '{segment[:200]}'")
                logger.info(f"{'─'*80}")
                
                # Extraire le numéro d'objectif
                numero = self._extraire_numero_objectif_segment(segment)
                
                if not numero:
                    logger.warning(f"  ⚠️ Aucun numéro trouvé, tentative d'extraction étendue...")
                    # Fallback : chercher n'importe quel chiffre isolé
                    match_chiffre = re.search(r'\b(\d)\b', segment)
                    if match_chiffre:
                        numero = int(match_chiffre.group(1))
                        logger.info(f"  ✓ Numéro trouvé via fallback: {numero}")
                    else:
                        logger.warning(f"  ✗ Segment ignoré")
                        continue
                
                logger.info(f"  ✓ Objectif numéro: {numero}")
                
                # Extraire les modifications pour cet objectif
                changements = self._extraire_modifications_segment_ameliore(
                    segment,
                    numero,
                    objectifs_list
                )
                
                if changements:
                    modifications.append({
                        'numero': numero,
                        'changements': changements
                    })
                    logger.info(f"  ✅ CHANGEMENTS: {list(changements.keys())}")
                else:
                    logger.warning(f"  ⚠️ Aucun changement détecté")
            
            # ==========================================
            # FALLBACK SI AUCUN SEGMENT N'EST TROUVÉ
            # ==========================================
            if not modifications:
                logger.info(f"\n{'='*80}")
                logger.info("🔄 FALLBACK: Extraction globale par pattern")
                logger.info(f"{'='*80}\n")
                
                # Pattern global qui capture tout entre deux objectifs
                pattern = r"(?:l'|le\s+)?objectif\s+(\d+)\s*(.+?)(?=\s+et\s+(?:l'|le\s+)?objectif\s+\d+|$)"
                matches = list(re.finditer(pattern, message, re.IGNORECASE | re.DOTALL))
                
                logger.info(f"📊 Matches trouvés: {len(matches)}")
                
                for match_idx, match in enumerate(matches, 1):
                    numero = int(match.group(1))
                    contenu = match.group(2).strip()
                    
                    logger.info(f"\n  Match [{match_idx}] - Objectif {numero}:")
                    logger.info(f"    Contenu: '{contenu[:200]}'")
                    
                    changements = self._extraire_modifications_segment_ameliore(
                        contenu,
                        numero,
                        objectifs_list
                    )
                    
                    if changements:
                        modifications.append({
                            'numero': numero,
                            'changements': changements
                        })
                        logger.info(f"    ✅ Changements: {list(changements.keys())}")
            
            # ==========================================
            # RÉSULTAT FINAL
            # ==========================================
            logger.info(f"\n{'='*80}")
            logger.info(f"✅ EXTRACTION TERMINÉE")
            logger.info(f"📊 TOTAL: {len(modifications)} modification(s)")
            
            if modifications:
                for mod in modifications:
                    logger.info(f"  • Objectif {mod['numero']}: {list(mod['changements'].keys())}")
            else:
                logger.warning("  ⚠️ Aucune modification extraite")
            
            logger.info(f"{'='*80}\n")
            
            return modifications


    def _extraire_modifications_segment_ameliore(
        self,
        segment: str,
        numero: int,
        objectifs_list: List[Dict]
    ) -> Dict[str, Any]:
        """
        VERSION AMÉLIORÉE qui détecte mieux les descriptions
        """
        
        changements = {}
        segment_lower = segment.lower()
        
        logger.info(f"\n  🔬 Analyse détaillée du segment pour objectif {numero}:")
        
        # Trouver l'objectif actuel
        objectif_actuel = None
        for obj in objectifs_list:
            if obj['numero'] == numero:
                objectif_actuel = obj
                break
        
        if not objectif_actuel:
            logger.warning(f"  ⚠️ Objectif {numero} introuvable dans la liste")
            return {}
        
        # ==========================================
        # 1. EXTRAIRE LE POIDS (inchangé)
        # ==========================================
        poids_patterns = [
            r"(?:avec\s+le\s+)?poids\s+(?:à|de|:|=)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"(?:à|de|en|par|avec)\s+(\d+(?:[.,]\d+)?)\s*%",
            r"poids\s+(\d+)",
            r"(\d+(?:[.,]\d+)?)\s*%",
        ]
        
        for pattern in poids_patterns:
            match = re.search(pattern, segment_lower)
            if match:
                try:
                    poids_str = match.group(1).replace(',', '.')
                    nouveau_poids = float(poids_str)
                    if 1 <= nouveau_poids <= 100:
                        changements['poids'] = nouveau_poids
                        logger.info(f"    ✓ Poids détecté: {nouveau_poids}%")
                        break
                except (ValueError, IndexError):
                    continue
        
        # ==========================================
        # 2. EXTRAIRE LA DESCRIPTION (AMÉLIORÉ)
        # ==========================================
        desc_patterns = [
            # "avec comme description X"
            r"avec\s+comme\s+description\s+(.+?)(?=\s*(?:et\s|,\s*et\s|$))",
            # "description : X" ou "description = X"
            r"description\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|résultat|et\s|$))",
            # "avec la description X"
            r"avec\s+(?:la\s+)?description\s+(.+?)(?=\s*(?:poids|résultat|et\s|$))",
            # "devient X" ou "sera X"
            r"(?:devient|sera|modifier\s+(?:en|par))\s*[:=]?\s*[\"']?(.{10,}?)(?=\s*(?:poids|résultat|et\s|$))",
            # "objectif N: X" (description directe après deux-points)
            r":\s*(.{15,}?)(?=\s*(?:poids|résultat|et\s|$))",
        ]
        
        for pattern_idx, pattern in enumerate(desc_patterns, 1):
            match = re.search(pattern, segment_lower, re.DOTALL | re.IGNORECASE)
            if match:
                nouvelle_desc = match.group(1).strip()
                # Nettoyer les caractères de ponctuation en fin
                nouvelle_desc = nouvelle_desc.rstrip('"\',.:;')
                
                logger.info(f"    🔍 Pattern {pattern_idx} match: '{nouvelle_desc[:80]}'")
                
                # Validation : au moins 5 caractères
                if len(nouvelle_desc) >= 5:
                    # Récupérer avec la casse originale
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouvelle_desc_original = segment[start_pos:end_pos].strip().rstrip('"\',.:;')
                    
                    changements['objectif'] = nouvelle_desc_original
                    logger.info(f"    ✓ Description détectée: '{nouvelle_desc_original[:80]}'")
                    break
        
        # ==========================================
        # 3. EXTRAIRE LE RÉSULTAT (inchangé)
        # ==========================================
        result_patterns = [
            r"résultat\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|objectif|et\s|$))",
            r"avec\s+(?:le\s+)?résultat\s+(.+?)(?=\s*(?:poids|objectif|et\s|$))",
            r"indicateur\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|objectif|et\s|$))",
        ]
        
        for pattern in result_patterns:
            match = re.search(pattern, segment_lower, re.DOTALL)
            if match:
                nouveau_resultat = match.group(1).strip().rstrip('"\',.:;')
                if len(nouveau_resultat) >= 10:
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouveau_resultat_original = segment[start_pos:end_pos].strip().rstrip('"\',.:;')
                    changements['resultat'] = nouveau_resultat_original
                    logger.info(f"    ✓ Résultat détecté: '{nouveau_resultat_original[:80]}'")
                    break
        
        if not changements:
            logger.warning(f"    ⚠️ Aucun changement détecté dans ce segment")
        
        return changements
    
    def _extraire_numero_objectif_segment(self, segment: str) -> Optional[int]:
        """Extrait le numéro d'objectif dans un segment de texte"""
        
        patterns = [
            r"objectif\s+(?:numéro\s+|n°\s+|#)?(\d+)",
            r"(?:l'|le\s+)?objectif\s+(\d+)",
            r"obj\s+(\d+)",
            r"(?:le|l')\s+(\d+)(?:ème|eme|er)?",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, segment.lower())
            if match:
                return int(match.group(1))
        
        return None
    
    def _extraire_modifications_segment(
        self,
        segment: str,
        numero: int,
        objectifs_list: List[Dict]
    ) -> Dict[str, Any]:
        """Extrait les modifications d'un segment pour un objectif spécifique"""
        
        changements = {}
        segment_lower = segment.lower()
        
        # Trouver l'objectif actuel
        objectif_actuel = None
        for obj in objectifs_list:
            if obj['numero'] == numero:
                objectif_actuel = obj
                break
        
        if not objectif_actuel:
            return {}
        
        # ==========================================
        # 1. EXTRAIRE LE POIDS
        # ==========================================
        poids_patterns = [
            r"(?:poids|pondération)\s+(?:à|de|en|par|:|=)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"(?:à|de|en|par|avec)\s+(\d+(?:[.,]\d+)?)\s*%",
            r"(\d+(?:[.,]\d+)?)\s*%",
        ]
        
        for pattern in poids_patterns:
            match = re.search(pattern, segment_lower)
            if match:
                try:
                    poids_str = match.group(1).replace(',', '.')
                    nouveau_poids = float(poids_str)
                    if 1 <= nouveau_poids <= 100:
                        changements['poids'] = nouveau_poids
                        break
                except (ValueError, IndexError):
                    continue
        
        # ==========================================
        # 2. EXTRAIRE LA DESCRIPTION
        # ==========================================
        desc_patterns = [
            r"description\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|résultat|$))",
            r"(?:devient|sera)\s*[:=]?\s*[\"']?(.{15,}?)(?=\s*(?:poids|résultat|et\s|,|$))",
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, segment_lower, re.DOTALL)
            if match:
                nouvelle_desc = match.group(1).strip().strip('"\',.:;')
                if len(nouvelle_desc) >= 10:
                    # Récupérer avec casse originale
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouvelle_desc_original = segment[start_pos:end_pos].strip().strip('"\',.:;')
                    changements['objectif'] = nouvelle_desc_original
                    break
        
        # ==========================================
        # 3. EXTRAIRE LE RÉSULTAT
        # ==========================================
        result_patterns = [
            r"résultat\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|objectif|$))",
            r"indicateur\s*[:=]\s*[\"']?(.+?)(?=\s*(?:poids|objectif|$))",
        ]
        
        for pattern in result_patterns:
            match = re.search(pattern, segment_lower, re.DOTALL)
            if match:
                nouveau_resultat = match.group(1).strip().strip('"\',.:;')
                if len(nouveau_resultat) >= 10:
                    # Récupérer avec casse originale
                    start_pos = match.start(1)
                    end_pos = match.end(1)
                    nouveau_resultat_original = segment[start_pos:end_pos].strip().strip('"\',.:;')
                    changements['resultat'] = nouveau_resultat_original
                    break
        
        return changements
# ==================== ACTIONS DE SUPPRESSION D'OBJECTIFS ====================

class ActionSupprimerObjectif(Action):
    """
    Supprime UN SEUL objectif spécifique
    Exemples : "supprime l'objectif 2", "retire le premier objectif"
    """
    
    def name(self) -> Text:
        return "action_supprimer_objectif"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        if not objectifs_list:
            dispatcher.utter_message(
                text="❌ **Aucun objectif à supprimer.**\n\nLa liste est déjà vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION D'UN SEUL OBJECTIF")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Objectifs actuels: {len(objectifs_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE LE NUMÉRO
        # ==========================================
        numero_a_supprimer = self._extraire_numero_simple(user_message)
        
        if not numero_a_supprimer:
            dispatcher.utter_message(
                text="❓ **Quel objectif souhaitez-vous supprimer ?**\n\n"
                     f"📋 **Objectifs disponibles :**\n" +
                     "\n".join([
                         f"  • **Objectif {obj['numero']}** : {obj['objectif'][:60]}... ({obj['poids']}%)"
                         for obj in objectifs_list
                     ]) +
                     "\n\n💡 **Exemple :** *'Supprime l'objectif 2'*"
            )
            return []
        
        logger.info(f"🎯 Numéro à supprimer: {numero_a_supprimer}")
        
        # ==========================================
        # ÉTAPE 2 : VÉRIFIER L'EXISTENCE
        # ==========================================
        objectif_trouve = None
        index_objectif = None
        
        for i, obj in enumerate(objectifs_list):
            if obj['numero'] == numero_a_supprimer:
                objectif_trouve = obj
                index_objectif = i
                break
        
        if not objectif_trouve:
            numeros_existants = [obj['numero'] for obj in objectifs_list]
            dispatcher.utter_message(
                text=f"❌ **L'objectif {numero_a_supprimer} n'existe pas.**\n\n"
                     f"📋 Objectifs disponibles : {', '.join([str(n) for n in sorted(numeros_existants)])}"
            )
            return []
        
        # ==========================================
        # ÉTAPE 3 : SUPPRIMER
        # ==========================================
        objectifs_list.pop(index_objectif)
        
        # ==========================================
        # ÉTAPE 4 : RENUMÉROTER
        # ==========================================
        for i, obj in enumerate(objectifs_list, 1):
            obj['numero'] = i
        
        logger.info(f"✅ Objectif {numero_a_supprimer} supprimé")
        logger.info(f"📊 Objectifs restants: {len(objectifs_list)}")
        
        # ==========================================
        # ÉTAPE 5 : CALCULER LA SOMME
        # ==========================================
        somme_poids = sum(obj['poids'] for obj in objectifs_list) if objectifs_list else 0
        
        # ==========================================
        # ÉTAPE 6 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Objectif {numero_a_supprimer} supprimé avec succès !**\n\n"
        message += f"{'─' * 50}\n\n"
        
        # Détails de l'objectif supprimé
        message += "**🗑️ Objectif supprimé :**\n\n"
        message += (
            f"  ❌ **{objectif_trouve['objectif'][:80]}**\n"
            f"  📊 Poids : {objectif_trouve['poids']}%\n"
            f"  📈 Résultat : {objectif_trouve['resultat'][:60]}...\n\n"
        )
        
        message += f"{'─' * 50}\n\n"
        
        # État actuel
        if objectifs_list:
            message += f"**📋 Objectifs restants : {len(objectifs_list)}**\n\n"
            
            for obj in objectifs_list:
                message += (
                    f"  • **Objectif {obj['numero']}** : {obj['objectif'][:60]}...\n"
                    f"    📊 Poids : {obj['poids']}%\n\n"
                )
            
            message += f"{'─' * 50}\n\n"
            message += f"📊 **Somme des poids : {somme_poids:.0f}%**\n\n"
            
            # Validation
            if len(objectifs_list) < 3:
                message += (
                    f"⚠️ **Attention : Il reste {len(objectifs_list)} objectif(s)**\n"
                    f"Le minimum requis est de **3 objectifs**.\n\n"
                    f"📝 Veuillez ajouter {3 - len(objectifs_list)} objectif(s)."
                )
            elif abs(somme_poids - 100) > 0.1:
                message += (
                    f"⚠️ **Somme des poids ≠ 100%**\n"
                    f"Différence : **{100 - somme_poids:+.0f}%**\n\n"
                    f"💡 Ajustez les poids ou ajoutez des objectifs."
                )
            else:
                message += "✅ La somme des poids est correcte (100%) !"
        else:
            message += (
                "⚠️ **Tous les objectifs ont été supprimés.**\n\n"
                "📝 Veuillez créer au moins **3 objectifs**."
            )
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 7 : METTRE À JOUR LES SLOTS
        # ==========================================
        is_complet = (
            len(objectifs_list) >= 3 and 
            abs(somme_poids - 100) < 0.1
        ) if objectifs_list else False
        
        return [
            SlotSet("objectifs_list", objectifs_list),
            SlotSet("is_complet_objectifs", is_complet),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    
    def _extraire_numero_simple(self, message: str) -> Optional[int]:
        """Extrait UN SEUL numéro d'objectif"""
        
        # Pattern 1 : Numéros explicites
        patterns = [
            r"objectif\s+(?:numéro\s+|n°\s+|#)?(\d+)",
            r"(?:l'|le\s+)?objectif\s+(\d+)",
            r"obj\s+(\d+)",
            r"(?:le|l')\s+(\d+)(?:ème|eme|er)?",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        
        # Pattern 2 : Ordinaux
        ordinaux = {
            'premier': 1, 'première': 1, '1er': 1, '1ère': 1, '1ere': 1,
            'deuxième': 2, 'deuxieme': 2, 'second': 2, 'seconde': 2, '2ème': 2, '2eme': 2, '2e': 2,
            'troisième': 3, 'troisieme': 3, '3ème': 3, '3eme': 3, '3e': 3,
            'quatrième': 4, 'quatrieme': 4, '4ème': 4, '4eme': 4, '4e': 4,
            'cinquième': 5, 'cinquieme': 5, '5ème': 5, '5eme': 5, '5e': 5,
        }
        
        for ordinal, numero in ordinaux.items():
            if ordinal in message.lower():
                return numero
        
        return None


class ActionSupprimerObjectifsMultiples(Action):
    """
    Supprime PLUSIEURS objectifs spécifiques
    Exemples : "supprime les objectifs 1 et 3", "retire du 2 au 4"
    """
    
    def name(self) -> Text:
        return "action_supprimer_objectifs_multiples"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        if not objectifs_list:
            dispatcher.utter_message(
                text="❌ **Aucun objectif à supprimer.**\n\nLa liste est déjà vide."
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE PLUSIEURS OBJECTIFS")
        logger.info(f"📋 Message: '{user_message}'")
        logger.info(f"📊 Objectifs actuels: {len(objectifs_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 1 : EXTRAIRE TOUS LES NUMÉROS
        # ==========================================
        numeros_a_supprimer = self._extraire_numeros_multiples(user_message, objectifs_list)
        
        if not numeros_a_supprimer or len(numeros_a_supprimer) < 2:
            dispatcher.utter_message(
                text="❓ **Quels objectifs souhaitez-vous supprimer ?**\n\n"
                     f"📋 **Objectifs disponibles :**\n" +
                     "\n".join([
                         f"  • **Objectif {obj['numero']}** : {obj['objectif'][:60]}... ({obj['poids']}%)"
                         for obj in objectifs_list
                     ]) +
                     "\n\n💡 **Exemples :**\n"
                     "  • *'Supprime les objectifs 1 et 3'*\n"
                     "  • *'Retire du 2 au 4'*\n"
                     "  • *'Efface les objectifs 2, 3 et 5'*"
            )
            return []
        
        logger.info(f"🎯 Numéros à supprimer: {numeros_a_supprimer}")
        
        # ==========================================
        # ÉTAPE 2 : VÉRIFIER LA VALIDITÉ
        # ==========================================
        numeros_existants = {obj['numero'] for obj in objectifs_list}
        numeros_valides = [n for n in numeros_a_supprimer if n in numeros_existants]
        numeros_invalides = [n for n in numeros_a_supprimer if n not in numeros_existants]
        
        if not numeros_valides:
            dispatcher.utter_message(
                text=f"❌ **Aucun des objectifs mentionnés n'existe.**\n\n"
                     f"📋 Disponibles : {', '.join([str(n) for n in sorted(numeros_existants)])}\n"
                     f"❌ Invalides : {', '.join([str(n) for n in numeros_invalides])}"
            )
            return []
        
        # ==========================================
        # ÉTAPE 3 : SAUVEGARDER LES SUPPRIMÉS
        # ==========================================
        objectifs_supprimes = [
            obj for obj in objectifs_list 
            if obj['numero'] in numeros_valides
        ]
        
        logger.info(f"📋 {len(objectifs_supprimes)} objectif(s) à supprimer:")
        for obj in objectifs_supprimes:
            logger.info(f"  • Objectif {obj['numero']}: {obj['objectif'][:60]}...")
        
        # ==========================================
        # ÉTAPE 4 : SUPPRIMER
        # ==========================================
        objectifs_list = [
            obj for obj in objectifs_list 
            if obj['numero'] not in numeros_valides
        ]
        
        # ==========================================
        # ÉTAPE 5 : RENUMÉROTER
        # ==========================================
        for i, obj in enumerate(objectifs_list, 1):
            obj['numero'] = i
        
        logger.info(f"✅ Objectifs restants: {len(objectifs_list)}")
        
        # ==========================================
        # ÉTAPE 6 : CALCULER LA SOMME
        # ==========================================
        somme_poids = sum(obj['poids'] for obj in objectifs_list) if objectifs_list else 0
        
        # ==========================================
        # ÉTAPE 7 : MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **{len(objectifs_supprimes)} objectifs supprimés !**\n\n"
        
        if numeros_invalides:
            message += (
                f"⚠️ **Numéros ignorés** (inexistants) : "
                f"{', '.join([str(n) for n in sorted(numeros_invalides)])}\n\n"
            )
        
        message += f"{'─' * 50}\n\n"
        
        # Détails des supprimés
        message += "**🗑️ Objectifs supprimés :**\n\n"
        for obj in objectifs_supprimes:
            message += (
                f"  ❌ **Objectif {obj['numero']}** ({obj['poids']}%)\n"
                f"     {obj['objectif'][:80]}...\n\n"
            )
        
        message += f"{'─' * 50}\n\n"
        
        # État actuel
        if objectifs_list:
            message += f"**📋 Objectifs restants : {len(objectifs_list)}**\n\n"
            
            for obj in objectifs_list:
                message += (
                    f"  • **Objectif {obj['numero']}** : {obj['objectif'][:60]}...\n"
                    f"    📊 Poids : {obj['poids']}%\n\n"
                )
            
            message += f"{'─' * 50}\n\n"
            message += f"📊 **Somme des poids : {somme_poids:.0f}%**\n\n"
            
            # Validation
            if len(objectifs_list) < 3:
                message += (
                    f"⚠️ **Attention : Il reste {len(objectifs_list)} objectif(s)**\n"
                    f"Minimum requis : **3 objectifs**\n\n"
                    f"📝 Ajoutez {3 - len(objectifs_list)} objectif(s)."
                )
            elif abs(somme_poids - 100) > 0.1:
                message += (
                    f"⚠️ **Somme ≠ 100%**\n"
                    f"Différence : **{100 - somme_poids:+.0f}%**\n\n"
                    f"💡 Ajustez les poids."
                )
            else:
                message += "✅ Somme correcte (100%) !"
        else:
            message += (
                "⚠️ **Tous les objectifs supprimés.**\n\n"
                "📝 Créez au moins **3 objectifs**."
            )
        
        dispatcher.utter_message(text=message)
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # ÉTAPE 8 : METTRE À JOUR LES SLOTS
        # ==========================================
        is_complet = (
            len(objectifs_list) >= 3 and 
            abs(somme_poids - 100) < 0.1
        ) if objectifs_list else False
        
        return [
            SlotSet("objectifs_list", objectifs_list),
            SlotSet("is_complet_objectifs", is_complet),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
    def _extraire_numeros_multiples(self, message: str, objectifs_list: List[Dict]) -> List[int]:
        """Extrait PLUSIEURS numéros (minimum 2)"""
        
        numeros = []
        message_lower = message.lower()
        
        logger.info(f"🔍 Extraction de plusieurs numéros...")
        logger.info(f"📋 Message: '{message_lower}'")
        
        # ==========================================
        # PATTERN 1 : NUMÉROS EXPLICITES (AMÉLIORÉ)
        # ==========================================
        patterns_numero = [
            # ✅ NOUVEAU : Gère "l'objectif" avec apostrophe collée
            r"l'objectif\s+(\d+)",
            # Patterns existants
            r"objectif\s+(?:numéro\s+|n°\s+|#)?(\d+)",
            r"(?:le\s+)?objectif\s+(\d+)",
            r"obj\s+(\d+)",
            # ✅ NOUVEAU : Juste le mot "objectif" suivi d'un chiffre
            r"objectif\s*(\d+)",
        ]
        
        for pattern_idx, pattern in enumerate(patterns_numero, 1):
            matches = list(re.finditer(pattern, message_lower))
            if matches:
                logger.info(f"  Pattern {pattern_idx} ('{pattern}') → {len(matches)} match(es)")
            
            for match in matches:
                numero = int(match.group(1))
                if numero not in numeros and 1 <= numero <= 20:
                    numeros.append(numero)
                    logger.info(f"    ✓ Numéro trouvé: {numero}")
        
        # ==========================================
        # PATTERN 2 : PLAGES (AMÉLIORÉ)
        # ==========================================
        plage_patterns = [
            # Patterns existants
            r"(?:du|de\s+l'objectif|de\s+l')\s+(\d+)\s+(?:au|à\s+l'objectif|à\s+l')\s+(\d+)",
            r"entre\s+(?:l'objectif\s+)?(\d+)\s+et\s+(?:l'objectif\s+)?(\d+)",
            r"objectifs?\s+(\d+)\s+[àa]\s+(\d+)",
            # ✅ NOUVEAU : "du 2 au 4", "de 1 à 3"
            r"(?:du|de)\s+(\d+)\s+(?:au|[àa])\s+(\d+)",
        ]
        
        for pattern in plage_patterns:
            match = re.search(pattern, message_lower)
            if match:
                debut = int(match.group(1))
                fin = int(match.group(2))
                logger.info(f"  ✓ Plage détectée: {debut} à {fin}")
                
                # Valider la plage
                if debut > fin:
                    debut, fin = fin, debut  # Inverser si nécessaire
                
                if 1 <= debut <= 20 and 1 <= fin <= 20 and (fin - debut) <= 10:
                    for numero in range(debut, fin + 1):
                        if numero not in numeros:
                            numeros.append(numero)
                            logger.info(f"    ✓ Ajouté: {numero}")
        
        # ==========================================
        # PATTERN 3 : "ET" SÉPARATEUR (NOUVEAU)
        # ==========================================
        # Gère "objectif 2 et 3", "le 1 et 4", "2 et 3"
        pattern_et = r"(?:l'objectif\s+|le\s+|objectif\s+)?(\d+)\s+et\s+(?:l'objectif\s+|le\s+)?(\d+)"
        matches_et = list(re.finditer(pattern_et, message_lower))
        
        if matches_et:
            logger.info(f"  Pattern 'ET' → {len(matches_et)} match(es)")
            
            for match in matches_et:
                num1 = int(match.group(1))
                num2 = int(match.group(2))
                
                for numero in [num1, num2]:
                    if numero not in numeros and 1 <= numero <= 20:
                        numeros.append(numero)
                        logger.info(f"    ✓ Numéro trouvé: {numero}")
        
        # ==========================================
        # PATTERN 4 : LISTE AVEC VIRGULES (NOUVEAU)
        # ==========================================
        # Gère "objectifs 1, 2 et 3", "les 2, 3, 4"
        pattern_liste = r"(?:objectifs?\s+)?(\d+)(?:\s*,\s*(\d+))*(?:\s+et\s+(\d+))?"
        match_liste = re.search(pattern_liste, message_lower)
        
        if match_liste:
            for group in match_liste.groups():
                if group and group.isdigit():
                    numero = int(group)
                    if numero not in numeros and 1 <= numero <= 20:
                        numeros.append(numero)
                        logger.info(f"  ✓ Liste: {numero}")
        
        # ==========================================
        # PATTERN 5 : NOMBRES ISOLÉS (FALLBACK)
        # ==========================================
        # ✅ CORRECTION : Activer même si on a déjà des numéros
        # pour capturer "supprimer l'objectif 2 et 3" où "3" est isolé
        if len(numeros) < 2:
            logger.info("  🔍 Recherche de nombres isolés (fallback)...")
            nombres_isoles = re.findall(r'\b(\d+)\b', message_lower)
            
            for n in nombres_isoles:
                numero = int(n)
                if numero not in numeros and 1 <= numero <= 10:
                    numeros.append(numero)
                    logger.info(f"    ✓ Isolé: {numero}")
        
        # ==========================================
        # TRI ET VALIDATION FINALE
        # ==========================================
        numeros = sorted(set(numeros))  # Éliminer doublons et trier
        
        logger.info(f"\n📊 RÉSULTAT FINAL: {len(numeros)} numéro(s)")
        if numeros:
            logger.info(f"   → Numéros: {numeros}")
        else:
            logger.warning("   ⚠️ AUCUN numéro détecté")
        
        return numeros


class ActionSupprimerTousObjectifs(Action):
    """
    Supprime TOUS les objectifs avec confirmation
    Exemples : "supprime tout", "efface tous les objectifs"
    """
    
    def name(self) -> Text:
        return "action_supprimer_tous_objectifs"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        objectifs_list = tracker.get_slot("objectifs_list") or []
        
        if not objectifs_list:
            dispatcher.utter_message(
                text="ℹ️ **La liste des objectifs est déjà vide.**"
            )
            return []
        
        user_message = tracker.latest_message.get('text', '').lower()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🗑️ SUPPRESSION DE TOUS LES OBJECTIFS")
        logger.info(f"📊 Objectifs actuels: {len(objectifs_list)}")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # VÉRIFICATION : CONFIRMATION EXPLICITE
        # ==========================================
        patterns_confirmation = [
            r"\btous\s+les\s+objectifs?\b",
            r"\btout\b",
            r"\btoutes?\b",
            r"\bl'ensemble\b",
            r"\btotalité\b",
            r"\breset\b",
            r"\bremettre\s+[àa]\s+zéro\b",
        ]
        
        confirmation_explicite = any(
            re.search(pattern, user_message) 
            for pattern in patterns_confirmation
        )
        
        if not confirmation_explicite:
            logger.warning("⚠️ Aucune confirmation explicite")
            dispatcher.utter_message(
                text=f"⚠️ **Êtes-vous sûr(e) de vouloir supprimer TOUS les objectifs ?**\n\n"
                     f"📊 **{len(objectifs_list)} objectif(s) seront définitivement supprimés.**\n\n"
                     f"📋 **Objectifs concernés :**\n" +
                     "\n".join([
                         f"  • **Objectif {obj['numero']}** ({obj['poids']}%)"
                         for obj in objectifs_list
                     ]) +
                     f"\n\n💡 **Pour confirmer, répondez :**\n"
                     f"[Oui supprime tout, Annuler la suppression](action_supprimer_tous_objectifs)"
            )
            return []
        
        # ==========================================
        # SAUVEGARDER POUR LE MESSAGE
        # ==========================================
        nb_objectifs = len(objectifs_list)
        somme_poids_avant = sum(obj['poids'] for obj in objectifs_list)
        objectifs_supprimes = objectifs_list.copy()
        
        logger.info(f"🗑️ Suppression de {nb_objectifs} objectif(s)")
        
        # ==========================================
        # SUPPRESSION TOTALE
        # ==========================================
        objectifs_list = []
        
        # ==========================================
        # MESSAGE DE CONFIRMATION
        # ==========================================
        message = f"✅ **Tous les objectifs ont été supprimés !**\n\n"
        message += f"{'─' * 50}\n\n"
        message += f"**🗑️ {nb_objectifs} objectif(s) supprimé(s)**\n"
        message += f"**📊 Somme avant suppression : {somme_poids_avant:.0f}%**\n\n"
        message += f"{'─' * 50}\n\n"
        
        # Détails
        message += "**Détail des objectifs supprimés :**\n\n"
        for obj in objectifs_supprimes:
            message += (
                f"  ❌ **Objectif {obj['numero']}** ({obj['poids']}%)\n"
                f"     {obj['objectif'][:80]}...\n\n"
            )
        
        message += f"{'─' * 50}\n\n"
        message += (
            "⚠️ **La liste est maintenant vide.**\n\n"
            "📝 Veuillez créer au moins **3 nouveaux objectifs**.\n\n"
            "💡 **Format attendu :**\n"
            "Objectif 1 : [Description]\n"
            "Poids : [XX]%\n"
            "Indicateurs : [Résultats attendus]"
        )
        
        dispatcher.utter_message(text=message)
        
        logger.info(f"✅ Tous les objectifs supprimés")
        logger.info(f"{'='*80}\n")
        
        # ==========================================
        # METTRE À JOUR LES SLOTS
        # ==========================================
        return [
            SlotSet("objectifs_list", []),
            SlotSet("is_complet_objectifs", False),
            SlotSet("objectif", None),
            SlotSet("poids", None),
            SlotSet("resultat_attendu", None),
            FollowupAction("verify_if_all_information_is_complet_add_ddr")
        ]
