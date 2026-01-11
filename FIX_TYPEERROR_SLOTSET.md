# Correction du bug TypeError dans flux_recrutement_handler

## L'erreur

```
TypeError: isinstance() arg 2 must be a type, a tuple of types, or a union
```

**Cause** : À la ligne 381, le code utilisait `isinstance(slot_event, SlotSet)` mais cela causait une erreur de type.

## La solution

Au lieu de :
```python
if isinstance(slot_event, SlotSet):
```

Utiliser :
```python
if hasattr(slot_event, 'key') and hasattr(slot_event, 'value'):
```

## Explication

- `isinstance()` vérifie si un objet est instance d'une classe
- `hasattr()` vérifie si un objet a un attribut
- L'approche `hasattr()` est plus robuste ("duck typing") : si ça quacke comme un SlotSet, c'est un SlotSet

## Fichier modifié

- `actions/handlers/flux_recrutement_handler.py` ligne 381

## Impact

✅ Le code devrait maintenant fonctionner sans cette erreur TypeError
✅ Les slots nom_flux et nom_flux_id seront correctement extraits et synchronisés
