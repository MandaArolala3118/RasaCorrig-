import os
import subprocess
import json

# Dossiers
nlu_folder = "data/nlu"
domain_file = "domain"  # chemin vers le domain
results_folder = "results"

# Créer le dossier results s'il n'existe pas
os.makedirs(results_folder, exist_ok=True)

# Parcourir tous les fichiers du dossier data/nlu
for filename in os.listdir(nlu_folder):
    if filename.endswith(".yml") or filename.endswith(".yaml"):
        nlu_file = os.path.join(nlu_folder, filename)
        print(f"\n=== Test NLU pour : {filename} ===")

        # Créer un dossier de résultats spécifique
        result_path = os.path.join(results_folder, filename.replace(".yml","").replace(".yaml",""))
        os.makedirs(result_path, exist_ok=True)

        # Commande pour tester le NLU avec le domain spécifié
        command = [
            "rasa", "test", "nlu",
            "--nlu", nlu_file,
            "--out", result_path,
            "--domain", domain_file
        ]

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Erreur lors du test de {filename}: {e}")
            continue

        # Lire le fichier JSON généré pour récupérer l'accuracy
        result_json_path = os.path.join(result_path, "evaluation", "intent_report.json")
        if os.path.exists(result_json_path):
            with open(result_json_path, "r") as f:
                data = json.load(f)
                overall_acc = data.get("accuracy", None)
                if overall_acc is not None:
                    print(f"Accuracy pour {filename}: {overall_acc*100:.2f}%")
                else:
                    print("Accuracy non trouvée dans le fichier JSON.")
        else:
            print("Fichier evaluation/intent_report.json introuvable.")
