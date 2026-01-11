"""
Service de recherche intelligente de flux avec gestion des imports et filtrage par type
"""

import sys
from pathlib import Path
import unicodedata
from typing import Optional, Dict, List, Union
from rapidfuzz import fuzz, process

# Ajouter le répertoire racine du projet au PYTHONPATH
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent  # Remonte à Rasa4/
sys.path.insert(0, str(project_root))

from actions.services.ddr_service import get_backend_service

class FluxSearchService:
    """
    Service de recherche intelligente de flux avec tolérance aux fautes,
    insensibilité à la casse et aux accents, et filtrage par type
    """
    
    def __init__(self, default_threshold: int = 60, default_limit: int = 5):
        """
        Initialise le service de recherche de flux
        
        Args:
            default_threshold (int): Seuil de correspondance par défaut (0-100)
            default_limit (int): Nombre maximum de résultats par défaut
        """
        self.backend_service = get_backend_service()
        self.default_threshold = default_threshold
        self.default_limit = default_limit
        self._flux_cache = None
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalise le texte en retirant les accents et en convertissant en minuscules
        
        Args:
            text (str): Texte à normaliser
            
        Returns:
            str: Texte normalisé
        """
        text = text.lower().strip()
        text = ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
        return text
    
    def refresh_cache(self) -> None:
        """Rafraîchit le cache des flux"""
        self._flux_cache = None
    
    def get_all_flux(self, use_cache: bool = True) -> List[Dict]:
        """
        Récupère tous les flux disponibles avec les détails des utilisateurs
        
        Args:
            use_cache (bool): Utiliser le cache si disponible
            
        Returns:
            List[Dict]: Liste de tous les flux avec les noms des validateurs
        """
        try:
            if use_cache and self._flux_cache is not None:
                return self._flux_cache
            
            # Utiliser le nouvel endpoint avec les détails des utilisateurs
            flux_list = self.backend_service.get_flux_mouvements_with_details()
            self._flux_cache = flux_list
            print(f"📋 {len(flux_list)} flux récupérés avec détails utilisateurs")
            return flux_list
            
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des flux: {e}")
            return []
    
    def _filter_by_typeflux(self, flux_list: List[Dict], typeflux: Optional[str]) -> List[Dict]:
        """
        Filtre une liste de flux par TypeFlux
        
        Args:
            flux_list (List[Dict]): Liste des flux à filtrer
            typeflux (str, optional): Type de flux à filtrer (ex: "Engagement", "Liquidation")
            
        Returns:
            List[Dict]: Liste filtrée des flux
        """
        if not typeflux:
            return flux_list
        
        typeflux_normalized = self.normalize_text(typeflux)
        filtered = []
        
        for flux in flux_list:
            flux_type = flux.get('TypeFlux', '')
            if flux_type:
                flux_type_normalized = self.normalize_text(str(flux_type))
                if typeflux_normalized in flux_type_normalized or flux_type_normalized == typeflux_normalized:
                    filtered.append(flux)
        
        if filtered:
            print(f"🔍 Filtre TypeFlux '{typeflux}': {len(filtered)}/{len(flux_list)} flux correspondent")
        else:
            print(f"⚠️ Aucun flux ne correspond au TypeFlux '{typeflux}'")
        
        return filtered
    
    def search_by_name(
        self, 
        nom_flux: str, 
        threshold: Optional[int] = None, 
        limit: Optional[int] = None,
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche intelligente de flux par nom
        
        Args:
            nom_flux (str): Le nom du flux à rechercher
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: 
                - Dict unique si correspondance exacte
                - List[Dict] si correspondances partielles
                - None si aucune correspondance
        """
        threshold = threshold or self.default_threshold
        limit = limit or self.default_limit
        
        try:
            all_flux = self.get_all_flux()
            
            if not all_flux:
                print("⚠️ Aucun flux disponible dans la base de données")
                return None
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            if not all_flux:
                return None
            
            print(f"🔍 Recherche intelligente pour: '{nom_flux}'")
            print(f"📊 Total flux dans la base: {len(all_flux)}")
            
            flux_names = [f.get('NomFluxMouvement', '') for f in all_flux if f.get('NomFluxMouvement')]
            
            if not flux_names:
                print("⚠️ Aucun flux avec un nom valide trouvé")
                return None
            
            nom_flux_normalized = self.normalize_text(nom_flux)
            
            # 1. Vérifier correspondance exacte
            exact_match = self._find_exact_match(all_flux, nom_flux_normalized)
            if exact_match:
                return exact_match
            
            # 2. Recherche par sous-chaîne et floue
            matching_flux = self._fuzzy_search(
                all_flux, 
                flux_names, 
                nom_flux_normalized, 
                threshold, 
                limit
            )
            
            return self._process_results(matching_flux, limit)
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche du flux '{nom_flux}': {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_exact_match(self, all_flux: List[Dict], nom_normalized: str) -> Optional[Dict]:
        """Recherche une correspondance exacte"""
        for flux in all_flux:
            flux_name_normalized = self.normalize_text(flux.get('NomFluxMouvement', ''))
            if flux_name_normalized == nom_normalized:
                print(f"✅ Correspondance exacte trouvée: {flux.get('NomFluxMouvement')}")
                return flux
        return None
    
    def _fuzzy_search(
        self, 
        all_flux: List[Dict], 
        flux_names: List[str],
        nom_normalized: str, 
        threshold: int, 
        limit: int
    ) -> List[Dict]:
        """Effectue une recherche floue et par sous-chaîne"""
        substring_matches = []
        
        # Recherche par sous-chaîne
        for flux in all_flux:
            flux_name = flux.get('NomFluxMouvement', '')
            flux_name_normalized = self.normalize_text(flux_name)
            
            if nom_normalized in flux_name_normalized:
                substring_matches.append({
                    'flux': flux,
                    'match_score': 100,
                    'matched_name': flux_name
                })
        
        # Recherche floue
        normalized_names = [self.normalize_text(name) for name in flux_names]
        fuzzy_matches = process.extract(
            nom_normalized,
            normalized_names,
            scorer=fuzz.partial_ratio,
            limit=limit * 2
        )
        
        for match in fuzzy_matches:
            matched_normalized = match[0]
            score = match[1]
            
            if score >= threshold:
                try:
                    idx = normalized_names.index(matched_normalized)
                    flux_detail = all_flux[idx]
                    
                    if not any(m['flux'].get('NomFluxMouvement') == flux_detail.get('NomFluxMouvement') 
                              for m in substring_matches):
                        substring_matches.append({
                            'flux': flux_detail,
                            'match_score': score,
                            'matched_name': flux_detail.get('NomFluxMouvement')
                        })
                except (ValueError, IndexError):
                    continue
        
        return sorted(substring_matches, key=lambda x: x['match_score'], reverse=True)
    
    def _process_results(self, matching_flux: List[Dict], limit: int) -> Union[Dict, List[Dict], None]:
        """Traite et retourne les résultats selon leur score"""
        if not matching_flux:
            print(f"❌ Aucun flux trouvé avec un score >= {self.default_threshold}%")
            return None
        
        top_score = matching_flux[0]['match_score']
        
        # Correspondance perfaite unique
        if top_score == 100:
            perfect_matches = [m for m in matching_flux if m['match_score'] == 100]
            
            if len(perfect_matches) == 1:
                print(f"✅ Correspondance perfaite trouvée avec score {top_score}%")
                return perfect_matches[0]['flux']
            else:
                print(f"📋 {len(perfect_matches)} flux avec correspondance perfaite trouvés:")
                for idx, match in enumerate(perfect_matches, 1):
                    print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
                return perfect_matches
        
        # Score très élevé avec différence significative
        if top_score >= 95 and len(matching_flux) > 1:
            second_score = matching_flux[1]['match_score']
            if top_score - second_score >= 10:
                print(f"✅ Un flux clairement plus pertinent trouvé avec score {top_score}%")
                return matching_flux[0]['flux']
        
        # Limiter aux meilleurs résultats
        matching_flux = matching_flux[:limit]
        
        if len(matching_flux) == 1:
            print(f"✅ Un seul flux trouvé avec score {matching_flux[0]['match_score']}%")
            return matching_flux[0]['flux']
        
        print(f"📋 {len(matching_flux)} flux trouvés:")
        for idx, match in enumerate(matching_flux, 1):
            print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
        
        return matching_flux
    
    def search_by_id(self, flux_id: int, typeflux: Optional[str] = None) -> Optional[Dict]:
        """
        Recherche un flux par son ID
        
        Args:
            flux_id (int): L'identifiant du flux
            typeflux (str, optional): Type de flux pour filtrer
            
        Returns:
            Optional[Dict]: Les données du flux si trouvé
        """
        try:
            all_flux = self.get_all_flux()
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            for flux in all_flux:
                if flux.get('IdFlux') == flux_id:
                    print(f"✅ Flux trouvé: {flux.get('NomFluxMouvement')}")
                    return flux
            
            print(f"❌ Aucun flux trouvé avec l'ID {flux_id}")
            return None
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche du flux ID {flux_id}: {e}")
            return None
    
    def search_by_username(
        self,
        usernames: Union[str, List[str]],
        threshold: Optional[int] = None,
        limit: Optional[int] = None,
        match_all: bool = False,
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche intelligente de flux par username(s) de validateur (V1, V2, V3, V4, V5)
        
        Args:
            usernames (Union[str, List[str]]): Un ou plusieurs usernames à rechercher
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            match_all (bool): Si True, le flux doit contenir TOUS les usernames
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: Flux trouvé(s) ou None
        """
        return self.search_by_validators(
            validators=usernames,
            threshold=threshold,
            limit=limit,
            match_all=match_all,
            search_by_name=False,
            typeflux=typeflux
        )
    
    @staticmethod
    def extract_matricule(username: str) -> Optional[str]:
        """
        Extrait le matricule (partie numérique) d'un username
        
        Args:
            username (str): Username au format 'mand700500', 'espe123456', etc.
            
        Returns:
            Optional[str]: Le matricule extrait ou None si aucun nombre trouvé
        """
        import re
        match = re.search(r'\d+', username)
        return match.group() if match else None
    
    def search_by_matricule(
        self,
        matricules: Union[str, int, List[Union[str, int]]],
        threshold: Optional[int] = None,
        limit: Optional[int] = None,
        match_all: bool = False,
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche intelligente de flux par matricule(s) de validateur
        
        Args:
            matricules (Union[str, int, List]): Un ou plusieurs matricules à rechercher
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            match_all (bool): Si True, le flux doit contenir TOUS les matricules
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: Flux trouvé(s) ou None
        """
        threshold = threshold or self.default_threshold
        limit = limit or self.default_limit
        
        # Normaliser l'entrée en liste de strings
        if isinstance(matricules, (str, int)):
            matricules = [str(matricules)]
        else:
            matricules = [str(m) for m in matricules]
        
        try:
            all_flux = self.get_all_flux()
            
            if not all_flux:
                print("⚠️ Aucun flux disponible dans la base de données")
                return None
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            if not all_flux:
                return None
            
            print(f"🔍 Recherche par matricule(s): {matricules}")
            print(f"📊 Mode: {'TOUS les matricules' if match_all else 'AU MOINS UN matricule'}")
            print(f"📊 Total flux dans la base: {len(all_flux)}")
            
            matching_flux = []
            
            for flux in all_flux:
                # Récupérer tous les usernames et extraire les matricules
                flux_matricules = []
                for i in range(1, 6):
                    v_key = f'V{i}'
                    username = flux.get(v_key)
                    
                    if username:
                        matricule = self.extract_matricule(str(username))
                        if matricule:
                            flux_matricules.append({
                                'key': v_key,
                                'username': str(username),
                                'matricule': matricule,
                                'full_name': flux.get(f'V{i}UserName', 'N/A')
                            })
                
                if not flux_matricules:
                    continue
                
                # Calculer le score de correspondance pour chaque matricule recherché
                matricule_scores = []
                matched_matricules = []
                
                for search_matricule in matricules:
                    best_score = 0
                    best_match = None
                    
                    # Vérifier les correspondances exactes
                    for fm in flux_matricules:
                        if fm['matricule'] == search_matricule:
                            best_score = 100
                            best_match = fm
                            break
                    
                    # Si pas de correspondance exacte, recherche floue
                    if best_score < 100:
                        for fm in flux_matricules:
                            if search_matricule in fm['matricule']:
                                score = 95
                            else:
                                score = fuzz.ratio(search_matricule, fm['matricule'])
                            
                            if score > best_score:
                                best_score = score
                                best_match = fm
                    
                    matricule_scores.append(best_score)
                    if best_match and best_score >= threshold:
                        matched_matricules.append({
                            'search_term': search_matricule,
                            'matched_field': best_match['key'],
                            'matched_username': best_match['username'],
                            'matched_matricule': best_match['matricule'],
                            'matched_full_name': best_match['full_name'],
                            'score': best_score
                        })
                
                # Vérifier si le flux correspond aux critères
                if match_all:
                    if all(score >= threshold for score in matricule_scores):
                        avg_score = sum(matricule_scores) / len(matricule_scores)
                        matching_flux.append({
                            'flux': flux,
                            'match_score': int(avg_score),
                            'matched_matricules': matched_matricules,
                            'matched_name': flux.get('NomFluxMouvement')
                        })
                else:
                    if any(score >= threshold for score in matricule_scores):
                        max_score = max(matricule_scores)
                        matching_flux.append({
                            'flux': flux,
                            'match_score': max_score,
                            'matched_matricules': matched_matricules,
                            'matched_name': flux.get('NomFluxMouvement')
                        })
            
            matching_flux = sorted(matching_flux, key=lambda x: x['match_score'], reverse=True)
            
            if not matching_flux:
                print(f"❌ Aucun flux trouvé avec matricule(s) correspondant (seuil: {threshold}%)")
                return None
            
            return self._process_matricule_results(matching_flux, limit)
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche par matricule(s): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _process_matricule_results(
        self, 
        matching_flux: List[Dict], 
        limit: int
    ) -> Union[Dict, List[Dict], None]:
        """Traite et retourne les résultats de recherche par matricule"""
        if not matching_flux:
            return None
        
        top_score = matching_flux[0]['match_score']
        
        if top_score == 100:
            perfect_matches = [m for m in matching_flux if m['match_score'] == 100]
            
            if len(perfect_matches) == 1:
                print(f"✅ Correspondance parfaite trouvée avec matricule(s)")
                self._print_matricule_matches(perfect_matches[0])
                return perfect_matches[0]['flux']
            else:
                print(f"📋 {len(perfect_matches)} flux avec correspondance parfaite trouvés:")
                for idx, match in enumerate(perfect_matches, 1):
                    print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
                    self._print_matricule_matches(match, indent=6)
                return perfect_matches
        
        matching_flux = matching_flux[:limit]
        
        if len(matching_flux) == 1:
            print(f"✅ Un seul flux trouvé avec score {matching_flux[0]['match_score']}%")
            self._print_matricule_matches(matching_flux[0])
            return matching_flux[0]['flux']
        
        print(f"📋 {len(matching_flux)} flux trouvés:")
        for idx, match in enumerate(matching_flux, 1):
            print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
            self._print_matricule_matches(match, indent=6)
        
        return matching_flux
    
    def _print_matricule_matches(self, match: Dict, indent: int = 3) -> None:
        """Affiche les matricules correspondants"""
        spaces = " " * indent
        for mm in match['matched_matricules']:
            print(f"{spaces}→ Matricule '{mm['search_term']}' trouvé dans {mm['matched_field']}: "
                  f"{mm['matched_username']} (matricule: {mm['matched_matricule']}, "
                  f"nom: {mm['matched_full_name']}, score: {mm['score']}%)")
    
    def search_by_ordered_validators(
        self,
        validators: List[str],
        threshold: Optional[int] = None,
        limit: Optional[int] = None,
        search_type: str = 'username',
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche intelligente de flux par validateurs dans un ordre spécifique
        
        Args:
            validators (List[str]): Liste ordonnée des validateurs à rechercher
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            search_type (str): Type de recherche - 'username', 'full_name', ou 'matricule'
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: Flux trouvé(s) ou None
        """
        threshold = threshold or self.default_threshold
        limit = limit or self.default_limit
        
        if not validators:
            print("⚠️ Liste de validateurs vide")
            return None
        
        if len(validators) > 5:
            print("⚠️ Maximum 5 validateurs (V1 à V5)")
            validators = validators[:5]
        
        try:
            all_flux = self.get_all_flux()
            
            if not all_flux:
                print("⚠️ Aucun flux disponible dans la base de données")
                return None
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            if not all_flux:
                return None
            
            validators_normalized = [self.normalize_text(str(v)) for v in validators]
            
            if search_type not in ['username', 'full_name', 'matricule']:
                print(f"⚠️ Type de recherche invalide: {search_type}. Utilisation de 'username'")
                search_type = 'username'
            
            print(f"🔍 Recherche par validateurs ORDONNÉS ({search_type}):")
            for idx, val in enumerate(validators, 1):
                print(f"   V{idx} = '{val}'")
            print(f"📊 Total flux dans la base: {len(all_flux)}")
            
            matching_flux = []
            
            for flux in all_flux:
                position_scores = []
                matched_positions = []
                
                for position, search_value in enumerate(validators_normalized, 1):
                    v_index = position
                    
                    if search_type == 'matricule':
                        username = flux.get(f'V{v_index}')
                        if not username:
                            position_scores.append(0)
                            continue
                        
                        flux_matricule = self.extract_matricule(str(username))
                        if not flux_matricule:
                            position_scores.append(0)
                            continue
                        
                        flux_value_normalized = self.normalize_text(flux_matricule)
                        display_value = f"{username} (matricule: {flux_matricule})"
                        field_key = f'V{v_index}'
                        
                    else:
                        field_key = f'V{v_index}' if search_type == 'username' else f'V{v_index}UserName'
                        flux_value = flux.get(field_key)
                        
                        if not flux_value:
                            position_scores.append(0)
                            continue
                        
                        flux_value_normalized = self.normalize_text(str(flux_value))
                        display_value = str(flux_value)
                    
                    # Calculer le score
                    if flux_value_normalized == search_value:
                        score = 100
                    elif search_value in flux_value_normalized:
                        score = 95
                    else:
                        score = fuzz.ratio(search_value, flux_value_normalized)
                    
                    position_scores.append(score)
                    
                    if score >= threshold:
                        matched_positions.append({
                            'position': v_index,
                            'search_term': validators[position - 1],
                            'matched_field': field_key,
                            'matched_value': display_value,
                            'score': score
                        })
                
                if all(score >= threshold for score in position_scores):
                    avg_score = sum(position_scores) / len(position_scores)
                    matching_flux.append({
                        'flux': flux,
                        'match_score': int(avg_score),
                        'matched_positions': matched_positions,
                        'matched_name': flux.get('NomFluxMouvement')
                    })
            
            matching_flux = sorted(matching_flux, key=lambda x: x['match_score'], reverse=True)
            
            if not matching_flux:
                print(f"❌ Aucun flux trouvé avec les validateurs dans l'ordre spécifié (seuil: {threshold}%)")
                return None
            
            return self._process_ordered_results(matching_flux, limit)
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche ordonnée: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _process_ordered_results(
        self, 
        matching_flux: List[Dict], 
        limit: int
    ) -> Union[Dict, List[Dict], None]:
        """Traite et retourne les résultats de recherche ordonnée"""
        if not matching_flux:
            return None
        
        top_score = matching_flux[0]['match_score']
        
        if top_score == 100:
            perfect_matches = [m for m in matching_flux if m['match_score'] == 100]
            
            if len(perfect_matches) == 1:
                print(f"✅ Correspondance parfaite trouvée (ordre respecté)")
                self._print_ordered_matches(perfect_matches[0])
                return perfect_matches[0]['flux']
            else:
                print(f"📋 {len(perfect_matches)} flux avec correspondance parfaite trouvés:")
                for idx, match in enumerate(perfect_matches, 1):
                    print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
                    self._print_ordered_matches(match, indent=6)
                return perfect_matches
        
        matching_flux = matching_flux[:limit]
        
        if len(matching_flux) == 1:
            print(f"✅ Un seul flux trouvé avec score {matching_flux[0]['match_score']}%")
            self._print_ordered_matches(matching_flux[0])
            return matching_flux[0]['flux']
        
        print(f"📋 {len(matching_flux)} flux trouvés:")
        for idx, match in enumerate(matching_flux, 1):
            print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
            self._print_ordered_matches(match, indent=6)
        
        return matching_flux
    
    def _print_ordered_matches(self, match: Dict, indent: int = 3) -> None:
        """Affiche les correspondances ordonnées"""
        spaces = " " * indent
        for mp in match['matched_positions']:
            print(f"{spaces}→ V{mp['position']}: '{mp['search_term']}' → "
                  f"{mp['matched_value']} (score: {mp['score']}%)")
    
    def search_by_validators(
        self,
        validators: Union[str, List[str]],
        threshold: Optional[int] = None,
        limit: Optional[int] = None,
        match_all: bool = False,
        search_by_name: bool = True,
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche intelligente de flux par validateur(s)
        
        Args:
            validators (Union[str, List[str]]): Un ou plusieurs validateurs à rechercher
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            match_all (bool): Si True, le flux doit contenir TOUS les validateurs
            search_by_name (bool): Si True, recherche dans V*UserName (noms complets)
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: Flux trouvé(s) ou None
        """
        threshold = threshold or self.default_threshold
        limit = limit or self.default_limit
        
        if isinstance(validators, str):
            validators = [validators]
        
        try:
            all_flux = self.get_all_flux()
            
            if not all_flux:
                print("⚠️ Aucun flux disponible dans la base de données")
                return None
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            if not all_flux:
                return None
            
            validators_normalized = [self.normalize_text(v) for v in validators]
            
            search_type = "noms complets (V*UserName)" if search_by_name else "usernames (V*)"
            print(f"🔍 Recherche par validateur(s) dans {search_type}: {validators}")
            print(f"📊 Mode: {'TOUS les validateurs' if match_all else 'AU MOINS UN validateur'}")
            print(f"📊 Total flux dans la base: {len(all_flux)}")
            
            matching_flux = []
            
            for flux in all_flux:
                flux_validators = []
                for i in range(1, 6):
                    v_key = f'V{i}UserName' if search_by_name else f'V{i}'
                    v_value = flux.get(v_key)
                    
                    if v_value:
                        flux_validators.append({
                            'key': v_key,
                            'value': str(v_value),
                            'normalized': self.normalize_text(str(v_value))
                        })
                
                if not flux_validators:
                    continue
                
                validator_scores = []
                matched_validators = []
                
                for search_validator in validators_normalized:
                    best_score = 0
                    best_match = None
                    
                    for fv in flux_validators:
                        if fv['normalized'] == search_validator:
                            best_score = 100
                            best_match = fv
                            break
                    
                    if best_score < 100:
                        for fv in flux_validators:
                            if search_validator in fv['normalized']:
                                score = 95
                            else:
                                score = fuzz.ratio(search_validator, fv['normalized'])
                            
                            if score > best_score:
                                best_score = score
                                best_match = fv
                    
                    validator_scores.append(best_score)
                    if best_match and best_score >= threshold:
                        matched_validators.append({
                            'search_term': validators[validators_normalized.index(search_validator)],
                            'matched_field': best_match['key'],
                            'matched_value': best_match['value'],
                            'score': best_score
                        })
                
                if match_all:
                    if all(score >= threshold for score in validator_scores):
                        avg_score = sum(validator_scores) / len(validator_scores)
                        matching_flux.append({
                            'flux': flux,
                            'match_score': int(avg_score),
                            'matched_validators': matched_validators,
                            'matched_name': flux.get('NomFluxMouvement')
                        })
                else:
                    if any(score >= threshold for score in validator_scores):
                        max_score = max(validator_scores)
                        matching_flux.append({
                            'flux': flux,
                            'match_score': max_score,
                            'matched_validators': matched_validators,
                            'matched_name': flux.get('NomFluxMouvement')
                        })
            
            matching_flux = sorted(matching_flux, key=lambda x: x['match_score'], reverse=True)
            
            if not matching_flux:
                print(f"❌ Aucun flux trouvé avec validateur(s) correspondant (seuil: {threshold}%)")
                return None
            
            return self._process_validator_results(matching_flux, limit)
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche par validateur(s): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _process_validator_results(
        self, 
        matching_flux: List[Dict], 
        limit: int
    ) -> Union[Dict, List[Dict], None]:
        """Traite et retourne les résultats de recherche par validateur"""
        if not matching_flux:
            return None
        
        top_score = matching_flux[0]['match_score']
        
        if top_score == 100:
            perfect_matches = [m for m in matching_flux if m['match_score'] == 100]
            
            if len(perfect_matches) == 1:
                print(f"✅ Correspondance parfaite trouvée avec validateur(s)")
                self._print_validator_matches(perfect_matches[0])
                return perfect_matches[0]['flux']
            else:
                print(f"📋 {len(perfect_matches)} flux avec correspondance parfaite trouvés:")
                for idx, match in enumerate(perfect_matches, 1):
                    print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
                    self._print_validator_matches(match, indent=6)
                return perfect_matches
        
        matching_flux = matching_flux[:limit]
        
        if len(matching_flux) == 1:
            print(f"✅ Un seul flux trouvé avec score {matching_flux[0]['match_score']}%")
            self._print_validator_matches(matching_flux[0])
            return matching_flux[0]['flux']
        
        print(f"📋 {len(matching_flux)} flux trouvés:")
        for idx, match in enumerate(matching_flux, 1):
            print(f"   {idx}. {match['matched_name']} (score: {match['match_score']}%)")
            self._print_validator_matches(match, indent=6)
        
        return matching_flux
    
    def _print_validator_matches(self, match: Dict, indent: int = 3) -> None:
        """Affiche les validateurs correspondants"""
        spaces = " " * indent
        for vm in match['matched_validators']:
            print(f"{spaces}→ '{vm['search_term']}' trouvé dans {vm['matched_field']}: "
                  f"{vm['matched_value']} (score: {vm['score']}%)")
    
    def format_results(self, results: Union[Dict, List[Dict], None]) -> str:
        """
        Formate les résultats de recherche pour un affichage lisible
        
        Args:
            results: Résultats de recherche
            
        Returns:
            str: Message formaté
        """
        if results is None:
            return "❌ Aucun flux trouvé correspondant à votre recherche."
        
        if isinstance(results, dict):
            if 'matched_matricules' in results:
                return self._format_flux_with_matricules(results)
            elif 'matched_validators' in results or 'matched_positions' in results:
                return self._format_flux_with_validators(results)
            elif 'flux' in results:
                flux = results['flux']
                score = results['match_score']
                return self._format_single_flux(flux, score)
            else:
                return self._format_single_flux(results)
        
        if isinstance(results, list):
            if results and 'matched_matricules' in results[0]:
                return self._format_multiple_flux_with_matricules(results)
            elif results and ('matched_validators' in results[0] or 'matched_positions' in results[0]):
                return self._format_multiple_flux_with_validators(results)
            else:
                return self._format_multiple_flux(results)
        
        return "⚠️ Format de résultat inattendu."
    
    def _format_flux_with_matricules(self, result: Dict) -> str:
        """Formate un flux avec ses matricules correspondants"""
        flux = result['flux']
        score = result['match_score']
        matched_matricules = result['matched_matricules']
        
        message = f"✅ Flux trouvé (score: {score}%):\n"
        message += f"   ID: {flux.get('IdFlux')}\n"
        message += f"   Nom: {flux.get('NomFluxMouvement')}\n"
        message += f"   Type: {flux.get('TypeFlux', 'N/A')}\n"
        message += f"   Matricules correspondants:\n"
        
        for mm in matched_matricules:
            message += f"      → Matricule '{mm['search_term']}' trouvé dans {mm['matched_field']}: "
            message += f"{mm['matched_username']} (matricule: {mm['matched_matricule']}, "
            message += f"nom: {mm['matched_full_name']}, score: {mm['score']}%)\n"
        
        return message.strip()
    
    def _format_multiple_flux_with_matricules(self, results: List[Dict]) -> str:
        """Formate plusieurs flux avec leurs matricules correspondants"""
        message = f"📋 {len(results)} flux trouvés:\n\n"
        
        for idx, result in enumerate(results, 1):
            flux = result['flux']
            score = result['match_score']
            matched_matricules = result['matched_matricules']
            
            message += f"{idx}. {flux.get('NomFluxMouvement')} (score: {score}%)\n"
            message += f"   ID: {flux.get('IdFlux')} | Type: {flux.get('TypeFlux', 'N/A')}\n"
            message += f"   Matricules correspondants:\n"
            
            for mm in matched_matricules:
                message += f"      → {mm['matched_field']}: {mm['matched_username']}\n"
            
            message += "\n"
        
        return message.strip()
    
    def _format_flux_with_validators(self, result: Dict) -> str:
        """Formate un flux avec ses validateurs correspondants"""
        flux = result['flux']
        score = result['match_score']
        
        if 'matched_positions' in result:
            matched_items = result['matched_positions']
            label = "Validateurs ordonnés correspondants"
        else:
            matched_items = result['matched_validators']
            label = "Validateurs correspondants"
        
        message = f"✅ Flux trouvé (score: {score}%):\n"
        message += f"   ID: {flux.get('IdFlux')}\n"
        message += f"   Nom: {flux.get('NomFluxMouvement')}\n"
        message += f"   Type: {flux.get('TypeFlux', 'N/A')}\n"
        message += f"   {label}:\n"
        
        if 'matched_positions' in result:
            for mp in matched_items:
                message += f"      → V{mp['position']}: {mp['matched_value']}\n"
        else:
            for vm in matched_items:
                message += f"      → {vm['matched_field']}: {vm['matched_value']}\n"
        
        return message.strip()
    
    def _format_multiple_flux_with_validators(self, results: List[Dict]) -> str:
        """Formate plusieurs flux avec leurs validateurs correspondants"""
        message = f"📋 {len(results)} flux trouvés:\n\n"
        
        for idx, result in enumerate(results, 1):
            flux = result['flux']
            score = result['match_score']
            
            message += f"{idx}. {flux.get('NomFluxMouvement')} (score: {score}%)\n"
            message += f"   ID: {flux.get('IdFlux')} | Type: {flux.get('TypeFlux', 'N/A')}\n\n"
        
        return message.strip()
    
    def _format_single_flux(self, flux: Dict, score: Optional[int] = None) -> str:
        """Formate un seul flux"""
        score_text = f" (score: {score}%)" if score else ""
        message = f"✅ Flux trouvé{score_text}:\n"
        message += f"   ID: {flux.get('IdFlux')}\n"
        message += f"   Nom: {flux.get('NomFluxMouvement')}\n"
        message += f"   Type: {flux.get('TypeFlux', 'N/A')}\n"
        
        for i in range(1, 6):
            username = flux.get(f'V{i}', 'N/A')
            full_name = flux.get(f'V{i}UserName', 'N/A')
            message += f"   V{i}: {username} ({full_name})\n"
        
        return message.strip()
    
    def _format_multiple_flux(self, results: List[Dict]) -> str:
        """Formate plusieurs flux"""
        message = f"📋 {len(results)} flux trouvés:\n\n"
        
        for idx, match in enumerate(results, 1):
            flux = match['flux']
            score = match['match_score']
            message += f"{idx}. {flux.get('NomFluxMouvement')} (score: {score}%)\n"
            message += f"   ID: {flux.get('IdFlux')} | Type: {flux.get('TypeFlux', 'N/A')}\n\n"
        
        return message.strip()
    """
    Nouvelle fonction pour recherche stricte par séquence de validateurs
    À ajouter dans la classe FluxSearchService
    """

    def _convert_fullnames_to_usernames(self, full_names: List[str]) -> List[str]:
        """
        Convertit une liste de noms complets en usernames
        Utilise UserSearchService pour chercher les utilisateurs correspondants
        
        Args:
            full_names (List[str]): Liste des noms complets
            
        Returns:
            List[str]: Liste des usernames correspondants (ou noms originaux si pas trouvés)
        """
        try:
            from actions.services.Calculate.RechercheNom import UserSearchService
            user_service = UserSearchService()
            converted = []
            
            for full_name in full_names:
                results = user_service.search_user_by_name(full_name, max_results=1)
                if results and len(results) > 0:
                    username = results[0].get('UserName')
                    if username:
                        print(f"   ✓ Conversion : '{full_name}' → '{username}'")
                        converted.append(username)
                    else:
                        print(f"   ⚠️ Pas de username pour '{full_name}'")
                        converted.append(full_name)
                else:
                    print(f"   ⚠️ Utilisateur '{full_name}' non trouvé")
                    converted.append(full_name)
            
            return converted
        except Exception as e:
            print(f"❌ Erreur lors de la conversion des noms: {e}")
            import traceback
            traceback.print_exc()
            return full_names

    def search_by_strict_validator_sequence(
        self,
        validators: List[str],
        threshold: Optional[int] = None,
        limit: Optional[int] = None,
        search_type: str = 'full_name',
        typeflux: Optional[str] = None
    ) -> Union[Dict, List[Dict], None]:
        """
        Recherche stricte par séquence de validateurs avec respect de l'ordre ET de l'absence
        
        Exemple:
        - validators = ["Manda Arolala ANDRIANINA"]
        - Trouvera : flux avec V1=Manda et V2=null
        - Ne trouvera PAS : flux avec V1=Manda et V2=Antsa (car V2 doit être vide)
        
        Args:
            validators (List[str]): Liste ordonnée des validateurs (les positions suivantes doivent être vides)
            threshold (int, optional): Seuil de correspondance (0-100)
            limit (int, optional): Nombre maximum de résultats
            search_type (str): Type de recherche - 'username', 'full_name', ou 'matricule'
            typeflux (str, optional): Type de flux pour filtrer les résultats
            
        Returns:
            Union[Dict, List[Dict], None]: Flux trouvé(s) ou None
        """
        threshold = threshold or self.default_threshold
        limit = limit or self.default_limit
        
        if not validators:
            print("⚠️ Liste de validateurs vide")
            return None
        
        if len(validators) > 5:
            print("⚠️ Maximum 5 validateurs (V1 à V5)")
            validators = validators[:5]
        
        try:
            all_flux = self.get_all_flux()
            
            if not all_flux:
                print("⚠️ Aucun flux disponible dans la base de données")
                return None
            
            # Filtrer par TypeFlux si spécifié
            all_flux = self._filter_by_typeflux(all_flux, typeflux)
            
            if not all_flux:
                return None
            
            # ⭐ CONVERSION IMPORTANTE : Si search_type='full_name', convertir les noms complets en usernames
            # Car la base de données stocke les usernames dans les champs V1, V2, etc.
            if search_type == 'full_name':
                print(f"🔄 Conversion des noms complets en usernames...")
                converted_validators = self._convert_fullnames_to_usernames(validators)
                # Utiliser 'username' pour la recherche après conversion
                search_type = 'username'
            else:
                converted_validators = validators
            
            validators_normalized = [self.normalize_text(str(v)) for v in converted_validators]
            num_validators = len(converted_validators)
            
            if search_type not in ['username', 'full_name', 'matricule']:
                print(f"⚠️ Type de recherche invalide: {search_type}. Utilisation de 'username'")
                search_type = 'username'
            
            print(f"🔍 Recherche STRICTE par séquence de validateurs ({search_type}):")
            for idx, val in enumerate(converted_validators, 1):
                print(f"   V{idx} = '{val}' (doit correspondre)")
            print(f"   V{num_validators + 1} à V5 = VIDE (obligatoire)")
            print(f"📊 Total flux dans la base: {len(all_flux)}")
            
            matching_flux = []
            
            for flux in all_flux:
                position_scores = []
                matched_positions = []
                is_valid = True
                
                # 1. Vérifier que les positions spécifiées correspondent
                for position, search_value in enumerate(validators_normalized, 1):
                    v_index = position
                    
                    if search_type == 'matricule':
                        username = flux.get(f'V{v_index}')
                        if not username:
                            is_valid = False
                            break
                        
                        flux_matricule = self.extract_matricule(str(username))
                        if not flux_matricule:
                            is_valid = False
                            break
                        
                        flux_value_normalized = self.normalize_text(flux_matricule)
                        display_value = f"{username} (matricule: {flux_matricule})"
                        field_key = f'V{v_index}'
                        
                    else:
                        # Toujours chercher dans V{v_index} (username)
                        field_key = f'V{v_index}'
                        flux_value = flux.get(field_key)
                        
                        if not flux_value:
                            is_valid = False
                            break
                        
                        flux_value_normalized = self.normalize_text(str(flux_value))
                        display_value = str(flux_value)
                    
                    # Calculer le score
                    if flux_value_normalized == search_value:
                        score = 100
                    elif search_value in flux_value_normalized:
                        score = 95
                    else:
                        score = fuzz.ratio(search_value, flux_value_normalized)
                    
                    if score < threshold:
                        is_valid = False
                        break
                    
                    position_scores.append(score)
                    matched_positions.append({
                        'position': v_index,
                        'search_term': validators[position - 1],
                        'matched_field': field_key,
                        'matched_value': display_value,
                        'score': score
                    })
                
                if not is_valid:
                    continue
                
                # 2. CRITIQUE : Vérifier que les positions suivantes sont VIDES
                for empty_position in range(num_validators + 1, 6):
                    # Vérifier les deux champs (username et full_name)
                    username_field = f'V{empty_position}'
                    fullname_field = f'V{empty_position}UserName'
                    
                    username_value = flux.get(username_field)
                    fullname_value = flux.get(fullname_field)
                    
                    # Si l'un des deux champs est rempli, le flux est invalide
                    if username_value or fullname_value:
                        print(f"   ❌ Flux '{flux.get('NomFluxMouvement')}' rejeté : "
                            f"V{empty_position} devrait être vide mais contient "
                            f"'{username_value or fullname_value}'")
                        is_valid = False
                        break
                
                if not is_valid:
                    continue
                
                # 3. Le flux est valide : il a les bons validateurs ET les positions suivantes sont vides
                avg_score = sum(position_scores) / len(position_scores)
                matching_flux.append({
                    'flux': flux,
                    'match_score': int(avg_score),
                    'matched_positions': matched_positions,
                    'matched_name': flux.get('NomFluxMouvement')
                })
            
            matching_flux = sorted(matching_flux, key=lambda x: x['match_score'], reverse=True)
            
            if not matching_flux:
                print(f"❌ Aucun flux trouvé avec la séquence stricte spécifiée (seuil: {threshold}%)")
                print(f"   Rappel : les positions V{num_validators + 1} à V5 doivent être VIDES")
                return None
            
            print(f"✅ {len(matching_flux)} flux trouvé(s) avec séquence stricte respectée")
            return self._process_ordered_results(matching_flux, limit)
            
        except Exception as e:
            print(f"❌ Erreur lors de la recherche stricte par séquence: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _format_strict_sequence_result(self, result: Dict) -> str:
        """
        Formate un résultat de recherche stricte par séquence
        
        Args:
            result: Résultat contenant flux et matched_positions
            
        Returns:
            str: Message formaté
        """
        flux = result['flux']
        score = result['match_score']
        matched_positions = result['matched_positions']
        
        message = f"✅ Flux trouvé (séquence stricte, score: {score}%):\n"
        message += f"   ID: {flux.get('IdFlux')}\n"
        message += f"   Nom: {flux.get('NomFluxMouvement')}\n"
        message += f"   Type: {flux.get('TypeFlux', 'N/A')}\n\n"
        message += f"   Séquence de validateurs:\n"
        
        # Afficher les validateurs correspondants
        for mp in matched_positions:
            message += f"      ✓ V{mp['position']}: {mp['matched_value']} (score: {mp['score']}%)\n"
        
        # Afficher les positions vides
        num_validators = len(matched_positions)
        if num_validators < 5:
            message += f"\n   Positions vides (comme requis):\n"
            for empty_pos in range(num_validators + 1, 6):
                message += f"      ○ V{empty_pos}: (vide)\n"
        
        return message.strip()


    def format_results(self, results: Union[Dict, List[Dict], None]) -> str:
        """
        Formate les résultats de recherche pour un affichage lisible
        VERSION MISE À JOUR avec support de la recherche stricte
        """
        if results is None:
            return "❌ Aucun flux trouvé correspondant à votre recherche."
        
        # Résultat unique
        if isinstance(results, dict):
            if 'matched_positions' in results:
                return self._format_strict_sequence_result(results)
            elif 'matched_matricules' in results:
                return self._format_flux_with_matricules(results)
            elif 'matched_validators' in results:
                return self._format_flux_with_validators(results)
            elif 'flux' in results:
                flux = results['flux']
                score = results['match_score']
                return self._format_single_flux(flux, score)
            else:
                return self._format_single_flux(results)
        
        # Résultats multiples
        if isinstance(results, list):
            if results and 'matched_positions' in results[0]:
                return self._format_multiple_strict_sequences(results)
            elif results and 'matched_matricules' in results[0]:
                return self._format_multiple_flux_with_matricules(results)
            elif results and 'matched_validators' in results[0]:
                return self._format_multiple_flux_with_validators(results)
            else:
                return self._format_multiple_flux(results)
        
        return "⚠️ Format de résultat inattendu."


    def _format_multiple_strict_sequences(self, results: List[Dict]) -> str:
        """Formate plusieurs flux avec séquence stricte"""
        message = f"📋 {len(results)} flux trouvés (séquence stricte):\n\n"
        
        for idx, result in enumerate(results, 1):
            flux = result['flux']
            score = result['match_score']
            matched_positions = result['matched_positions']
            
            message += f"{idx}. {flux.get('NomFluxMouvement')} (score: {score}%)\n"
            message += f"   ID: {flux.get('IdFlux')} | Type: {flux.get('TypeFlux', 'N/A')}\n"
            message += f"   Validateurs: "
            
            # Liste compacte des validateurs
            validators_list = [f"V{mp['position']}: {mp['matched_value']}" 
                            for mp in matched_positions]
            message += ", ".join(validators_list)
            
            # Indiquer les positions vides
            num_validators = len(matched_positions)
            if num_validators < 5:
                empty_positions = [f"V{i}" for i in range(num_validators + 1, 6)]
                message += f", {', '.join(empty_positions)}: (vides)"
            
            message += "\n\n"
        
        return message.strip()