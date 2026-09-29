from guidance_proposition_extractor.fetch import FetchedPage
from guidance_proposition_extractor.models import GuidanceProposition
from guidance_proposition_extractor.provenance import attach_provenance


def test_attach_provenance_sets_section_locators():
    page = FetchedPage(
        url="https://www.gov.uk/x",
        title="X",
        description="",
        body_text="Intro.\nYou must store slurry.\nMore.",
        sections=[
            ("section:intro", ["Intro."]),
            ("section:rules", ["You must store slurry.", "More."]),
        ],
    )
    props = [
        GuidanceProposition(
            proposition_text="A farmer must store slurry safely.",
            source_paragraphs=["You must store slurry."],
        )
    ]
    out, misses = attach_provenance(props, page)
    assert misses == 0
    assert out[0].section_locators == ["section:rules"]


def test_attach_provenance_counts_verbatim_misses():
    page = FetchedPage(
        url="https://www.gov.uk/x",
        title="X",
        description="",
        body_text="Real text on the page.",
        sections=[("section:body", ["Real text on the page."])],
    )
    props = [
        GuidanceProposition(
            proposition_text="Hallucinated obligation.",
            source_paragraphs=["This paragraph does not exist."],
        )
    ]
    out, misses = attach_provenance(props, page)
    assert misses == 1
    assert out[0].section_locators == []
