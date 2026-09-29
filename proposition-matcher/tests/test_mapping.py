from proposition_matcher.pipeline.mapping import guidance_from_guidance_proposition_extractor_entry, guidance_from_guidance_proposition_extractor_output


def test_maps_susan_entry_to_guidance_propositions():
    entry = {
        "url": "https://www.gov.uk/x",
        "content_id": "cid-x",
        "meta_data": {
            "title": "X",
            "propositions": [
                {"proposition_text": "A farmer must store slurry safely.", "actor": "farmer",
                 "regulatory_kind": "statutory_obligation", "source_paragraphs": ["You must store slurry…"],
                 "section_locators": ["section:storage", "section:rules"]},
                {"proposition_text": "Records must be kept.", "actor": "", "source_paragraphs": "single string"},
            ],
        },
    }
    gps = guidance_from_guidance_proposition_extractor_entry(entry)
    assert [g.proposition_text for g in gps] == ["A farmer must store slurry safely.", "Records must be kept."]
    assert gps[0].legal_subject == "farmer"                 # actor -> legal_subject
    assert gps[0].regulatory_kind == "statutory_obligation" # regulatory_kind carried through
    assert gps[0].content_id == "cid-x"
    assert gps[0].section_locator == "section:storage; section:rules"
    assert gps[1].legal_subject == "you"                    # blank actor -> default
    assert gps[1].regulatory_kind == ""                     # absent -> empty
    assert gps[1].source_paragraphs == ["single string"]    # str coerced to list
    assert gps[1].section_locator == ""
    assert all(g.source_url == "https://www.gov.uk/x" for g in gps)
    assert gps[0].id != gps[1].id


def test_flattens_whole_output():
    out = [
        {"url": "u1", "meta_data": {"propositions": [{"proposition_text": "a"}]}},
        {"url": "u2", "meta_data": {"propositions": [{"proposition_text": "b"}, {"proposition_text": "c"}]}},
    ]
    assert len(guidance_from_guidance_proposition_extractor_output(out)) == 3
