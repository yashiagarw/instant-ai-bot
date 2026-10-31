# Parts and labour price templates

Use these to add price sources for the files that have no PARTS_PRICE_SOURCES sheet (1-8, 10, 11, 13, 15-17). The
columns are the same as the PARTS_PRICE_SOURCES sheet of files 12, 14 and 18, so rows can be copied between them.

1. Copy a template into `data/catalogue/parts/` and name it after the dataset file it belongs to:
   - `part_price_sources.csv` → `data/catalogue/parts/F07-part_price_sources.csv`
   - `labour_rates.csv` → `data/catalogue/parts/F07-labour_rates.csv`
2. Fill one row per part and segment (save as CSV, UTF-8).
3. Rebuild the catalogue: `cd backend && uv run python -m app.parts build`. The output table shows what was loaded for
   each file, and `data/review/parts/fit-unmatched.csv` lists fit text that names no model in the vehicle catalogue.

## part_price_sources.csv

| Column | What to write | Example |
|---|---|---|
| Key | Your own short code, unique within the file. `B_` / `M_` / `P_` for budget / mid / premium by convention | `B_STARTER` |
| Fault IDs using it | The file's own fault IDs, comma separated. Only these faults show the part | `SS-01, SS-04` |
| Segment | Budget, Mid-range or Premium | `Budget` |
| Vehicle (fit) | Which cars the source lists the part for. Name the model as in the vehicle catalogue, with years and fuel when the source gives them. Write `Budget car - check fit` (or Mid-range / Premium) when the source names no car. Add "confirm by VIN" when the source says so | `Maruti Swift 2024+ petrol (Maruti site)` |
| Part | Part name a customer understands | `Starter motor` |
| Manufacturer / brand | Brand on the box. `Any good brand` when it is not a specific brand | `Maruti Genuine` |
| OEM / aftermarket | `Genuine` (carmaker), `Aftermarket (OE supplier)`, `Aftermarket`, or `Genuine or good aftermarket` | `Genuine` |
| Part number | The maker's part number; `Model specific` when there is none. `x 3` for a set | `31100M68K00` |
| Price (INR) | Number only, no Rs or commas | `6200` |
| Price basis | What the price is | `MRP / website price` |
| Supplier | Where the price came from | `Maruti Genuine Parts website` |
| Source URL | Link to the page | |
| Date | Date the price was checked | `31-Oct-2026` |
| GST | `Incl. (as shown)`, `Excl.`, or `Assume incl. - confirm` | `Incl. (as shown)` |
| Fitting included? | `No - labour separate` or `Yes` | `No - labour separate` |
| Verification status | `Checked on Indian website`, `Listed price - recheck` or `APPROX - quotation needed` | `Checked on Indian website` |
| Picture ID | Picture code from the file's image index, if any | |
| Note | Anything a customer should know about the price or fit | |

A part is shown as fitting a customer's car only when the Vehicle (fit) text names that car's model (and its years
and fuel match). Everything else is shown as "fit not verified".

## labour_rates.csv

| Column | What to write | Example |
|---|---|---|
| Repair | The job | `Starter motor replace` |
| Budget (INR), Mid-range (INR), Premium (INR) | Numbers only. Write `0` when the job does not apply to that segment | `800`, `1200`, `2500` |
| Workshop type | | `Independent garage / dealer` |
| City | | `Delhi NCR` |
| Source / basis | Where the figure came from | |
| Date | Date checked | `31-Oct-2026` |
| Status | `APPROX` or `LISTED` | `APPROX` |
