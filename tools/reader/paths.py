"""Every folder and file the project reads or writes, in one place.

neoperseus/
  assets/            fonts and images the site uses (not code)
  site/              the website
    code/            its CSS and JavaScript (the source)
    public/          the built site: what is deployed (generated)
    local/           the built overlay for this computer: catalog, private texts (generated)
    cache/           what each built site was made from (generated)
  corpus/            all the texts and what is needed to get more
    library/         finished texts: perseus/ (converted), own/ (published), private/ (never published)
    catalog/         everything for finding and importing texts: the catalogs, the reading list, the format
                     spec, inbox/ (raw files waiting), unsorted/, sources/ (downloaded raw material)
    reviews/         proofreading logs
  tools/             all the Python (this package is tools/reader) and the scripts
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
IMAGES = ASSETS / "images"

SITE = ROOT / "site"
SITE_CODE = SITE / "code"
SITE_PUBLIC = SITE / "public"
SITE_LOCAL = SITE / "local"
SITE_CACHE = SITE / "cache"

CORPUS = ROOT / "corpus"
LIBRARY = CORPUS / "library"
LIBRARY_PERSEUS = LIBRARY / "perseus"
LIBRARY_OWN = LIBRARY / "own"
LIBRARY_PRIVATE = LIBRARY / "private"
EDITS_TSV = LIBRARY / "edits.tsv"
REVIEWS = CORPUS / "reviews"

CATALOG = CORPUS / "catalog"
CATALOG_JSON = CATALOG / "catalog.json"            # every Perseus work (tools/make_catalog.py)
WIKISOURCE_JSON = CATALOG / "wikisource.json"      # Wikisource pairs (tools/wikisource_catalog.py)
GROUPS_TSV = CATALOG / "groups.tsv"                # how authors with many works are grouped
SHELF = CATALOG / "shelf.txt"                      # the Perseus reading list
SPEC = CATALOG / "SPEC.md"
INBOX = CATALOG / "inbox"                          # raw files waiting to be imported
UNSORTED = CATALOG / "unsorted"
SOURCES = CATALOG / "sources"                      # downloaded Perseus XML, dictionary sources
