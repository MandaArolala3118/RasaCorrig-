#!/usr/bin/env python3
"""Generate reports for duplicate NLU examples and conflicting synonyms.
Outputs:
 - results/duplicate_examples.csv (example, intents (pipe-separated), files)
 - results/conflicting_synonyms.csv (synonym, targets (pipe-separated), files)
"""
import os
import yaml
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NLU_DIR = os.path.join(ROOT, "data", "nlu")
OUT_DIR = os.path.join(ROOT, "results")
os.makedirs(OUT_DIR, exist_ok=True)

example_map = defaultdict(lambda: {"intents": set(), "files": set()})
syn_map = defaultdict(lambda: {"targets": set(), "files": set()})

for fname in os.listdir(NLU_DIR):
    if not fname.endswith(".yml") and not fname.endswith(".yaml"):
        continue
    path = os.path.join(NLU_DIR, fname)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Skipping {path}: YAML load error: {e}")
        continue
    if not data:
        continue
    # Rasa NLU files usually have a top-level 'nlu' list
    nlu_items = data.get("nlu") if isinstance(data, dict) else None
    if not nlu_items:
        # try if file itself is a list
        if isinstance(data, list):
            nlu_items = data
    if not nlu_items:
        continue
    for item in nlu_items:
        if not isinstance(item, dict):
            continue
        # intents + examples
        if "intent" in item:
            intent = item.get("intent")
            examples = item.get("examples") or item.get("example") or item.get("text")
            if examples:
                if isinstance(examples, str):
                    # YAML block style with lines starting with '-'
                    for line in examples.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("-"):
                            ex = line.lstrip("- ").strip()
                        else:
                            ex = line
                        if ex:
                            key = ex.strip()
                            example_map[key]["intents"].add(intent)
                            example_map[key]["files"].add(fname)
        # synonyms - two common forms: 'synonym' or 'synonyms' or 'entity_synonyms'
        if "synonym" in item:
            # item like {"synonym": "target", "examples": "|- ..."}
            target = item.get("synonym")
            examples = item.get("examples")
            if examples and isinstance(examples, str):
                for line in examples.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("-"):
                        s = line.lstrip("- ").strip()
                    else:
                        s = line
                    if s:
                        syn_map[s]["targets"].add(target)
                        syn_map[s]["files"].add(fname)
        if "synonyms" in item:
            # item may be like {'synonyms': [{'value': 'X', 'synonyms': ['a','b']}, ...]} but not standard.
            syns = item.get("synonyms")
            # if it's a mapping
            if isinstance(syns, dict):
                for k,v in syns.items():
                    # v could be a list of synonyms mapping to k
                    if isinstance(v, list):
                        for s in v:
                            syn_map[s]["targets"].add(k)
                            syn_map[s]["files"].add(fname)
        # old-style entity_synonyms mapping may appear under key 'entity_synonyms' as list
        if "entity_synonyms" in item:
            es = item.get("entity_synonyms")
            if isinstance(es, list):
                for pair in es:
                    if isinstance(pair, dict):
                        for target, vals in pair.items():
                            if isinstance(vals, list):
                                for s in vals:
                                    syn_map[s]["targets"].add(target)
                                    syn_map[s]["files"].add(fname)

# Write duplicate examples CSV
dup_path = os.path.join(OUT_DIR, "duplicate_examples.csv")
with open(dup_path, "w", encoding="utf-8") as out:
    out.write("example,intents,files\n")
    for ex, info in sorted(example_map.items(), key=lambda x: (-len(x[1]["intents"]), x[0])):
        if len(info["intents"]) > 1:
            intents = "|".join(sorted(info["intents"]))
            files = "|".join(sorted(info["files"]))
            # escape double quotes
            out.write('"%s","%s","%s"\n' % (ex.replace('"','""'), intents, files))

# Write conflicting synonyms CSV (same surface mapped to multiple targets)
syn_path = os.path.join(OUT_DIR, "conflicting_synonyms.csv")
with open(syn_path, "w", encoding="utf-8") as out:
    out.write("surface,targets,files\n")
    for s, info in sorted(syn_map.items(), key=lambda x: (-len(x[1]["targets"]), x[0])):
        if len(info["targets"]) > 1:
            targets = "|".join(sorted(info["targets"]))
            files = "|".join(sorted(info["files"]))
            out.write('"%s","%s","%s"\n' % (s.replace('"','""'), targets, files))

print(f"Wrote {dup_path} and {syn_path}")
