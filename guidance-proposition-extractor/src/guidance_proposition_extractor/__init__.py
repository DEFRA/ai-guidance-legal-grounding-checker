"""Guidance Proposition Extractor — atomic proposition extraction from GOV.UK guidance pages."""

from .extract import extract_propositions
from .fetch import FetchedPage, fetch
from .models import GuidanceProposition

__all__ = ["GuidanceProposition", "FetchedPage", "fetch", "extract_propositions"]
