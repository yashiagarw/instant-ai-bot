# Evaluation cases

Each `*.yaml` file here is a list of cases; case ids become `<file stem>:<id>`. Besides these files, the harness
generates cases from the dataset (see `../README.md`).

```yaml
- id: tyre-flat-1                 # unique within the file
  type: free_text                 # chips | free_text | overlap | unlisted | safety (default: free_text with
                                  #   text, else chips)
  source: synthetic               # dataset | generated | synthetic (default) | mechanic
  lang: hinglish                  # en | hinglish | hi | typo (default: hi for Devanagari, else en)
  vehicle:                        # optional: make, model, year, fuel, transmission, segment, listed
    fuel: petrol
    segment: budget
    listed: false
  group: tyres                    # optional: tile, emergency topic or inspection code
  category: tyre                  # optional: category chosen inside the tile
  text: "tyre puncture ho gaya"   # optional free text
  answers:                        # optional; exact approved question text and option label
    - question: "What problem are you facing with your tyre?"
      option: "The tyre is fully or almost fully flat"
  expected: [F04-TY-03]           # fault keys; any of them counts as right (a single key is fine)
  expected_coverage: segment_estimate   # optional: a level or a list of accepted levels
  expected_alert: high            # optional: high / medium / low (an alert at least that serious), or none
  simulate: true                  # optional; default: true for text or a tile without answers (not safety)
  note: "where this case came from"
```

Cases need `expected`, `expected_alert`, or both. Synthetic files (`synthetic_*.yaml`) were written to fill gaps
(Hindi, typos, unlisted cars, safety texts): replace them with real or mechanic-checked cases when available.
