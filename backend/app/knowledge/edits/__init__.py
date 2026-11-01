"""Knowledge editors (admin app): every save is an override on top of the imported data (knowledge_edits).

- handlers.py: one handler per item type (category, problem group, fault, fault lines, phrase, question, safety rule,
  media links, photo label). snapshot() reads an item's state in a version, write() makes it so.
- apply.py: re-applies the published edits and a draft's own edits to a version (a pipeline step after every import),
  reporting conflicts (the import changed an edited field too) and orphans (the edited item is gone).
- service.py: save, revert, sign off, publish (the draft's edits become part of the live knowledge).
- taxonomy.py: the taxonomy per version (taxonomy.yaml + edits) and syncing the live tables from it.
"""
