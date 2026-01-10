# Configuration file for the Sphinx documentation builder.

import sys
from pathlib import Path
import tomllib

# Add the package to the path so autodoc can find it
sys.path.insert(0, str(Path(__file__).parent.parent))

# Read metadata from pyproject.toml
with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)["project"]

project = pyproject["name"]
author = pyproject["authors"][0]["name"]
release = pyproject["version"]
copyright = f"2026, {author}"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.mathjax",
    "myst_parser",
]

myst_enable_extensions = [
    "dollarmath",
    "amsmath",
]

html_theme = "furo"

autodoc_member_order = "bysource"
autodoc_typehints = "description"
