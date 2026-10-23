# Evaluation cases

Each `*.yaml` file in this folder is a list of cases. `run_eval.py` runs every case through the engine and
reports top-1 / top-3 accuracy per category (Phase 1 categories separately).

```yaml
- id: tyre-flat-1                 # unique within the file
  vehicle:                        # optional; any of: make, model, year, fuel, transmission, segment, listed
    fuel: petrol
    segment: budget
  group: tyres                    # optional: tile, emergency topic or inspection code
  category: tyre                  # optional: category chosen inside the tile
  text: "tyre puncture ho gaya"   # optional free text
  answers:                        # optional; exact approved question text and option label
    - question: "What problem are you facing with your tyre?"
      option: "The tyre is fully or almost fully flat"
  expected: F04-TY-03             # fault key that should rank first
```

`examples.yaml` holds two worked examples. Add real cases (for example from support chats or mechanic
feedback) in new files.
