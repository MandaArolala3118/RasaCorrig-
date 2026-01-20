import json
import csv
import os
from collections import defaultdict

class RasaTestAnalyzer:
    def __init__(self, test_folder):
        self.test_folder = test_folder
        self.results = {}
        
    def load_json_file(self, filename):
        """Charge un fichier JSON"""
        filepath = os.path.join(self.test_folder, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Erreur lors de la lecture de {filename}: {e}")
        return None
    
    def load_csv_file(self, filename):
        """Charge un fichier CSV"""
        filepath = os.path.join(self.test_folder, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    return list(reader)
            except Exception as e:
                print(f"Erreur lors de la lecture de {filename}: {e}")
        return None
    
    def analyze_intent_report(self):
        """Analyse le rapport des intentions"""
        report = self.load_json_file('intent_report.json')
        if not report:
            return None
        
        analysis = {
            'accuracy': report.get('accuracy', 'N/A'),
            'macro_avg_f1': report.get('macro avg', {}).get('f1-score', 'N/A'),
            'weighted_avg_f1': report.get('weighted avg', {}).get('f1-score', 'N/A'),
            'low_performing_intents': [],
            'high_performing_intents': []
        }
        
        # Identifier les intentions problématiques
        for intent, metrics in report.items():
            if isinstance(metrics, dict) and 'f1-score' in metrics:
                f1 = metrics['f1-score']
                support = metrics.get('support', 0)
                
                intent_info = {
                    'name': intent,
                    'f1-score': f1,
                    'precision': metrics.get('precision', 'N/A'),
                    'recall': metrics.get('recall', 'N/A'),
                    'support': support
                }
                
                if f1 < 0.7:  # Seuil de performance faible
                    analysis['low_performing_intents'].append(intent_info)
                elif f1 > 0.9:
                    analysis['high_performing_intents'].append(intent_info)
        
        return analysis
    
    def analyze_intent_errors(self):
        """Analyse les erreurs d'intentions"""
        errors = self.load_json_file('intent_errors.json')
        if not errors:
            return None
        
        error_patterns = defaultdict(list)
        
        for error in errors:
            predicted = error.get('intent_prediction', {}).get('name', 'unknown')
            actual = error.get('intent', 'unknown')
            text = error.get('text', '')
            confidence = error.get('intent_prediction', {}).get('confidence', 0)
            
            error_patterns[f"{actual} → {predicted}"].append({
                'text': text,
                'confidence': confidence
            })
        
        return {
            'total_errors': len(errors),
            'error_patterns': dict(error_patterns)
        }
    
    def analyze_diet_report(self):
        """Analyse le rapport DIETClassifier"""
        report = self.load_json_file('DIETClassifier_report.json')
        if not report:
            return None
        
        analysis = {
            'overall_performance': {},
            'entity_performance': []
        }
        
        # Performance globale
        if 'macro avg' in report:
            analysis['overall_performance'] = {
                'precision': report['macro avg'].get('precision', 'N/A'),
                'recall': report['macro avg'].get('recall', 'N/A'),
                'f1-score': report['macro avg'].get('f1-score', 'N/A')
            }
        
        # Performance par entité
        for entity, metrics in report.items():
            if isinstance(metrics, dict) and entity not in ['macro avg', 'weighted avg', 'micro avg']:
                analysis['entity_performance'].append({
                    'entity': entity,
                    'precision': metrics.get('precision', 'N/A'),
                    'recall': metrics.get('recall', 'N/A'),
                    'f1-score': metrics.get('f1-score', 'N/A'),
                    'support': metrics.get('support', 0)
                })
        
        return analysis
    
    def analyze_diet_errors(self):
        """Analyse les erreurs DIETClassifier"""
        errors = self.load_json_file('DIETClassifier_errors.json')
        if not errors:
            return None
        
        return {
            'total_errors': len(errors),
            'sample_errors': errors[:5] if len(errors) > 5 else errors
        }
    
    def analyze_regex_extractor(self):
        """Analyse le RegexEntityExtractor"""
        report = self.load_json_file('RegexEntityExtractor_report.json')
        if not report:
            return None
        
        analysis = {
            'entities_detected': []
        }
        
        for entity, metrics in report.items():
            if isinstance(metrics, dict) and entity not in ['macro avg', 'weighted avg', 'micro avg']:
                analysis['entities_detected'].append({
                    'entity': entity,
                    'precision': metrics.get('precision', 'N/A'),
                    'recall': metrics.get('recall', 'N/A'),
                    'f1-score': metrics.get('f1-score', 'N/A'),
                    'support': metrics.get('support', 0)
                })
        
        return analysis
    
    def analyze_conflicting_synonyms(self):
        """Analyse les synonymes conflictuels"""
        conflicts = self.load_csv_file('conflicting_synonyms.csv')
        if not conflicts:
            return None
        
        return {
            'total_conflicts': len(conflicts),
            'conflicts': conflicts
        }
    
    def format_percentage(self, value):
        """Formate une valeur en pourcentage"""
        if isinstance(value, (int, float)):
            return f"{value:.2%}"
        return str(value)
    
    def format_decimal(self, value):
        """Formate une valeur décimale"""
        if isinstance(value, (int, float)):
            return f"{value:.4f}"
        return str(value)
    
    def generate_summary(self):
        """Génère un résumé complet de l'analyse"""
        print("=" * 80)
        print("ANALYSE DES RÉSULTATS DE TEST RASA NLU")
        print("=" * 80)
        print()
        
        # Analyse des intentions
        print("📊 ANALYSE DES INTENTIONS")
        print("-" * 80)
        intent_analysis = self.analyze_intent_report()
        if intent_analysis:
            print(f"✓ Accuracy globale: {self.format_percentage(intent_analysis['accuracy'])}")
            print(f"✓ F1-Score (macro): {self.format_percentage(intent_analysis['macro_avg_f1'])}")
            
            if intent_analysis['low_performing_intents']:
                print(f"\n⚠️  INTENTIONS À AMÉLIORER ({len(intent_analysis['low_performing_intents'])}):")
                sorted_intents = sorted(intent_analysis['low_performing_intents'], 
                                      key=lambda x: x['f1-score'] if isinstance(x['f1-score'], (int, float)) else 0)
                for intent in sorted_intents:
                    print(f"  • {intent['name']}: F1={self.format_percentage(intent['f1-score'])}, "
                          f"Precision={self.format_percentage(intent['precision'])}, "
                          f"Recall={self.format_percentage(intent['recall'])}, "
                          f"Support={intent['support']}")
            
            if intent_analysis['high_performing_intents']:
                print(f"\n✅ INTENTIONS PERFORMANTES ({len(intent_analysis['high_performing_intents'])}):")
                for intent in intent_analysis['high_performing_intents'][:3]:
                    print(f"  • {intent['name']}: F1={self.format_percentage(intent['f1-score'])}")
        else:
            print("⚠️  Fichier intent_report.json non trouvé")
        print()
        
        # Erreurs d'intentions
        print("❌ ERREURS D'INTENTIONS")
        print("-" * 80)
        intent_errors = self.analyze_intent_errors()
        if intent_errors:
            print(f"Total d'erreurs: {intent_errors['total_errors']}")
            if intent_errors['error_patterns']:
                print("\nPatterns d'erreurs les plus fréquents:")
                sorted_patterns = sorted(intent_errors['error_patterns'].items(), 
                                       key=lambda x: len(x[1]), reverse=True)
                for pattern, examples in sorted_patterns[:5]:
                    print(f"  • {pattern} ({len(examples)} fois)")
                    if examples:
                        text_preview = examples[0]['text'][:60]
                        if len(examples[0]['text']) > 60:
                            text_preview += "..."
                        print(f"    Exemple: \"{text_preview}\" "
                              f"(confiance: {self.format_percentage(examples[0]['confidence'])})")
        else:
            print("✓ Aucune erreur ou fichier intent_errors.json non trouvé")
        print()
        
        # Analyse DIETClassifier
        print("🧠 ANALYSE DIETCLASSIFIER (Entités)")
        print("-" * 80)
        diet_analysis = self.analyze_diet_report()
        if diet_analysis:
            perf = diet_analysis['overall_performance']
            if perf:
                print(f"Performance globale:")
                print(f"  Precision: {self.format_decimal(perf.get('precision', 'N/A'))}")
                print(f"  Recall: {self.format_decimal(perf.get('recall', 'N/A'))}")
                print(f"  F1-Score: {self.format_decimal(perf.get('f1-score', 'N/A'))}")
            
            if diet_analysis['entity_performance']:
                print("\nPerformance par entité:")
                sorted_entities = sorted(diet_analysis['entity_performance'], 
                                       key=lambda x: x.get('f1-score', 0) if isinstance(x.get('f1-score'), (int, float)) else 0)
                for entity in sorted_entities:
                    f1 = entity['f1-score']
                    indicator = "⚠️ " if (isinstance(f1, (int, float)) and f1 < 0.7) else "✓ "
                    print(f"  {indicator}{entity['entity']}: "
                          f"F1={self.format_decimal(f1)}, "
                          f"P={self.format_decimal(entity['precision'])}, "
                          f"R={self.format_decimal(entity['recall'])}, "
                          f"Support={entity['support']}")
        else:
            print("⚠️  Fichier DIETClassifier_report.json non trouvé")
        print()
        
        # RegexEntityExtractor
        print("🔍 ANALYSE REGEX ENTITY EXTRACTOR")
        print("-" * 80)
        regex_analysis = self.analyze_regex_extractor()
        if regex_analysis and regex_analysis['entities_detected']:
            for entity in regex_analysis['entities_detected']:
                print(f"  • {entity['entity']}: "
                      f"F1={self.format_decimal(entity['f1-score'])}, "
                      f"Support={entity['support']}")
        else:
            print("  Aucune entité détectée par regex ou fichier non trouvé")
        print()
        
        # Synonymes conflictuels
        print("⚡ SYNONYMES CONFLICTUELS")
        print("-" * 80)
        synonyms = self.analyze_conflicting_synonyms()
        if synonyms and synonyms['total_conflicts'] > 0:
            print(f"⚠️  {synonyms['total_conflicts']} conflits détectés!")
            print("Les premiers conflits:")
            for i, conflict in enumerate(synonyms['conflicts'][:5], 1):
                print(f"  {i}. {conflict}")
        else:
            print("✓ Aucun conflit de synonymes détecté ou fichier vide")
        print()
        
        # Recommandations
        self.generate_recommendations(intent_analysis, intent_errors, diet_analysis)
    
    def generate_recommendations(self, intent_analysis, intent_errors, diet_analysis):
        """Génère des recommandations d'amélioration"""
        print("💡 RECOMMANDATIONS D'AMÉLIORATION")
        print("=" * 80)
        
        recommendations = []
        
        # Recommandations sur les intentions
        if intent_analysis and intent_analysis['low_performing_intents']:
            recommendations.append("1. AMÉLIORER LES INTENTIONS FAIBLES:")
            for intent in intent_analysis['low_performing_intents'][:3]:
                recommendations.append(f"   - Ajouter plus d'exemples pour '{intent['name']}' "
                                     f"(actuellement {intent['support']} exemples)")
                recommendations.append(f"     → Diversifier les formulations et le vocabulaire")
                
                # Recommandations spécifiques selon les métriques
                precision = intent.get('precision', 0)
                recall = intent.get('recall', 0)
                if isinstance(precision, (int, float)) and isinstance(recall, (int, float)):
                    if precision < recall:
                        recommendations.append(f"     → La précision est faible: vérifier les faux positifs")
                    elif recall < precision:
                        recommendations.append(f"     → Le recall est faible: ajouter plus d'exemples variés")
        
        # Recommandations sur les erreurs
        if intent_errors and intent_errors['total_errors'] > 0:
            recommendations.append("\n2. CORRIGER LES CONFUSIONS FRÉQUENTES:")
            error_patterns = intent_errors.get('error_patterns', {})
            sorted_patterns = sorted(error_patterns.items(), key=lambda x: len(x[1]), reverse=True)
            for pattern, examples in sorted_patterns[:3]:
                recommendations.append(f"   - Pattern '{pattern}' ({len(examples)} erreurs)")
                recommendations.append(f"     → Revoir les exemples d'entraînement pour différencier ces intentions")
                recommendations.append(f"     → Ajouter des contre-exemples explicites")
        
        # Recommandations sur les entités
        if diet_analysis and diet_analysis['entity_performance']:
            low_entities = [e for e in diet_analysis['entity_performance'] 
                          if isinstance(e.get('f1-score'), (int, float)) and e['f1-score'] < 0.7]
            if low_entities:
                recommendations.append("\n3. AMÉLIORER L'EXTRACTION D'ENTITÉS:")
                for entity in low_entities[:3]:
                    recommendations.append(f"   - Entité '{entity['entity']}': "
                                         f"F1={self.format_decimal(entity['f1-score'])}")
                    recommendations.append(f"     → Vérifier la cohérence des annotations")
                    recommendations.append(f"     → Ajouter plus d'exemples annotés avec cette entité")
        
        # Recommandations générales
        if not recommendations:
            recommendations.append("✅ Votre modèle performe bien globalement!")
            recommendations.append("   Continuez à surveiller les métriques et à enrichir vos données.")
        else:
            recommendations.append("\n4. BONNES PRATIQUES GÉNÉRALES:")
            recommendations.append("   - Équilibrer le nombre d'exemples entre les différentes intentions")
            recommendations.append("   - Utiliser la validation croisée pour évaluer la robustesse")
            recommendations.append("   - Analyser régulièrement les nouvelles erreurs en production")
            recommendations.append("   - Documenter les cas limites et ambiguïtés")
        
        for rec in recommendations:
            print(rec)
        print("=" * 80)


# Utilisation
if __name__ == "__main__":
    # Remplacez par le chemin vers votre dossier de résultats de test
    test_folder = "."  # ou le chemin complet vers votre dossier
    
    print("🔍 Démarrage de l'analyse des résultats RASA NLU...")
    print(f"📁 Dossier analysé: {os.path.abspath(test_folder)}")
    print()
    
    analyzer = RasaTestAnalyzer(test_folder)
    analyzer.generate_summary()
    
    print("\n✅ Analyse terminée!")