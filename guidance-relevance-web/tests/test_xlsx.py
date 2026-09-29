from io import BytesIO

from openpyxl import load_workbook

from guidance_relevance_web.xlsx import (
    pages_from_kept,
    parse_workbook,
    split_kept_dropped,
    workbook_bytes,
)

OUTPUT = [
    {
        "url": "https://www.gov.uk/guidance/keep",
        "content_id": "c1",
        "meta_data": {
            "title": "Keep me",
            "is_withdrawn": True,
            "labels": {"slurry": True},
            "funnel": {"stage": "pass2_keep", "pass1_reason": "yes", "pass2_reason": "keep"},
        },
    },
    {
        "url": "https://www.gov.uk/guidance/drop",
        "content_id": "c2",
        "meta_data": {
            "title": "Drop me",
            "labels": {"slurry": False},
            "funnel": {"stage": "pass2_drop", "pass1_reason": "yes", "pass2_reason": "incidental"},
        },
    },
]


def test_split_and_round_trip_accounting():
    kept, dropped = split_kept_dropped(OUTPUT, "slurry")
    assert [r["url"] for r in kept] == ["https://www.gov.uk/guidance/keep"]
    assert [r["url"] for r in dropped] == ["https://www.gov.uk/guidance/drop"]
    assert kept[0]["is_withdrawn"] is True
    assert dropped[0]["is_withdrawn"] is False
    data = workbook_bytes(kept, dropped)
    wb = load_workbook(BytesIO(data), data_only=True)
    assert [c.value for c in next(wb["kept"].iter_rows(min_row=1, max_row=1))][3] == "is_withdrawn"
    assert wb["kept"]["D2"].value is True
    assert wb["dropped"]["D2"].value is False
    wb.close()
    kept2, dropped2 = parse_workbook(data)
    assert kept2[0]["url"] == kept[0]["url"]
    assert dropped2[0]["funnel_stage"] == "pass2_drop"

    original = {r["url"] for r in kept}
    promoted = dict(dropped[0])
    kept_rows = [dict(kept[0]), promoted]
    payload = pages_from_kept(kept_rows, original)
    assert payload["accounting"]["n_added"] == 1
    assert payload["accounting"]["n_removed"] == 0
    assert payload["pages"][1]["content_id"] == "c2"

    deleted = pages_from_kept([], original)
    assert deleted["accounting"]["n_removed"] == 1
    assert deleted["accounting"]["n_pages"] == 0


def test_rejects_non_govuk_add():
    try:
        pages_from_kept([{"url": "https://example.com/x", "title": "", "content_id": ""}], set())
    except ValueError:
        return
    raise AssertionError("expected ValueError")
