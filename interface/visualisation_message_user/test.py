#!/usr/bin/env python3
"""
Script pour tester la fiabilité du modèle Rasa
Utilise les fichiers YAML exportés depuis la base de données
"""

import yaml
import requests
import json
import sys
from datetime import datetime
from collections import defaultdict
import argparse

class RasaModelTester:
    def __init__(self, rasa_url='http://localhost:5005', yaml_file=None):
        self.rasa_url = rasa_url
        self.yaml_file = yaml_file
        self.results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'errors': [],
            'confidence_scores': []
        }
    
    def load_test_stories(self):
        """Charger les test stories depuis le fichier YAML"""
        try:
            with open(self.yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data.get('stories', [])
        except Exception as e:
            print(f"❌ Erreur lors du chargement du fichier YAML: {e}")
            sys.exit(1)
    
    def send_message(self, sender, message):
        """Envoyer un message à Rasa et obtenir la réponse"""
        try:
            response = requests.post(
                f"{self.rasa_url}/webhooks/rest/webhook",
                json={
                    "sender": sender,
                    "message": message
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi du message: {e}")
            return None
    
    def get_tracker(self, sender):
        """Obtenir le tracker de conversation"""
        try:
            response = requests.get(
                f"{self.rasa_url}/conversations/{sender}/tracker",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Erreur lors de la récupération du tracker: {e}")
            return None
    
    def calculate_similarity(self, expected, actual):
        """Calculer la similarité entre deux textes (simple)"""
        expected_lower = expected.lower().strip()
        actual_lower = actual.lower().strip()
        
        # Correspondance exacte
        if expected_lower == actual_lower:
            return 100.0
        
        # Correspondance partielle
        if expected_lower in actual_lower or actual_lower in expected_lower:
            return 70.0
        
        # Compter les mots communs
        expected_words = set(expected_lower.split())
        actual_words = set(actual_lower.split())
        common_words = expected_words.intersection(actual_words)
        
        if len(expected_words) > 0:
            similarity = (len(common_words) / len(expected_words)) * 100
            return similarity
        
        return 0.0
    
    def test_story(self, story):
        """Tester une story complète"""
        story_name = story.get('story', 'Unknown')
        steps = story.get('steps', [])
        
        print(f"\n📖 Test de la story: {story_name}")
        print("=" * 60)
        
        sender = f"test_{story_name}_{int(datetime.now().timestamp())}"
        story_passed = True
        
        for step_idx, step in enumerate(steps):
            if 'user' in step:
                user_message = step['user']
                print(f"\n👤 User: {user_message}")
                
                # Envoyer le message
                responses = self.send_message(sender, user_message)
                
                if responses is None:
                    print("❌ Aucune réponse de Rasa")
                    story_passed = False
                    self.results['errors'].append({
                        'story': story_name,
                        'step': step_idx,
                        'error': 'No response from Rasa'
                    })
                    continue
                
                # Vérifier la réponse attendue
                if step_idx + 1 < len(steps):
                    next_step = steps[step_idx + 1]
                    if 'expected' in next_step:
                        expected = next_step['expected']
                        
                        # Combiner toutes les réponses
                        actual_responses = [r.get('text', '') for r in responses if 'text' in r]
                        actual = ' '.join(actual_responses)
                        
                        print(f"🤖 Bot (attendu): {expected[:100]}...")
                        print(f"🤖 Bot (reçu): {actual[:100]}...")
                        
                        # Calculer la similarité
                        similarity = self.calculate_similarity(expected, actual)
                        self.results['confidence_scores'].append(similarity)
                        
                        if similarity >= 70:
                            print(f"✅ Match: {similarity:.1f}%")
                        else:
                            print(f"❌ Échec: {similarity:.1f}%")
                            story_passed = False
                            self.results['errors'].append({
                                'story': story_name,
                                'step': step_idx,
                                'expected': expected,
                                'actual': actual,
                                'similarity': similarity
                            })
        
        self.results['total_tests'] += 1
        if story_passed:
            self.results['passed'] += 1
            print(f"\n✅ Story '{story_name}' RÉUSSIE")
        else:
            self.results['failed'] += 1
            print(f"\n❌ Story '{story_name}' ÉCHOUÉE")
    
    def run_tests(self):
        """Exécuter tous les tests"""
        print("🚀 Démarrage des tests Rasa")
        print(f"📁 Fichier de test: {self.yaml_file}")
        print(f"🌐 URL Rasa: {self.rasa_url}")
        
        stories = self.load_test_stories()
        
        if not stories:
            print("❌ Aucune story trouvée dans le fichier YAML")
            sys.exit(1)
        
        print(f"\n📊 {len(stories)} story(ies) à tester\n")
        
        for story in stories:
            self.test_story(story)
        
        self.print_summary()
    
    def print_summary(self):
        """Afficher le résumé des tests"""
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DES TESTS")
        print("=" * 60)
        
        print(f"\nTotal de tests: {self.results['total_tests']}")
        print(f"✅ Réussis: {self.results['passed']}")
        print(f"❌ Échoués: {self.results['failed']}")
        
        if self.results['total_tests'] > 0:
            success_rate = (self.results['passed'] / self.results['total_tests']) * 100
            print(f"📈 Taux de réussite: {success_rate:.1f}%")
        
        if self.results['confidence_scores']:
            avg_confidence = sum(self.results['confidence_scores']) / len(self.results['confidence_scores'])
            print(f"📊 Similarité moyenne: {avg_confidence:.1f}%")
        
        if self.results['errors']:
            print(f"\n❌ {len(self.results['errors'])} erreur(s) détectée(s):")
            for error in self.results['errors'][:5]:  # Afficher les 5 premières erreurs
                print(f"\n  Story: {error['story']}")
                if 'expected' in error:
                    print(f"  Attendu: {error['expected'][:80]}...")
                    print(f"  Reçu: {error['actual'][:80]}...")
                    print(f"  Similarité: {error['similarity']:.1f}%")
        
        # Sauvegarder le rapport
        self.save_report()
    
    def save_report(self):
        """Sauvegarder le rapport de test"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"test_report_{timestamp}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 Rapport sauvegardé: {report_file}")


def main():
    parser = argparse.ArgumentParser(description='Tester la fiabilité du modèle Rasa')
    parser.add_argument('yaml_file', help='Fichier YAML contenant les test stories')
    parser.add_argument('--rasa-url', default='http://localhost:5005', 
                       help='URL du serveur Rasa (défaut: http://localhost:5005)')
    
    args = parser.parse_args()
    
    tester = RasaModelTester(rasa_url=args.rasa_url, yaml_file=args.yaml_file)
    tester.run_tests()


if __name__ == '__main__':
    main()