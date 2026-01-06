#!/usr/bin/env python3
"""Apply conservative NLU fixes based on reports in results/:
- results/duplicate_examples.csv : remove example from intents with fewer examples
- results/conflicting_synonyms.csv : keep the most frequent target for each surface

Backups: when editing a file, create filename + '.bak' copy
"""
import os
import csv
import shutil
import re
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
NLU_DIR = os.path.join(ROOT, 'data', 'nlu')
RES_DIR = os.path.join(ROOT, 'results')
DUP = os.path.join(RES_DIR, 'duplicate_examples.csv')
SYN = os.path.join(RES_DIR, 'conflicting_synonyms.csv')

if not os.path.exists(DUP) and not os.path.exists(SYN):
    print('No reports found in results/. Run scripts/nlu_reports.py first.')
    raise SystemExit(1)

# Helper to load nlu YAML as text and perform line-based edits

def backup_file(path):
    bak = path + '.bak'
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f'Backup created: {bak}')


def remove_example_from_file(example_text, target_intent, filename):
    path = os.path.join(NLU_DIR, filename)
    if not os.path.exists(path):
        print('File not found:', path)
        return False
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    inside_intent = False
    current_intent = None
    for line in lines:
        stripped = line.strip()
        # detect intent header
        m = re.match(r"^-\s*intent:\s*(\S+)", stripped)
        if m:
            current_intent = m.group(1)
            inside_intent = (current_intent == target_intent)
            new_lines.append(line)
            continue
        # When inside the intent block and encountering examples block
        if inside_intent and re.match(r"^examples:\s*\|", stripped):
            # copy examples but skip lines matching the example
            new_lines.append(line)
            # consume following indented example lines
            idx = len(new_lines)
            # iterate the following lines from original
            continue
        new_lines.append(line)
    # Simpler approach: string replace of the example within the file
    text = ''.join(lines)
    # look for the example as a line like '- example' possibly with annotation
    # Escape special chars for regex
    ex = example_text.strip()
    # handle cases where example includes annotations like [..](entity)
    # We'll match the literal text inside the quotes from the CSV: exact match
    # The CSV contains examples as they appear, possibly with markdown annotations. We'll try to remove lines that contain the plain example text.
    pattern = re.compile(r'^\s*-\s*' + re.escape(ex) + r'\s*$', flags=re.MULTILINE)
    (new_text, nsubs) = pattern.subn('', text)
    if nsubs > 0:
        backup_file(path)
        # tidy up: remove duplicate empty lines
        new_text = re.sub(r'\n{3,}', '\n\n', new_text)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_text)
        print(f'Removed example from {filename}: "{ex}"')
        return True
    else:
        # Try to match without markdown annotations: remove line containing the plain example substring
        # Search any line starting with '-' that contains ex
        pattern2 = re.compile(r'^(\s*-\s*.*' + re.escape(ex) + r'.*)$', flags=re.MULTILINE)
        (new_text2, n2) = pattern2.subn('', text)
        if n2 > 0:
            backup_file(path)
            new_text2 = re.sub(r'\n{3,}', '\n\n', new_text2)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_text2)
            print(f'Removed example (fuzzy) from {filename}: "{ex}"')
            return True
    return False


def canonicalize_synonym(surface, chosen_target, files_list):
    # We will scan files and replace definitions mapping surface->other targets with chosen_target
    # Look for blocks like:
    # - synonym: TARGET
    #   examples: |
    #     - surface
    # or old-style entity_synonyms entries
    replaced_files = set()
    for fname in files_list:
        path = os.path.join(NLU_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        new_text = text
        # Replace any synonym mapping where surface is listed but target != chosen_target
        # Conservative: remove entries where surface maps to other targets by deleting the '- surface' line under that synonym
        # Pattern: - synonym: SOMETARGET\n  examples: |\n    - surface
        # We'll find all 'synonym' blocks and ensure surface appears only under chosen_target
        # First, find blocks for other targets that include surface and remove that surface line
        pattern_block = re.compile(r'(-\s*synonym:\s*(?P<target>.+?)\s*\n\s*examples:\s*\|\n(?P<lines>(?:\s*[-].*\n)+))', flags=re.IGNORECASE)
        for m in pattern_block.finditer(text):
            target = m.group('target').strip()
            block = m.group(0)
            lines = m.group('lines')
            # if surface present in lines and target != chosen_target
            if chosen_target != target and re.search(r'[-]\s*' + re.escape(surface) + r'\b', lines):
                # remove the line with surface
                new_lines = re.sub(r'(\n\s*[-]\s*' + re.escape(surface) + r'\b)', '\n', lines)
                new_block = re.sub(re.escape(lines), new_lines, block, count=1)
                new_text = new_text.replace(block, new_block)
        # Also handle entity_synonyms lists (old style)
        # e.g., - synonym: TARGET\n  examples: |\n    - s
        if new_text != text:
            backup_file(path)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_text)
            print(f'Canonicalized "{surface}" -> "{chosen_target}" in {fname}')
            replaced_files.add(fname)
    return replaced_files

# Process duplicate examples
if os.path.exists(DUP):
    with open(DUP, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ex = row['example']
            intents = row['intents'].split('|') if row['intents'] else []
            files = row['files'].split('|') if row['files'] else []
            # Heuristic: pick intent to keep = intent that appears in most files in this list
            # But we don't know counts; we'll count occurrences in NLU files by counting number of examples for each intent
            intent_counts = {}
            for intent in intents:
                # count examples for this intent across all files
                count = 0
                for fname in os.listdir(NLU_DIR):
                    if not fname.endswith('.yml'):
                        continue
                    p = os.path.join(NLU_DIR, fname)
                    with open(p, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    # crude count: occurrences of '- ' lines under intent header
                    pattern = re.compile(rf'-\s*{re.escape(ex.strip())}\s*', flags=re.IGNORECASE)
                    if pattern.search(txt):
                        count += 1
                intent_counts[intent] = count
            # choose intent to keep as the one with highest count, fallback to first
            keep = max(intent_counts.items(), key=lambda x: (x[1], x[0]))[0]
            # remove example from other intents
            for intent in intents:
                if intent == keep:
                    continue
                # find the filename(s) where this example appears for that intent - use provided files list
                for fname in files:
                    removed = remove_example_from_file(ex.strip().strip('"'), intent, fname)

# Process conflicting synonyms
if os.path.exists(SYN):
    with open(SYN, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            surface = row['surface']
            targets = row['targets'].split('|') if row['targets'] else []
            files = row['files'].split('|') if row['files'] else []
            # Heuristic: pick the most common target by scanning files for occurrences
            target_counts = defaultdict(int)
            for t in targets:
                for fname in files:
                    p = os.path.join(NLU_DIR, fname)
                    if not os.path.exists(p):
                        continue
                    with open(p, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    # count occurrences of target in synonym blocks
                    target_counts[t] += len(re.findall(rf'synonym:\s*{re.escape(t)}', txt, flags=re.IGNORECASE))
            if target_counts:
                chosen = max(target_counts.items(), key=lambda x: x[1])[0]
            else:
                chosen = targets[0] if targets else None
            if chosen:
                canonicalize_synonym(surface, chosen, files)

print('Done applying conservative fixes.')
