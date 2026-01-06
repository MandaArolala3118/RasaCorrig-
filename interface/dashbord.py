# fichier : dashboard_rasa.py
import os
import json
import subprocess
import streamlit as st

nlu_folder = "data/nlu"
domain_file = "domain/domain.yml"
results_folder = "results"

# Créer le dossier results s'il n'existe pas
os.makedirs(results_folder, exist_ok=True)

st.title("Dashboard de fiabilité du modèle Rasa")

results_data = []

for filename in os.listdir(nlu_folder):
    if filename.endswith(".yml") or filename.endswith(".yaml"):
        nlu_file = os.path.join(nlu_folder, filename)
        result_path = os.path.join(results_folder, filename.replace(".yml","").replace(".yaml",""))
        os.makedirs(result_path, exist_ok=True)

        # Tester le NLU
        command = [
            "rasa", "test", "nlu",
            "--nlu", nlu_file,
            "--domain", domain_file,
            "--out", result_path
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            st.error(f"Erreur lors du test de {filename}")
            continue

        # Lire le fichier JSON pour l'accuracy
        result_json_path = os.path.join(result_path, "evaluation", "intent_report.json")
        if os.path.exists(result_json_path):
            with open(result_json_path, "r") as f:
                data = json.load(f)
                overall_acc = data.get("accuracy", None)
                if overall_acc is not None:
                    results_data.append({"Fichier": filename, "Accuracy (%)": round(overall_acc*100, 2)})
                else:
                    results_data.append({"Fichier": filename, "Accuracy (%)": "Non trouvé"})
        else:
            results_data.append({"Fichier": filename, "Accuracy (%)": "Fichier introuvable"})

# Afficher les résultats
if results_data:
    st.subheader("Résultats des tests NLU")
    st.table(results_data)

    # Calcul de la moyenne globale
    accuracies = [r["Accuracy (%)"] for r in results_data if isinstance(r["Accuracy (%)"], float)]
    if accuracies:
        st.subheader(f"Fiabilité globale du modèle : {sum(accuracies)/len(accuracies):.2f}%")
