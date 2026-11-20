"""Every folder and file the project reads or writes, in one place. Change a name here and nowhere else.

neoperseus/
  assets/              fonts and images the site uses
  site/                the website: code/ (css, js), public/ (built, deployed), local/ (built overlay for this
                       computer), cache/ (what each built site was made from)
  corpus/
    library/           every text that is built. Texts that did not come from Perseus sit directly in it.
      perseus/         the preliminary corpus: converted from Perseus (generated)
      private/         texts that are never published
    dictionary/        LSJ, Lewis & Short, Greek forms (dict/) and the downloaded Perseus XML (greekLit, latinLit)
    catalog/           finding and importing: catalog.json, 0_inbox/ (raw files), 1_checkstage/ (drafts being
                       checked), sources/ (the Wikisource list)
    reviews/           proofreading logs
    continue_reading.txt   the Perseus works to keep up to date
  tools/               all the Python and the scripts
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---- what the site shows
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
IMAGES = ASSETS / "images"

# ---- the website
SITE = ROOT / "site"
SITE_CODE = SITE / "code"
SITE_PUBLIC = SITE / "public"
SITE_LOCAL = SITE / "local"
SITE_CACHE = SITE / "cache"

# ---- the texts
CORPUS = ROOT / "corpus"
LIBRARY = CORPUS / "library"                     # everything built; non-Perseus texts sit directly in it
LIBRARY_PERSEUS = LIBRARY / "perseus"            # converted from Perseus (generated)
LIBRARY_PRIVATE = LIBRARY / "private"            # never published
GROUPS_TSV = LIBRARY / "groups.tsv"              # how authors with many works are grouped on the library page
CONTINUE_READING = CORPUS / "continue_reading.txt"   # the Perseus works to keep up to date
REVIEWS = CORPUS / "reviews"

# ---- the dictionary and the Perseus XML it sits beside
DICTIONARY = CORPUS / "dictionary"
DICTIONARY_SOURCES = DICTIONARY / "dict"         # LSJ, Lewis & Short, Morpheus, downloaded once
PERSEUS_XML = DICTIONARY                         # greekLit/ and latinLit/ are downloaded here

# ---- finding and importing texts
CATALOG = CORPUS / "catalog"
CATALOG_JSON = CATALOG / "catalog.json"          # every Perseus work (tools/make_catalog.py)
INBOX = CATALOG / "0_inbox"                      # raw files waiting to be imported
CHECKSTAGE = CATALOG / "1_checkstage"            # drafts being checked
WIKISOURCE_DIR = CATALOG / "sources"
WIKISOURCE_JSON = WIKISOURCE_DIR / "wikisource.json"   # Wikisource pairs (tools/wikisource_catalog.py)
LIBRARY_FORMAT = CATALOG / "library_format.md"   # how texts are formatted, paired and finished
REVISION_CHECK = CATALOG / "0_revision_check.md" # the prompt that checks a text and writes the fix
