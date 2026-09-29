from guidance_proposition_extractor.models import GuidanceProposition


def test_proposition_round_trip():
    p = GuidanceProposition(
        proposition_text="A licence holder must record each movement within 24 hours.",
        subject_area="avian influenza control",
        instrument="EXD353(HPAI)(EW) general licence",
        actor="licence holder",
        source_paragraphs=["A licence holder must record each movement within 24 hours."],
        regulatory_kind="statutory_obligation",
        derives_from=["Animal Health Act 1981, section 1"],
    )
    data = p.model_dump()
    assert data["proposition_text"].startswith("A licence holder")
    assert data["regulatory_kind"] == "statutory_obligation"
    assert data["derives_from"] == ["Animal Health Act 1981, section 1"]
    p2 = GuidanceProposition(**data)
    assert p == p2


def test_proposition_defaults():
    p = GuidanceProposition(proposition_text="Foo.")
    assert p.subject_area == ""
    assert p.instrument == ""
    assert p.actor == ""
    assert p.source_paragraphs == []
    assert p.regulatory_kind == ""
    assert p.derives_from == []
    assert p.section_locators == []


def test_regulatory_kind_round_trip():
    p = GuidanceProposition(
        proposition_text="Slurry stores funded under the grant must provide at least 8 months of storage capacity.",
        regulatory_kind="grant_condition",
    )
    data = p.model_dump()
    assert data["regulatory_kind"] == "grant_condition"
    assert data["derives_from"] == []
    p2 = GuidanceProposition(**data)
    assert p == p2


def test_derives_from_empty_list_default():
    p = GuidanceProposition(
        proposition_text="Sign in to the Rural Payments service to start an application.",
        regulatory_kind="procedural_step",
    )
    assert p.derives_from == []
    data = p.model_dump()
    assert data["derives_from"] == []
    p2 = GuidanceProposition(**data)
    assert p2.derives_from == []


def test_derives_from_multiple_citations():
    p = GuidanceProposition(
        proposition_text="A nitrate vulnerable zone is an area of land designated under the regulations.",
        regulatory_kind="definition",
        derives_from=[
            "the Nitrate Pollution Prevention Regulations 2015",
            "Regulation (EU) 2016/429",
        ],
    )
    data = p.model_dump()
    assert data["derives_from"] == [
        "the Nitrate Pollution Prevention Regulations 2015",
        "Regulation (EU) 2016/429",
    ]
    p2 = GuidanceProposition(**data)
    assert p == p2
