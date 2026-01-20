"""
Application Flask simplifiée - Proxy vers l'API .NET
Plus besoin de connexion directe à la base de données !
"""

from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import requests
import yaml
import io
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# 🔧 URL de votre API .NET (ASP.NET Core)
DOTNET_API_URL = 'https://localhost:7183'  # ← Changez selon votre port

# Configuration pour ignorer les erreurs SSL en développement
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def call_dotnet_api(endpoint):
    """Appeler l'API .NET"""
    try:
        url = f"{DOTNET_API_URL}/api/ChatHistory/{endpoint}"
        print(f"📡 Appel API: {url}")
        response = requests.get(url, verify=False, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Erreur API: {e}")
        raise

@app.route('/')
def index():
    """Page principale"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """Obtenir les statistiques globales"""
    try:
        print("\n=== API /api/stats appelée ===")
        stats = call_dotnet_api('stats')
        print(f"✅ Statistiques récupérées")
        return jsonify(stats)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users')
def get_users():
    """Obtenir la liste des utilisateurs"""
    try:
        print("\n=== API /api/users appelée ===")
        users = call_dotnet_api('users')
        print(f"✅ {len(users)} utilisateur(s) trouvé(s)")
        return jsonify(users)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations/<sender>')
def get_conversations(sender):
    """Obtenir l'historique de conversation d'un utilisateur"""
    try:
        print(f"\n=== API /api/conversations/{sender} appelée ===")
        limit = request.args.get('limit', 100)
        messages = call_dotnet_api(f'conversations/{sender}?limit={limit}')
        print(f"✅ {len(messages)} message(s) récupéré(s)")
        return jsonify(messages)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/yaml', methods=['POST'])
def export_yaml():
    """Exporter les conversations en format YAML pour Rasa test"""
    try:
        print("\n=== API /api/export/yaml appelée ===")
        data = request.json
        sender = data.get('sender')
        
        # Récupérer les données depuis l'API .NET
        messages = call_dotnet_api(f'export/yaml/{sender}')
        
        # Organiser les conversations
        conversations = []
        current_conversation = []
        
        for msg in messages:
            if msg['is_user']:
                current_conversation.append({
                    'user': msg['text'],
                    'timestamp': msg['timestamp']
                })
            else:
                if current_conversation:
                    current_conversation[-1]['bot'] = msg['text']
        
        # Créer le format YAML pour Rasa test stories
        test_stories = []
        story = {
            'story': f"{sender}_conversation",
            'steps': []
        }
        
        for msg in current_conversation:
            if 'user' in msg:
                story['steps'].append({'user': msg['user']})
            if 'bot' in msg:
                story['steps'].append({
                    'action': 'utter_response',
                    'expected': msg['bot']
                })
        
        test_stories.append(story)
        
        # Créer le fichier YAML
        yaml_content = yaml.dump(
            {'stories': test_stories},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
        
        # Créer un fichier en mémoire
        buffer = io.BytesIO()
        buffer.write(yaml_content.encode('utf-8'))
        buffer.seek(0)
        
        filename = f"test_stories_{sender}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yml"
        
        print(f"✅ Export YAML réussi: {filename}")
        
        return send_file(
            buffer,
            mimetype='text/yaml',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/nlu', methods=['POST'])
def export_nlu():
    """Exporter les messages utilisateur en format NLU pour Rasa"""
    try:
        print("\n=== API /api/export/nlu appelée ===")
        data = request.json
        sender = data.get('sender')
        
        # Récupérer les données depuis l'API .NET
        nlu_data = call_dotnet_api(f'export/nlu/{sender}')
        messages = nlu_data.get('messages', [])
        
        # Créer le format NLU
        nlu_yaml = {
            'nlu': [{
                'intent': 'user_messages',
                'examples': ''.join([f"- {msg}\n" for msg in messages])
            }]
        }
        
        # Créer le fichier YAML
        yaml_content = yaml.dump(
            nlu_yaml,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False
        )
        
        # Créer un fichier en mémoire
        buffer = io.BytesIO()
        buffer.write(yaml_content.encode('utf-8'))
        buffer.seek(0)
        
        filename = f"nlu_data_{sender}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yml"
        
        print(f"✅ Export NLU réussi: {filename}")
        
        return send_file(
            buffer,
            mimetype='text/yaml',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search')
def search_messages():
    """Rechercher dans les messages"""
    try:
        print("\n=== API /api/search appelée ===")
        query = request.args.get('q', '')
        sender = request.args.get('sender', '')
        
        url = f'search?q={query}'
        if sender:
            url += f'&sender={sender}'
        
        results = call_dotnet_api(url)
        print(f"✅ {len(results)} résultat(s) trouvé(s)")
        return jsonify(results)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    """Supprimer un message"""
    try:
        print(f"\n=== API /api/delete/{message_id} appelée ===")
        url = f"{DOTNET_API_URL}/api/ChatHistory/{message_id}"
        response = requests.delete(url, verify=False, timeout=10)
        response.raise_for_status()
        print(f"✅ Message {message_id} supprimé")
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 MouvPerso - Visualiseur de Conversations (Mode Proxy)")
    print("="*60)
    print(f"📡 API .NET: {DOTNET_API_URL}")
    print(f"🌐 Interface Flask: http://localhost:5002")
    print("="*60)
    print("\n⚠️  IMPORTANT: Démarrez votre API .NET AVANT Flask")
    print("\nAppuyez sur Ctrl+C pour arrêter\n")
    
    app.run(debug=True, host='0.0.0.0', port=5002)