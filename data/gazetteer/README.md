# Ontario place-name data

`cgn_on_places.csv` is a compact offline derivative of Natural Resources
Canada's Canadian Geographical Names Data Base (CGNDB). It retains populated
places and administrative areas from the weekly Ontario CSV distribution; the
larger downloaded ZIP is cached under `cache/` and excluded from Git.

Refresh the derivative from the repository root with:

```powershell
python scripts/build_gazetteer.py --refresh
```

Without `--refresh`, the builder works offline from the last verified cache and
does not check whether NRCan has published a newer weekly archive. It verifies
the cached archive against `source.json` before parsing it.

`source.json` records the exact URL, response metadata, checksum, retrieval
time, row counts, and licence for the downloaded snapshot. The build refuses an
unexpected ZIP layout or CSV header so a source-format change cannot silently
shift columns into plausible-looking coordinates.

`amalgamations.json` is a separately sourced, small historical layer. A current
gazetteer coordinate is not a validity interval: in CGNDB, a decision date can
record several kinds of naming action, so `places.py` does not manufacture
historical start or end years from that field.

Contains information from the Canadian Geographical Names Data Base (CGNDB),
Natural Resources Canada, licensed under the [Open Government Licence -
Canada](https://open.canada.ca/en/open-government-licence-canada). See the
[official CGNDB catalogue
record](https://open.canada.ca/data/en/dataset/e27c6eba-3c5d-4051-9db2-082dc6411c2c).

The source database contains historical terminology that may be racist,
offensive, or derogatory. Source spellings and identifiers should be preserved
for historical fidelity, while user-facing products should carry the official
CGNDB content advisory and appropriate context.
