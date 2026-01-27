"""
Utility functions for scraping.
Adapted from Reference/author/openalex/match-author-openalex.js
"""

import re
from typing import List


# Academic title prefixes (from reference code)
TITLE_PREFIX = [
    "prof", "prof.",
    "dr", "dr.",
    "ir", "ir.",
    "hj", "h.", "h"
]

# Academic title suffixes (from reference code)
TITLE_SUFFIX = [
    "s.t", "st",
    "s.kom", "skom",
    "m.kom", "mkom",
    "m.t", "mt",
    "m.sc", "msc",
    "ph.d", "phd",
    "m.si", "msi",
    "m.m", "mm",
    "s.si", "ssi",
    "s.pd", "spd",
    "s.e", "se",
    "m.m.", "m.pd",
    "drs", "drs.",
]


def strip_titles(name: str) -> str:
    """
    Remove academic titles from name.
    Adapted from Reference/author/openalex/match-author-openalex.js normalizeName()
    
    Args:
        name: Original name with possible titles
        
    Returns:
        Name with titles stripped
    """
    n = name.lower().replace(",", " ")
    
    # Remove prefixes
    removed = True
    while removed:
        removed = False
        for title in TITLE_PREFIX:
            pattern = rf"^{re.escape(title)}\s+"
            if re.match(pattern, n, re.IGNORECASE):
                n = re.sub(pattern, "", n, flags=re.IGNORECASE)
                removed = True
    
    # Remove suffixes
    removed_suffix = True
    while removed_suffix:
        removed_suffix = False
        for title in TITLE_SUFFIX:
            pattern = rf"[\s,]+{re.escape(title)}$"
            if re.search(pattern, n, re.IGNORECASE):
                n = re.sub(pattern, "", n, flags=re.IGNORECASE)
                removed_suffix = True
    
    return re.sub(r"\s+", " ", n).strip()


def normalize_name(name: str) -> str:
    """
    Normalize a name for comparison.
    Adapted from Reference/jurnal/crossref/main.js normalizeName()
    
    - Converts to lowercase
    - Removes non-alphabetic characters except spaces
    - Collapses multiple spaces
    
    Args:
        name: Original name
        
    Returns:
        Normalized name for comparison
    """
    n = name.lower()
    # Remove non-alphabetic characters except spaces
    n = re.sub(r"[^a-z\s]", "", n)
    # Collapse multiple spaces
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def clean_name_for_query(name: str) -> str:
    """
    Clean name for API query - strip titles and normalize.
    
    Args:
        name: Original name
        
    Returns:
        Cleaned name suitable for API query
    """
    return strip_titles(name)


def is_exact_match(name1: str, name2: str) -> bool:
    """
    Check if two names are an exact match after normalization.
    
    Args:
        name1: First name
        name2: Second name
        
    Returns:
        True if names match after normalization
    """
    return normalize_name(name1) == normalize_name(name2)


def extract_author_full_name(author_obj: dict) -> str:
    """
    Extract full name from Crossref author object.
    
    Args:
        author_obj: Author object from Crossref API
        
    Returns:
        Full name as "given family"
    """
    given = author_obj.get("given", "") or ""
    family = author_obj.get("family", "") or ""
    return f"{given} {family}".strip()


def is_unikom_affiliated(author_obj: dict) -> bool:
    """
    Check if author has UNIKOM affiliation.
    Adapted from Reference/jurnal/crossref/main.js isExactAuthorFromUNIKOM()
    
    Args:
        author_obj: Author object from Crossref API with affiliation list
        
    Returns:
        True if author has UNIKOM affiliation
    """
    affiliations = author_obj.get("affiliation", [])
    for aff in affiliations:
        aff_name = normalize_name(aff.get("name", ""))
        if "universitas komputer indonesia" in aff_name or "unikom" in aff_name:
            return True
    return False


def parse_date_parts(date_parts: List[List[int]]) -> str:
    """
    Parse Crossref date-parts format to string.
    
    Args:
        date_parts: List of date part lists, e.g., [[2024, 1, 15]]
        
    Returns:
        Date string like "2024-1-15"
    """
    if not date_parts or not date_parts[0]:
        return ""
    parts = date_parts[0]
    return "-".join(str(p) for p in parts)
