# Bootstrap eval baseline (Phase 5.6)

`quick.json` is the CI quick eval (`python -m app.datasets.ci_eval run --scope quick`) of `main` at ec2d2ab, taken
from CI run 42368365705 (3,125 cases; 9 of 800 danger cases missed, top-3 75.05%). The pull-request eval gate uses
it **only when no baseline from `main` is cached yet** (before Phase 5.6 is merged, or after the Actions cache was
cleared). After every push to `main`, that run's own report becomes the baseline instead, so this file never needs
updating; refresh it only if the cache is regularly empty.
