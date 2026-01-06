#actions/services/ddr_service.py
from multiprocessing import process
import requests
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
import os
from datetime import datetime
from rapidfuzz import fuzz, process

load_dotenv()

class BackendService:
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = base_url or os.getenv('API_URL', '')
        self.api_key = api_key or os.getenv('RASA_API_KEY', '')
        print(f"BackendService initialized with base_url: {self.base_url} and api_key: {self.api_key}")

        # Création de la session Requests
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Api-Key': self.api_key
        })

        # ⚠️ Ignore les certificats auto-signés pour localhost/dev
        self.session.verify = False  # ← applique à toutes les requêtes

        if not self.api_key:
            print("⚠️ WARNING: RASA_API_KEY not configured. API calls may fail with 401/403 errors.")

    def _handle_response(self, response: requests.Response) -> Any:
        """Handle API response and errors"""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # ✅ Messages d'erreur plus détaillés pour l'authentification
            if response.status_code == 401:
                print(f"❌ Authentication Error (401): Invalid or missing API Key")
                print(f"   Make sure RASA_API_KEY is set correctly in your .env file")
            elif response.status_code == 403:
                print(f"❌ Authorization Error (403): Access forbidden")
                print(f"   The API Key may be correct but you don't have permission for this endpoint")
            else:
                print(f"HTTP Error: {e}")
            print(f"Response: {response.text}")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection Error: Unable to reach the API at {self.base_url}")
            print(f"   Make sure the backend server is running")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    # ==================== POSTES ====================
    def get_postes(self) -> List[Dict]:
        """Get all postes"""
        url = f"{self.base_url}/Postes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    def get_poste_by_id(self, poste_id: int) -> Optional[Dict]:
        """Get poste by ID"""
        url = f"{self.base_url}/Postes/{poste_id}"
        response = self.session.get(url)
        return self._handle_response(response)
    
    # ==================== DIRECTIONS ====================
    def get_directions(self) -> List[Dict]:
        """Get all directions"""
        url = f"{self.base_url}/Directions"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== EXPLOITATIONS ====================
    def get_exploitations(self) -> List[Dict]:
        """Get all exploitations"""
        url = f"{self.base_url}/Exploitations"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== MOTIFS ====================
    def get_motif_demandes(self) -> List[Dict]:
        """Get all motif demandes"""
        url = f"{self.base_url}/MotifDemandes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    def get_motif_demandes_manoeuvre(self) -> List[Dict]:
        """Get all motif demandes manoeuvre"""
        url = f"{self.base_url}/MotifDemandesManoeuvre"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== SITUATION BUDGET ====================
    def get_situation_budgets(self) -> List[Dict]:
        """Get all situation budgets"""
        url = f"{self.base_url}/SituationBudgets"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== USERS ====================
    def get_users(self) -> List[Dict]:
        """Get all users"""
        url = f"{self.base_url}/User"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    def get_user_by_login(self, username: str) -> Optional[Dict]:
        """Get user by login"""
        url = f"{self.base_url}/Login/getUserByLogin"
        response = self.session.get(url, params={'username': username})
        return self._handle_response(response)
    
    def get_all_user_details(self) -> List[Dict]:
        """Get all user details"""
        url = f"{self.base_url}/Login/getAllUsers"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== DEMANDES ====================
    def create_demande(self, demande_data: Dict) -> Optional[Dict]:
        """Create a new demande"""
        url = f"{self.base_url}/Demandes"
        response = self.session.post(url, json=demande_data)
        return self._handle_response(response)
    
    def create_demande_manoeuvre(self, demande_data: Dict) -> Optional[Dict]:
        """Create a new demande manoeuvre"""
        url = f"{self.base_url}/DemandesManoeuvre"
        response = self.session.post(url, json=demande_data)
        return self._handle_response(response)
    
    def get_demandes_by_username(self, username: str) -> List[Dict]:
        """Get demandes by username"""
        url = f"{self.base_url}/Demandes/Demandes/{username}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    def get_demande_by_id(self, demande_id: int) -> Optional[Dict]:
        """Get demande by ID"""
        url = f"{self.base_url}/Demandes/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)
    
    # ==================== DOTATIONS ====================
    def get_dotation_categories(self) -> List[Dict]:
        """Get all dotation categories"""
        url = f"{self.base_url}/DotationCategories"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    def get_dotation_listes(self) -> List[Dict]:
        """Get all dotation listes"""
        url = f"{self.base_url}/DotationListes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []
    
    # ==================== VALIDATION HELPERS ====================
    def validate_poste(self, poste_name: str) -> bool:
        """Validate if poste exists"""
        postes = self.get_postes()
        poste_names = [p.get('NomPoste', '').lower() for p in postes if p.get('NomPoste')]
        return poste_name.lower() in poste_names
    
    def validate_direction(self, direction_name: str) -> bool:
        """Validate if direction exists"""
        directions = self.get_directions()
        direction_names = [d.get('NomDirection', '').lower() for d in directions if d.get('NomDirection')]
        return direction_name.lower() in direction_names
    
    def validate_exploitation(self, exploitation_name: str) -> bool:
        """Validate if exploitation exists"""
        exploitations = self.get_exploitations()
        exploitation_names = [e.get('NomExploitation', '').lower() for e in exploitations if e.get('NomExploitation')]
        return exploitation_name.lower() in exploitation_names
    
    def validate_motif(self, motif_name: str, is_manoeuvre: bool = False) -> bool:
        """Validate if motif exists"""
        if is_manoeuvre:
            motifs = self.get_motif_demandes_manoeuvre()
        else:
            motifs = self.get_motif_demandes()
        motif_names = [m.get('Motif', '').lower() for m in motifs if m.get('Motif')]
        return motif_name.lower() in motif_names
    
    def validate_situation_budget(self, situation_name: str) -> bool:
        """Validate if situation budget exists"""
        situations = self.get_situation_budgets()
        situation_names = [s.get('SituationBudget', '').lower() for s in situations if s.get('SituationBudget')]
        return situation_name.lower() in situation_names
    
    def get_poste_id_by_name(self, poste_name: str) -> Optional[int]:
        """Get poste ID by name"""
        postes = self.get_postes()
        for p in postes:
            if p.get('NomPoste', '').lower() == poste_name.lower():
                return p.get('IdPoste')
        return None
    
    def get_direction_id_by_name(self, direction_name: str) -> Optional[int]:
        """Get direction ID by name"""
        directions = self.get_directions()
        for d in directions:
            if d.get('NomDirection', '').lower() == direction_name.lower():
                return d.get('IdDir')
        return None
    
    def get_exploitation_id_by_name(self, exploitation_name: str) -> Optional[int]:
        """Get exploitation ID by name"""
        exploitations = self.get_exploitations()
        for e in exploitations:
            if e.get('NomExploitation', '').lower() == exploitation_name.lower():
                return e.get('IdExp')
        return None
    
    def get_motif_id_by_name(self, motif_name: str, is_manoeuvre: bool = False) -> Optional[int]:
        """Get motif ID by name"""
        if is_manoeuvre:
            motifs = self.get_motif_demandes_manoeuvre()
            id_field = 'IdMotifMOE'
        else:
            motifs = self.get_motif_demandes()
            id_field = 'IdMotif'
        
        for m in motifs:
            if m.get('Motif', '').lower() == motif_name.lower():
                return m.get(id_field)
        return None
    
    def get_situation_budget_id_by_name(self, situation_name: str) -> Optional[int]:
        """Get situation budget ID by name"""
        situations = self.get_situation_budgets()
        for s in situations:
            if s.get('SituationBudget', '').lower() == situation_name.lower():
                return s.get('IdSb')
        return None

    def validate_user_exists(self, fullname: str):
        """Recherche intelligente des utilisateurs par fullname, tolère fautes et inversions"""
        users = self.get_all_user_details()
        print(f"Recherche intelligente pour fullname: {fullname}")
        print(f"Total utilisateurs récupérés: {len(users)}")

        # Préparer la liste des noms de la base avec leurs index
        user_names = [u.get('FullName', '') for u in users if u.get('FullName')]

        # Faire la recherche intelligente avec fuzz
        matches = process.extract(
            fullname, 
            user_names, 
            scorer=fuzz.token_sort_ratio,  # gère les inversions de mots
            limit=5  # retourne les 5 meilleurs résultats
        )

        # Filtrer les résultats au-dessus d'un seuil (ex: 70%)
        threshold = 70
        matching_users = []
        
        for match in matches:
            if match[1] >= threshold:
                matched_name = match[0]
                # Trouver l'utilisateur complet correspondant au nom
                user_detail = next((u for u in users if u.get('FullName') == matched_name), None)
                if user_detail:
                    matching_users.append({
                        'user_details': user_detail,
                        'match_score': match[1]  # Score de correspondance pour référence
                    })

        print(f"-------------------------------------------------------------------Correspondances trouvées: {len(matching_users)} utilisateur(s)")
        return matching_users
    def upload_file(self, file_data: bytes, filename: str, mime_type: str = None) -> Optional[Dict]:
        """Upload a single file to the backend using multipart/form-data"""
        # ✅ Utiliser l'endpoint UploadFiles (avec S) qui existe déjà
        url = f"{self.base_url}/Demandes/UploadFiles"
        
        try:
            # Déterminer le type MIME
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Sauvegarder les headers
            headers_backup = self.session.headers.copy()
            
            # Retirer temporairement Content-Type: application/json
            if 'Content-Type' in self.session.headers:
                del self.session.headers['Content-Type']
            
            # ✅ Utiliser le paramètre 'files' (pluriel) comme dans upload_files()
            files = [('files', (filename, file_data, mime_type))]
            response = self.session.post(url, files=files)
            
            # Restaurer les headers
            self.session.headers = headers_backup
            
            result = self._handle_response(response)
            
            # Le backend retourne une liste de fichiers uploadés
            if result:
                if isinstance(result, list) and len(result) > 0:
                    return {'success': True, 'filename': result[0]}
                elif isinstance(result, dict):
                    return {'success': True, 'filename': result.get('filename', filename)}
                elif isinstance(result, str):
                    return {'success': True, 'filename': result}
            
            return None
            
        except Exception as e:
            print(f"❌ Error uploading file {filename}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def upload_file_from_metadata(self, attachment: Dict) -> Optional[str]:
        """
        Upload a file from Rasa metadata attachment
        Returns the uploaded filename or None if failed
        """
        try:
            filename = attachment.get('name', 'unknown')
            mime_type = attachment.get('type', 'application/octet-stream')
            file_url = attachment.get('url')
            
            if not file_url:
                print(f"⚠️ No URL found for attachment: {filename}")
                return None
            
            # Si l'URL est en base64
            if file_url.startswith('data:'):
                import base64
                header, encoded = file_url.split(',', 1)
                file_data = base64.b64decode(encoded)
            else:
                response = self.session.get(file_url)
                if response.status_code != 200:
                    print(f"❌ Failed to download file from {file_url}")
                    return None
                file_data = response.content
            
            print(f"📦 File size: {len(file_data)} bytes, type: {mime_type}")
            
            # Appeler upload_file (singulier) avec les 3 paramètres
            result = self.upload_file(file_data, filename, mime_type)
            
            if result and result.get('success'):
                uploaded_filename = result.get('filename', filename)
                print(f"✅ File uploaded successfully: {uploaded_filename}")
                return uploaded_filename
            else:
                print(f"❌ Upload failed for {filename}")
                return None
                
        except Exception as e:
            print(f"❌ Error processing attachment {attachment.get('name')}: {e}")
            import traceback
            traceback.print_exc()
            return None
    # ==================== HEALTH CHECK ====================
    def test_connection(self) -> bool:
        """Test if the API connection and authentication are working"""
        try:
            print(f"🔍 Testing connection to {self.base_url}...")
            print(f"🔑 Using API Key: {self.api_key[:20]}..." if self.api_key else "⚠️  No API Key configured")
            
            # Test avec un endpoint simple
            postes = self.get_postes()
            
            if postes is not None:
                print(f"✅ Connection successful! Retrieved {len(postes)} postes")
                return True
            else:
                print("❌ Connection failed - check logs above for details")
                return False
                
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False

    # ==================== DEMANDES MANOEUVRE ====================
    def get_demandes_manoeuvre(self) -> List[Dict]:
        """Get all demandes manoeuvre"""
        url = f"{self.base_url}/DemandesManoeuvre"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demandes_manoeuvre_by_username(self, username: str) -> List[Dict]:
        """Get demandes manoeuvre by username"""
        url = f"{self.base_url}/DemandesManoeuvre/DemandesManoeuvre/{username}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demande_manoeuvre_by_id(self, demande_id: int) -> Optional[Dict]:
        """Get demande manoeuvre by ID"""
        url = f"{self.base_url}/DemandesManoeuvre/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def update_demande(self, demande_id: int, demande_data: Dict) -> Optional[Dict]:
        """Update a demande"""
        url = f"{self.base_url}/Demandes/{demande_id}"
        response = self.session.put(url, json=demande_data)
        return self._handle_response(response)

    def update_demande_manoeuvre(self, demande_id: int, demande_data: Dict) -> Optional[Dict]:
        """Update a demande manoeuvre"""
        url = f"{self.base_url}/DemandesManoeuvre/{demande_id}"
        response = self.session.put(url, json=demande_data)
        return self._handle_response(response)

    def update_demande_statut(self, demande_id: int, demande_traitement: Dict) -> Optional[Dict]:
        """Update demande status"""
        url = f"{self.base_url}/Demandes/statut/{demande_id}"
        response = self.session.put(url, json=demande_traitement)
        return self._handle_response(response)

    def update_demande_manoeuvre_statut(self, demande_id: int, demande_traitement: Dict) -> Optional[Dict]:
        """Update demande manoeuvre status"""
        url = f"{self.base_url}/DemandesManoeuvre/statut/{demande_id}"
        response = self.session.put(url, json=demande_traitement)
        return self._handle_response(response)

    def delete_demande(self, demande_id: int) -> bool:
        """Delete a demande"""
        url = f"{self.base_url}/Demandes/{demande_id}"
        response = self.session.delete(url)
        return self._handle_response(response) is not None

    def filter_demande(self, search_criteria: Dict) -> List[Dict]:
        """Filter demandes"""
        url = f"{self.base_url}/Demandes/filterDemande"
        response = self.session.post(url, json=search_criteria)
        data = self._handle_response(response)
        return data if data else []

    def filter_demande_manoeuvre(self, search_criteria: Dict) -> List[Dict]:
        """Filter demandes manoeuvre"""
        url = f"{self.base_url}/DemandesManoeuvre/filterDemande"
        response = self.session.post(url, json=search_criteria)
        data = self._handle_response(response)
        return data if data else []

    # ==================== TYPE MOBILITE ====================
    def get_type_mobilites(self) -> List[Dict]:
        """Get all type mobilites"""
        url = f"{self.base_url}/MpTypeMobilites"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== OBJECTIFS ====================
    def get_objectif_demandes(self) -> List[Dict]:
        """Get all objectif demandes"""
        url = f"{self.base_url}/ObjectifDemandes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_objectif_demandes_manoeuvre(self) -> List[Dict]:
        """Get all objectif demandes manoeuvre"""
        url = f"{self.base_url}/ObjectifDemandesManoeuvre"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_objectifs_by_demande_id(self, demande_id: int) -> List[Dict]:
        """Get objectifs by demande ID"""
        url = f"{self.base_url}/Demandes/{demande_id}/Objectifs"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_objectifs_by_demande_manoeuvre_id(self, demande_id: int) -> List[Dict]:
        """Get objectifs by demande manoeuvre ID"""
        url = f"{self.base_url}/DemandesManoeuvre/{demande_id}/Objectifs"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== STATUTS ====================
    def get_statuts(self) -> List[Dict]:
        """Get all statuts"""
        url = f"{self.base_url}/Statuts"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_statut_traitements(self) -> List[Dict]:
        """Get all statut traitements"""
        url = f"{self.base_url}/StatutTraitements"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_statut_mobilites(self) -> List[Dict]:
        """Get all statut mobilites"""
        url = f"{self.base_url}/StatutMobilites"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== LIAISONS ====================
    def get_liaison_ddr_dotation(self) -> List[Dict]:
        """Get all liaison DDR dotation"""
        url = f"{self.base_url}/LiaisonDdrdotations"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_liaison_ddr_dotation_by_demande(self, demande_id: int) -> List[Dict]:
        """Get liaison DDR dotation by demande ID"""
        url = f"{self.base_url}/LiaisonDdrdotations/demande/{demande_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def update_liaison_ddr_dotation(self, liaison_id: int, dotation_embauche: Dict) -> Optional[Dict]:
        """Update liaison DDR dotation"""
        url = f"{self.base_url}/LiaisonDdrdotations/{liaison_id}"
        response = self.session.put(url, json=dotation_embauche)
        return self._handle_response(response)

    def get_liaison_dotation_poste(self) -> List[Dict]:
        """Get all liaison dotation poste"""
        url = f"{self.base_url}/LiaisonDotationPostes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def create_liaison_poste_dotation(self, liaison_data: Dict) -> Optional[Dict]:
        """Create liaison poste dotation"""
        url = f"{self.base_url}/LiaisonDotationPostes"
        response = self.session.post(url, json=liaison_data)
        return self._handle_response(response)

    def update_liaison_poste_dotation(self, liaison_id: int, liaison_data: Dict) -> Optional[Dict]:
        """Update liaison poste dotation"""
        url = f"{self.base_url}/LiaisonDotationPostes/{liaison_id}"
        response = self.session.put(url, json=liaison_data)
        return self._handle_response(response)

    def get_dotation_poste_by_id(self, liaison_id: int) -> Optional[Dict]:
        """Get dotation poste by ID"""
        url = f"{self.base_url}/LiaisonDotationPostes/{liaison_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_dotations_by_poste_id(self, poste_id: int) -> List[Dict]:
        """Get dotations by poste ID"""
        url = f"{self.base_url}/LiaisonDotationPostes/{poste_id}/Dotations"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def delete_liaison_dotation_poste(self, liaison_id: int) -> bool:
        """Delete liaison dotation poste"""
        url = f"{self.base_url}/LiaisonDotationPostes/{liaison_id}"
        response = self.session.delete(url)
        return self._handle_response(response) is not None

    # ==================== FLUX ====================
    def get_flux_taches(self) -> List[Dict]:
        """Get all flux taches"""
        url = f"{self.base_url}/FluxTaches"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_mouvements(self) -> List[Dict]:
        """Get all flux mouvements"""
        url = f"{self.base_url}/FluxMouvements"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_mouvements_with_details(self) -> List[Dict]:
        """Get all flux mouvements with details"""
        url = f"{self.base_url}/FluxMouvements/with-user-details"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_mouvement_by_direction(self, direction_id: int) -> List[Dict]:
        """Get flux mouvement by direction"""
        url = f"{self.base_url}/FluxMouvements/direction/{direction_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_mouvement_by_validateur(self, validateur: str) -> Optional[Dict]:
        """Get flux mouvement by validateur"""
        url = f"{self.base_url}/FluxMouvements/validateur/{validateur}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_flux_mouvement_by_validateur_and_demande(self, validateur: str, flux_id: int, demande_id: int) -> Optional[Dict]:
        """Get flux mouvement by validateur and demande"""
        url = f"{self.base_url}/FluxMouvements/validateur/{validateur}/{flux_id}/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_flux_mouvement_by_validateur_and_demande_moe(self, validateur: str, flux_id: int, demande_id: int) -> Optional[Dict]:
        """Get flux mouvement by validateur and demande manoeuvre"""
        url = f"{self.base_url}/FluxMouvements/validateurMOE/{validateur}/{flux_id}/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_flux_mouvement_by_validateur_and_validation(self, validateur: str, validation_id: int) -> Optional[Dict]:
        """Get flux mouvement by validateur and validation"""
        url = f"{self.base_url}/FluxMouvements/validateur/{validateur}/{validation_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_flux_tache_by_validateur(self, validateur: str) -> List[Dict]:
        """Get flux taches by validateur"""
        url = f"{self.base_url}/FluxTaches/validateur/{validateur}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_tache_manoeuvre_by_validateur(self, validateur: str) -> List[Dict]:
        """Get flux taches manoeuvre by validateur"""
        url = f"{self.base_url}/FluxTachesManoeuvre/validateur/{validateur}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def update_flux_tache(self, flux_id: int, flux_data: Dict) -> Optional[Dict]:
        """Update flux tache"""
        url = f"{self.base_url}/FluxTaches/{flux_id}"
        response = self.session.put(url, json=flux_data)
        return self._handle_response(response)

    def update_flux_tache_manoeuvre(self, flux_id: int, flux_data: Dict) -> Optional[Dict]:
        """Update flux tache manoeuvre"""
        url = f"{self.base_url}/FluxTachesManoeuvre/{flux_id}"
        response = self.session.put(url, json=flux_data)
        return self._handle_response(response)

    def get_flux_tache_by_demande_and_validateur(self, demande_id: int, validateur: str) -> Optional[Dict]:
        """Get flux tache by demande and validateur"""
        url = f"{self.base_url}/FluxTaches/demande/{demande_id}/validateur/{validateur}"
        response = self.session.get(url)
        return self._handle_response(response)
    
    def get_flux_tache_by_demande_manoeuvre_and_validateur(self, demande_id: int, validateur: str) -> Optional[Dict]:
        """Get flux tache by demande manoeuvre and validateur"""
        url = f"{self.base_url}/FluxTachesManoeuvre/demande/{demande_id}/validateur/{validateur}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_flux_tache_by_demande_and_etat(self, demande_id: int) -> List[Dict]:
        """Get flux taches by demande ID and validation state"""
        url = f"{self.base_url}/FluxTaches/demande/{demande_id}/validation"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_flux_tache_by_demande_manoeuvre_and_etat(self, demande_id: int) -> List[Dict]:
        """Get flux taches by demande manoeuvre ID and validation state"""
        url = f"{self.base_url}/FluxTachesManoeuvre/demande/{demande_id}/validation"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def create_flux(self, flux_data: Dict) -> Optional[Dict]:
        """Create flux mouvement"""
        url = f"{self.base_url}/FluxMouvements"
        response = self.session.post(url, json=flux_data)
        return self._handle_response(response)

    def update_flux(self, flux_id: int, flux_data: Dict) -> Optional[Dict]:
        """Update flux mouvement"""
        url = f"{self.base_url}/FluxMouvements/{flux_id}"
        response = self.session.put(url, json=flux_data)
        return self._handle_response(response)

    def get_flux_by_id(self, flux_id: int) -> Optional[Dict]:
        """Get flux by ID"""
        url = f"{self.base_url}/FluxMouvements/{flux_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def delete_flux(self, flux_id: int) -> bool:
        """Delete flux"""
        url = f"{self.base_url}/FluxMouvements/{flux_id}"
        response = self.session.delete(url)
        return self._handle_response(response) is not None

    # ==================== DOTATION ====================
    def create_dotation(self, dotation_data: Dict) -> Optional[Dict]:
        """Create dotation"""
        url = f"{self.base_url}/DotationListes"
        response = self.session.post(url, json=dotation_data)
        return self._handle_response(response)

    def update_dotation(self, dotation_id: int, dotation_data: Dict) -> Optional[Dict]:
        """Update dotation"""
        url = f"{self.base_url}/DotationListes/{dotation_id}"
        response = self.session.put(url, json=dotation_data)
        return self._handle_response(response)

    def get_dotation_by_id(self, dotation_id: int) -> Optional[Dict]:
        """Get dotation by ID"""
        url = f"{self.base_url}/DotationListes/{dotation_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_dotation_by_demande_id(self, demande_id: int) -> List[Dict]:
        """Get dotations by demande ID"""
        url = f"{self.base_url}/Demandes/{demande_id}/Dotations"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def delete_dotation(self, dotation_id: int) -> bool:
        """Delete dotation"""
        url = f"{self.base_url}/DotationListes/{dotation_id}"
        response = self.session.delete(url)
        return self._handle_response(response) is not None

    # ==================== EMBAUCHES ====================
    def get_embauches(self) -> List[Dict]:
        """Get all embauches"""
        url = f"{self.base_url}/Embauches"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def create_embauche(self, embauche_data: Dict) -> Optional[Dict]:
        """Create embauche"""
        url = f"{self.base_url}/Embauches"
        response = self.session.post(url, json=embauche_data)
        return self._handle_response(response)

    def get_embauche_by_id(self, embauche_id: int) -> Optional[Dict]:
        """Get embauche by ID"""
        url = f"{self.base_url}/Embauches/{embauche_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def update_embauche(self, embauche_id: int, embauche_data: Dict, photo_file: Optional[str] = None) -> Optional[Dict]:
        """Update embauche (multipart/form-data if photo included)"""
        url = f"{self.base_url}/Embauches/{embauche_id}"
        
        if photo_file:
            # Si un fichier photo est fourni, utiliser multipart/form-data
            files = {'Photo': open(photo_file, 'rb')}
            response = self.session.put(url, data=embauche_data, files=files)
        else:
            # Sinon, envoyer en JSON
            response = self.session.put(url, json=embauche_data)
        
        return self._handle_response(response)

    def delete_embauche(self, embauche_id: int) -> bool:
        """Delete embauche"""
        url = f"{self.base_url}/Embauches/{embauche_id}"
        response = self.session.delete(url)
        return self._handle_response(response) is not None

    def get_filtered_embauches(self) -> List[Dict]:
        """Get filtered embauches"""
        url = f"{self.base_url}/Embauches/filtered-embauches"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== MOUVEMENTS ====================
    def get_mouvement_by_id(self, mouvement_id: int) -> Optional[Dict]:
        """Get mouvement by ID"""
        url = f"{self.base_url}/Mouvements/{mouvement_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    # ==================== COMPLEMENTS ====================
    def create_complement(self, complement_data: Dict) -> Optional[Dict]:
        """Create complement DDR"""
        url = f"{self.base_url}/ComplementDdrs"
        response = self.session.post(url, json=complement_data)
        return self._handle_response(response)

    def create_complement_manoeuvre(self, complement_data: Dict) -> Optional[Dict]:
        """Create complement DDR manoeuvre"""
        url = f"{self.base_url}/ComplementDdrsMOE"
        response = self.session.post(url, json=complement_data)
        return self._handle_response(response)

    def get_complement_by_demande_id(self, demande_id: int) -> List[Dict]:
        """Get complements by demande ID"""
        url = f"{self.base_url}/ComplementDdrs/demande/{demande_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_complement_by_demande_manoeuvre_id(self, demande_id: int) -> List[Dict]:
        """Get complements by demande manoeuvre ID"""
        url = f"{self.base_url}/ComplementDdrsMOE/demande/{demande_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== POSTE ====================
    def create_poste(self, poste_data: Dict) -> Optional[Dict]:
        """Create poste"""
        url = f"{self.base_url}/Postes"
        response = self.session.post(url, json=poste_data)
        return self._handle_response(response)

    # ==================== VALIDATION ====================
    def get_demandes_for_validateur(self, username: str) -> List[Dict]:
        """Get demandes for validateur"""
        url = f"{self.base_url}/Demandes/validateur/{username}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demande_by_statut_and_login(self, statut_id: int, username: str) -> List[Dict]:
        """Get demandes by statut ID and username"""
        url = f"{self.base_url}/Demandes/Statut/{username}/{statut_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demande_manoeuvre_by_statut_and_login(self, statut_id: int, username: str) -> List[Dict]:
        """Get demandes manoeuvre by statut ID and username"""
        url = f"{self.base_url}/DemandesManoeuvre/Statut/{username}/{statut_id}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demande_traitement_by_id(self, demande_id: int) -> Optional[Dict]:
        """Get demande traitement by ID"""
        url = f"{self.base_url}/Demandes/traitement/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_demande_manoeuvre_traitement_by_id(self, demande_id: int) -> Optional[Dict]:
        """Get demande manoeuvre traitement by ID"""
        url = f"{self.base_url}/DemandesManoeuvre/traitement/{demande_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    def validate_mp_demande(self, demande_id: int, flux_tache_data: Dict) -> Optional[Dict]:
        """Validate MP demande"""
        url = f"{self.base_url}/Demandes/{demande_id}/validate"
        response = self.session.put(url, json=flux_tache_data)
        return self._handle_response(response)

    def validate_mp_demande_manoeuvre(self, demande_id: int, flux_tache_data: Dict) -> Optional[Dict]:
        """Validate MP demande manoeuvre"""
        url = f"{self.base_url}/DemandesManoeuvre/{demande_id}/validate"
        response = self.session.put(url, json=flux_tache_data)
        return self._handle_response(response)

    def send_demande_to_validateur(self, demande_id: int, nom_flux_id: int, responsable_rh: str, demande_data: Dict) -> Optional[Dict]:
        """Send demande to validateur"""
        url = f"{self.base_url}/Demandes/{demande_id}/send-to-validateur/{nom_flux_id}/{responsable_rh}"
        response = self.session.post(url, json=demande_data)
        return self._handle_response(response)

    def send_demande_manoeuvre_to_validateur(self, demande_id: int, nom_flux_id: int, responsable_rh: str, demande_data: Dict) -> Optional[Dict]:
        """Send demande manoeuvre to validateur"""
        url = f"{self.base_url}/DemandesManoeuvre/{demande_id}/send-to-validateur/{nom_flux_id}/{responsable_rh}"
        response = self.session.post(url, json=demande_data)
        return self._handle_response(response)

    def get_demandes_by_user_id(self, user_id: int) -> List[Dict]:
        """Get demandes by user ID"""
        url = f"{self.base_url}/Demandes/{user_id}/Demandes"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_demandes_manoeuvre_by_user_id(self, user_id: int) -> List[Dict]:
        """Get demandes manoeuvre by user ID"""
        url = f"{self.base_url}/Demandes/{user_id}/"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    # ==================== FILES ====================
    def upload_files(self, files: List[str]) -> Optional[Dict]:
        """Upload files"""
        url = f"{self.base_url}/Demandes/UploadFiles"
        files_data = [('files', open(f, 'rb')) for f in files]
        response = self.session.post(url, files=files_data)
        return self._handle_response(response)

    def download_file(self, filename: str) -> Optional[bytes]:
        """Download file"""
        url = f"{self.base_url}/Demandes/DownloadFile/{filename}"
        response = self.session.get(url)
        if response.status_code == 200:
            return response.content
        return None

    # ==================== NOM FLUX ====================

    def get_nom_flux_by_id(self, nom_flux_id: int) -> Optional[Dict]:
        """Get nom flux by ID"""
        url = f"{self.base_url}/NomFlux/{nom_flux_id}"
        response = self.session.get(url)
        return self._handle_response(response)

    # ==================== USER DETAILS ====================
    def get_user_by_full_name(self, username: str) -> List[Dict]:
        """Get user by full name"""
        url = f"{self.base_url}/Login/getUserByFullName/{username}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_user_by_username(self, username: str) -> List[Dict]:
        """Get user by username"""
        url = f"{self.base_url}/Login/{username}"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else []

    def get_current_user_role(self) -> Optional[Dict]:
        """Get current user role"""
        url = f"{self.base_url}/User/currentUserRole"
        response = self.session.get(url)
        return self._handle_response(response)

    def get_windows_identity(self) -> Optional[str]:
        """Get Windows identity"""
        url = f"{self.base_url}/Login/windowsIdentity"
        response = self.session.get(url)
        data = self._handle_response(response)
        return data if data else None

    def get_current_user_details_login(self) -> Optional[Dict]:
        """Get current user details from login"""
        url = f"{self.base_url}/Login/getDetailsLogin"
        response = self.session.get(url)
        return self._handle_response(response)

    # ==================== VALIDATION HELPERS (EXTENDED) ====================
    def get_objectif_demande_id_by_name(self, objectif_name: str) -> Optional[int]:
        """Get objectif demande ID by name"""
        objectifs = self.get_objectif_demandes()
        for obj in objectifs:
            if obj.get('Objectif', '').lower() == objectif_name.lower():
                return obj.get('IdObjectif')
        return None

    def get_objectif_demande_manoeuvre_id_by_name(self, objectif_name: str) -> Optional[int]:
        """Get objectif demande manoeuvre ID by name"""
        objectifs = self.get_objectif_demandes_manoeuvre()
        for obj in objectifs:
            if obj.get('Objectif', '').lower() == objectif_name.lower():
                return obj.get('IdObjectifMOE')
        return None
    
    def get_type_mobilite_id_by_name(self, type_name: str) -> Optional[int]:
        """Get type mobilite ID by name"""
        types = self.get_type_mobilites()
        for t in types:
            if t.get('TypeMobilite', '').lower() == type_name.lower():
                return t.get('IdTypeMobilite')
        return None

    def get_statut_id_by_name(self, statut_name: str) -> Optional[int]:
        """Get statut ID by name"""
        statuts = self.get_statuts()
        for s in statuts:
            if s.get('Statut', '').lower() == statut_name.lower():
                return s.get('IdStatut')
        return None

    def get_statut_traitement_id_by_name(self, statut_name: str) -> Optional[int]:
        """Get statut traitement ID by name"""
        statuts = self.get_statut_traitements()
        for s in statuts:
            if s.get('StatutTraitement', '').lower() == statut_name.lower():
                return s.get('IdStatutTraitement')
        return None

    def get_statut_mobilite_id_by_name(self, statut_name: str) -> Optional[int]:
        """Get statut mobilite ID by name"""
        statuts = self.get_statut_mobilites()
        for s in statuts:
            if s.get('StatutMobilite', '').lower() == statut_name.lower():
                return s.get('IdStatutMobilite')
        return None

    def get_dotation_categorie_id_by_name(self, categorie_name: str) -> Optional[int]:
        """Get dotation categorie ID by name"""
        categories = self.get_dotation_categories()
        for cat in categories:
            if cat.get('Categorie', '').lower() == categorie_name.lower():
                return cat.get('IdCategorie')
        return None

    # ==================== VALIDATION HELPERS (BOOLEAN) ====================
    def validate_objectif_demande(self, objectif_name: str) -> bool:
        """Validate if objectif demande exists"""
        objectifs = self.get_objectif_demandes()
        objectif_names = [obj.get('Objectif', '').lower() for obj in objectifs if obj.get('Objectif')]
        return objectif_name.lower() in objectif_names

    def validate_objectif_demande_manoeuvre(self, objectif_name: str) -> bool:
        """Validate if objectif demande manoeuvre exists"""
        objectifs = self.get_objectif_demandes_manoeuvre()
        objectif_names = [obj.get('Objectif', '').lower() for obj in objectifs if obj.get('Objectif')]
        return objectif_name.lower() in objectif_names

    def validate_type_mobilite(self, type_name: str) -> bool:
        """Validate if type mobilite exists"""
        types = self.get_type_mobilites()
        type_names = [t.get('TypeMobilite', '').lower() for t in types if t.get('TypeMobilite')]
        return type_name.lower() in type_names

    def validate_statut(self, statut_name: str) -> bool:
        """Validate if statut exists"""
        statuts = self.get_statuts()
        statut_names = [s.get('Statut', '').lower() for s in statuts if s.get('Statut')]
        return statut_name.lower() in statut_names

    def validate_statut_traitement(self, statut_name: str) -> bool:
        """Validate if statut traitement exists"""
        statuts = self.get_statut_traitements()
        statut_names = [s.get('StatutTraitement', '').lower() for s in statuts if s.get('StatutTraitement')]
        return statut_name.lower() in statut_names

    def validate_statut_mobilite(self, statut_name: str) -> bool:
        """Validate if statut mobilite exists"""
        statuts = self.get_statut_mobilites()
        statut_names = [s.get('StatutMobilite', '').lower() for s in statuts if s.get('StatutMobilite')]
        return statut_name.lower() in statut_names

    def validate_dotation_categorie(self, categorie_name: str) -> bool:
        """Validate if dotation categorie exists"""
        categories = self.get_dotation_categories()
        categorie_names = [cat.get('Categorie', '').lower() for cat in categories if cat.get('Categorie')]
        return categorie_name.lower() in categorie_names

    # ==================== SEARCH AND FUZZY MATCHING ====================
    def find_similar_postes(self, poste_name: str, threshold: int = 70, limit: int = 5) -> List[tuple]:
        """Find similar postes using fuzzy matching"""
        from rapidfuzz import fuzz, process
        
        postes = self.get_postes()
        poste_names = [p.get('NomPoste', '') for p in postes if p.get('NomPoste')]
        
        matches = process.extract(
            poste_name,
            poste_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        
        return [match for match in matches if match[1] >= threshold]

    def find_similar_directions(self, direction_name: str, threshold: int = 70, limit: int = 5) -> List[tuple]:
        """Find similar directions using fuzzy matching"""
        from rapidfuzz import fuzz, process
        
        directions = self.get_directions()
        direction_names = [d.get('NomDirection', '') for d in directions if d.get('NomDirection')]
        
        matches = process.extract(
            direction_name,
            direction_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        
        return [match for match in matches if match[1] >= threshold]

    def find_similar_exploitations(self, exploitation_name: str, threshold: int = 70, limit: int = 5) -> List[tuple]:
        """Find similar exploitations using fuzzy matching"""
        from rapidfuzz import fuzz, process
        
        exploitations = self.get_exploitations()
        exploitation_names = [e.get('NomExploitation', '') for e in exploitations if e.get('NomExploitation')]
        
        matches = process.extract(
            exploitation_name,
            exploitation_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        
        return [match for match in matches if match[1] >= threshold]

    def find_similar_motifs(self, motif_name: str, is_manoeuvre: bool = False, threshold: int = 70, limit: int = 5) -> List[tuple]:
        """Find similar motifs using fuzzy matching"""
        from rapidfuzz import fuzz, process
        
        if is_manoeuvre:
            motifs = self.get_motif_demandes_manoeuvre()
        else:
            motifs = self.get_motif_demandes()
        
        motif_names = [m.get('Motif', '') for m in motifs if m.get('Motif')]
        
        matches = process.extract(
            motif_name,
            motif_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        
        return [match for match in matches if match[1] >= threshold]

    def find_similar_users_by_fullname(self, fullname: str, threshold: int = 70, limit: int = 5) -> List[tuple]:
        """Find similar users by fullname using fuzzy matching"""
        from rapidfuzz import fuzz, process
        
        users = self.get_all_user_details()
        user_names = [u.get('FullName', '') for u in users if u.get('FullName')]
        
        matches = process.extract(
            fullname,
            user_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        
        return [match for match in matches if match[1] >= threshold]

    # ==================== BATCH OPERATIONS ====================
    def get_demande_with_details(self, demande_id: int) -> Optional[Dict]:
        """Get demande with all related details (objectifs, dotations, complements)"""
        demande = self.get_demande_by_id(demande_id)
        if not demande:
            return None
        
        # Enrichir avec les détails
        demande['objectifs'] = self.get_objectifs_by_demande_id(demande_id)
        demande['dotations'] = self.get_dotation_by_demande_id(demande_id)
        demande['complements'] = self.get_complement_by_demande_id(demande_id)
        demande['liaisons_dotation'] = self.get_liaison_ddr_dotation_by_demande(demande_id)
        demande['flux_taches'] = self.get_flux_tache_by_demande_and_etat(demande_id)
        
        return demande

    def get_demande_manoeuvre_with_details(self, demande_id: int) -> Optional[Dict]:
        """Get demande manoeuvre with all related details"""
        demande = self.get_demande_manoeuvre_by_id(demande_id)
        if not demande:
            return None
        
        # Enrichir avec les détails
        demande['objectifs'] = self.get_objectifs_by_demande_manoeuvre_id(demande_id)
        demande['complements'] = self.get_complement_by_demande_manoeuvre_id(demande_id)
        demande['flux_taches'] = self.get_flux_tache_by_demande_manoeuvre_and_etat(demande_id)
        
        return demande

    def get_user_demandes_summary(self, username: str) -> Dict:
        """Get complete summary of user's demandes and demandes manoeuvre"""
        summary = {
            'demandes': self.get_demandes_by_username(username),
            'demandes_manoeuvre': self.get_demandes_manoeuvre_by_username(username),
            'demandes_a_valider': self.get_demandes_for_validateur(username),
            'flux_taches': self.get_flux_tache_by_validateur(username),
            'flux_taches_manoeuvre': self.get_flux_tache_manoeuvre_by_validateur(username)
        }
        
        # Ajouter des statistiques
        summary['stats'] = {
            'total_demandes': len(summary['demandes']),
            'total_demandes_manoeuvre': len(summary['demandes_manoeuvre']),
            'total_a_valider': len(summary['demandes_a_valider']),
            'total_flux_taches': len(summary['flux_taches']),
            'total_flux_taches_manoeuvre': len(summary['flux_taches_manoeuvre'])
        }
        
        return summary

    # ==================== UTILITY FUNCTIONS ====================
    def get_all_reference_data(self) -> Dict:
        """Get all reference data in one call for caching purposes"""
        return {
            'postes': self.get_postes(),
            'directions': self.get_directions(),
            'exploitations': self.get_exploitations(),
            'motif_demandes': self.get_motif_demandes(),
            'motif_demandes_manoeuvre': self.get_motif_demandes_manoeuvre(),
            'objectif_demandes': self.get_objectif_demandes(),
            'objectif_demandes_manoeuvre': self.get_objectif_demandes_manoeuvre(),
            'situation_budgets': self.get_situation_budgets(),
            'statuts': self.get_statuts(),
            'statut_traitements': self.get_statut_traitements(),
            'statut_mobilites': self.get_statut_mobilites(),
            'type_mobilites': self.get_type_mobilites(),
            'dotation_categories': self.get_dotation_categories(),
            'nom_flux': self.get_nom_flux()
        }

    def format_date_for_api(self, date_str: str) -> str:
        """Format date string for API (ISO format)"""
        try:
            # Si c'est déjà au bon format, retourner tel quel
            if 'T' in date_str:
                return date_str
            
            # Sinon, parser et formater
            from datetime import datetime
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.isoformat()
        except Exception as e:
            print(f"Error formatting date: {e}")
            return date_str

    def print_api_summary(self):
        """Print a summary of available endpoints"""
        print("=" * 80)
        print("BACKEND SERVICE - API ENDPOINTS SUMMARY")
        print("=" * 80)
        print(f"Base URL: {self.base_url}")
        print(f"API Key configured: {'Yes' if self.api_key else 'No'}")
        print("\nAvailable endpoint categories:")
        print("  - Postes")
        print("  - Directions")
        print("  - Exploitations")
        print("  - Situation Budgets")
        print("  - Statuts (Standard, Traitement, Mobilite)")
        print("  - Type Mobilites")
        print("  - Users & Authentication")
        print("  - Demandes (Standard & Manoeuvre)")
        print("  - Dotations")
        print("  - Flux (Taches, Taches Manoeuvre, Mouvements)")
        print("  - Embauches")
        print("  - Mouvements")
        print("  - Complements")
        print("  - Files (Upload/Download)")
        print("  - Nom Flux")
        print("  - Validation & Workflow")
        print("=" * 80)
# Singleton instance
_backend_service = None

def get_backend_service() -> BackendService:
    """Get singleton instance of BackendService"""
    global _backend_service
    if _backend_service is None:
        _backend_service = BackendService()
    return _backend_service


# ==================== UTILITY FUNCTION FOR TESTING ====================
def test_backend_connection():
    """
    Utility function to test backend connection and authentication
    Can be called from Rasa actions or run directly
    """
    service = get_backend_service()
    return service.test_connection()


if __name__ == "__main__":
    # Test the connection when running this file directly
    print("=" * 60)
    print("Testing Backend Service Connection")
    print("=" * 60)
    test_backend_connection()