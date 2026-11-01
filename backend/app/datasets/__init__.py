"""Dataset publish pipeline: upload a category file, validate, diff, evaluate, publish, roll back (admin Datasets
page). pipeline.py has the flow; jobs.py and worker.py run it in the background (arq on Redis)."""
