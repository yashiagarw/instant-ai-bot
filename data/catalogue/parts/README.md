# Team price sources

Filled copies of the templates in `data/schema/templates/` go here, named after the dataset file:
`F07-part_price_sources.csv`, `F07-labour_rates.csv`. `cd backend && uv run python -m app.parts build` loads them
like the PARTS_PRICE_SOURCES and LABOUR_PRICE_RESEARCH sheets. See `data/schema/templates/README.md` for the columns.
