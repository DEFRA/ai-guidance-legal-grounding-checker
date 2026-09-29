from xml.etree import ElementTree

from law_proposition_extractor_pipeline.sources.clml_text import serialize_clml_text


def _serialize(xml: str) -> str:
    root = ElementTree.fromstring(xml)
    body = root.find("Body")
    assert body is not None
    target = next(iter(body))
    return serialize_clml_text(target)


def test_schedule_paragraph_number_subparagraph_and_list_labels() -> None:
    text = _serialize(
        """
        <Legislation>
          <Body>
            <P2 id="schedule-1a-paragraph-18">
              <Pnumber>18.</Pnumber>
              <P3>
                <Pnumber>1</Pnumber>
                <Text>The occupier must—</Text>
                <P4>
                  <Pnumber>a</Pnumber>
                  <Text>make a record of livestock manure, and</Text>
                </P4>
                <P4>
                  <Pnumber>b</Pnumber>
                  <Text>assess and record the amount of nitrogen.</Text>
                </P4>
              </P3>
            </P2>
          </Body>
        </Legislation>
        """
    )

    assert text.startswith("18(1) The occupier must—")
    assert "(a) make a record of livestock manure, and (b) assess and record" in text
    assert "181The" not in text
    assert "amake" not in text
    assert "andbassess" not in text


def test_regulation_paragraph_number_before_prose() -> None:
    text = _serialize(
        """
        <Legislation>
          <Body>
            <P1 id="regulation-1">
              <Pnumber>1.</Pnumber>
              <Text>These Regulations come into force on 1 April 2019.</Text>
            </P1>
          </Body>
        </Legislation>
        """
    )

    assert text == "1. These Regulations come into force on 1 April 2019."


def test_inline_markup_does_not_split_words() -> None:
    text = _serialize(
        """
        <Legislation>
          <Body>
            <P1 id="regulation-4">
              <Text>spread livestock <InlineAmendment>m</InlineAmendment>anure on land</Text>
            </P1>
          </Body>
        </Legislation>
        """
    )

    assert "livestock manure" in text
    assert "m anure" not in text


def test_live_clml_ppara_wrappers_serialize_provision_and_paragraph_text() -> None:
    """Regression: legislation.gov.uk nests operative text under P1para/P2para wrappers."""
    root = ElementTree.fromstring(
        """
        <Legislation>
          <Body>
            <P1 id="regulation-36">
              <Pnumber>36.</Pnumber>
              <P1para>
                <P2 id="regulation-36-4">
                  <Pnumber>4</Pnumber>
                  <P2para>
                    <Text>The occupier must make a record of the calculations.</Text>
                  </P2para>
                </P2>
              </P1para>
            </P1>
          </Body>
        </Legislation>
        """
    )
    regulation = root.find("./Body/P1")
    paragraph = root.find("./Body/P1/P1para/P2")
    assert regulation is not None
    assert paragraph is not None

    regulation_text = serialize_clml_text(regulation)
    paragraph_text = serialize_clml_text(paragraph)

    assert "occupier must make a record" in regulation_text
    assert regulation_text != "(36)"
    assert paragraph_text.startswith("(4) The occupier must make a record")


def test_live_pnumber_without_trailing_dot_uses_provision_marker_for_p1() -> None:
    """Live legislation.gov.uk CLML often omits the trailing dot on P1 Pnumber nodes."""
    root = ElementTree.fromstring(
        """
        <Legislation>
          <Body>
            <P1 id="regulation-36">
              <Pnumber>36</Pnumber>
              <P1para>
                <P2 id="regulation-36-4">
                  <Pnumber>4</Pnumber>
                  <P2para>
                    <Text>The occupier must make a record of the calculations.</Text>
                  </P2para>
                </P2>
              </P1para>
            </P1>
          </Body>
        </Legislation>
        """
    )
    regulation = root.find("./Body/P1")
    paragraph = root.find("./Body/P1/P1para/P2")
    assert regulation is not None
    assert paragraph is not None

    regulation_text = serialize_clml_text(regulation)
    paragraph_text = serialize_clml_text(paragraph)

    assert regulation_text.startswith(
        "36. (4) The occupier must make a record of the calculations."
    )
    assert paragraph_text.startswith("(4) The occupier must make a record")


def test_article_and_rule_parent_provisions_use_dot_numbering() -> None:
    root = ElementTree.fromstring(
        """
        <Legislation>
          <Body>
            <P1 id="article-12">
              <Pnumber>12</Pnumber>
              <P1para>
                <Text>Article 12 overview.</Text>
              </P1para>
            </P1>
            <P1 id="rule-5">
              <Pnumber>5</Pnumber>
              <P1para>
                <Text>Rule 5 overview.</Text>
              </P1para>
            </P1>
          </Body>
        </Legislation>
        """
    )
    article = root.find("./Body/P1[@id='article-12']")
    rule = root.find("./Body/P1[@id='rule-5']")
    assert article is not None
    assert rule is not None

    assert serialize_clml_text(article).startswith("12. Article 12 overview.")
    assert serialize_clml_text(rule).startswith("5. Rule 5 overview.")


def test_sibling_pnumber_text_nodes_in_operative_paragraph() -> None:
    root = ElementTree.fromstring(
        """
        <Legislation>
          <Body>
            <P3 id="schedule-1a-paragraph-18">
              <Pnumber>1</Pnumber>
              <Text>The occupier must—</Text>
              <P4>
                <Pnumber>a</Pnumber>
                <Text>make a record; and</Text>
              </P4>
              <P4>
                <Pnumber>b</Pnumber>
                <Text>assess nitrogen.</Text>
              </P4>
            </P3>
          </Body>
        </Legislation>
        """
    )
    node = root.find("./Body/P3")
    assert node is not None
    text = serialize_clml_text(node)

    assert text.startswith("(1) The occupier must—")
    assert "(a) make a record; and (b) assess nitrogen." in text
