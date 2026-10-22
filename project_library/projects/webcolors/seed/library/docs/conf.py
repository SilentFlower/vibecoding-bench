"""
Configuration file for the Sphinx documentation builder:

https://www.sphinx-doc.org/

"""

import doctest
import sys
from importlib.metadata import version as get_version

extensions = [
    "notfound.extension",
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinxext.opengraph",
    "sphinx_copybutton",
    "sphinx_inline_tabs",
]
templates_path = ["_templates"]
source_suffix = {".rst": "restructuredtext"}
master_doc = "index"
project = "webcolors"
copyright = "James Bennett and contributors"
version = get_version("webcolors")
release = version
exclude_trees = ["_build"]
pygments_style = "sphinx"
htmlhelp_basename = "webcolorsdoc"
latex_documents = [
    ("index", "webcolors.tex", "webcolors Documentation", "James Bennett", "manual"),
]
html_theme = "furo"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Spelling check needs an additional module that is not installed by default.  Add it
# only if spelling check is requested so docs can be generated without it.
if "spelling" in sys.argv:
    extensions.append("sphinxcontrib.spelling")

# Spelling language.
spelling_lang = "en_US"

# Location of word list.
spelling_word_list_filename = "spelling_wordlist.txt"

# The documentation does not include contributor names, so we skip this because it's
# flaky about needing to scan commit history.
spelling_ignore_contributor_names = False

# Doctest configuration.
doctest_global_setup = "from webcolors import *"
doctest_default_flags = (
    doctest.DONT_ACCEPT_TRUE_FOR_1
    | doctest.ELLIPSIS
    | doctest.IGNORE_EXCEPTION_DETAIL
    | doctest.NORMALIZE_WHITESPACE
)

# OGP metadata configuration.
ogp_enable_meta_description = True
ogp_site_url = "https://webcolors.readthedocs.io/"
