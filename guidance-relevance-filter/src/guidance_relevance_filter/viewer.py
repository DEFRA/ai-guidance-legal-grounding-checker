"""Streamlit UI: upload a URL CSV + a GRF run artifact, download the annotated CSV."""
from __future__ import annotations

import streamlit as st

from guidance_relevance_filter.annotate import (
    STAGE_GUIDE,
    AnnotateError,
    annotate_rows,
    index_payload,
    read_csv_text,
    resolve_url_column,
    write_csv_string,
)

st.set_page_config(page_title="Guidance Relevance Filter — explain", layout="wide")
st.title("Explain a URL list against a relevance-filter run")
st.caption(
    "Upload a CSV of URLs and a finished run's `output.json` or `funnel.json`. "
    "Each row gets `funnel_stage` and `funnel_reason`."
)

with st.expander("What the stages mean (top of the funnel first)", expanded=True):
    st.markdown(
        "The filter is a **funnel**. Each URL falls out at the first stage that "
        "rejects it; only survivors reach the next stage. "
        "`pass2_keep` and `pass2_unadjudicated` are both 'made it through' — "
        "not a further drop."
    )
    st.table(
        [
            {"order": i, "stage": stage, "means": label, "in plain English": meaning}
            for i, (stage, label, meaning) in enumerate(STAGE_GUIDE, start=1)
        ]
    )

csv_file = st.file_uploader("URL CSV", type=["csv"])
run_file = st.file_uploader("GRF artifact (`output.json` or `funnel.json`)", type=["json"])
url_column = st.text_input(
    "URL column (blank = url / Original URL / clened-urls)",
    value="",
)

if csv_file and run_file:
    try:
        rows, fields = read_csv_text(csv_file.getvalue().decode("utf-8-sig"))
        column = resolve_url_column(fields, url_column.strip() or None)
        index = index_payload(run_file.name, run_file.getvalue())
        annotated, out_fields, counts = annotate_rows(rows, fields, index, column)
    except AnnotateError as e:
        st.error(str(e))
    except UnicodeDecodeError:
        st.error("CSV is not valid UTF-8")
    else:
        st.subheader("Stage counts")
        guide = {stage: label for stage, label, _meaning in STAGE_GUIDE}
        ordered = [stage for stage, _label, _meaning in STAGE_GUIDE if counts.get(stage)]
        extras = [stage for stage in counts if stage not in guide]
        st.table(
            [
                {"stage": stage, "n": counts[stage], "means": guide.get(stage, "")}
                for stage in [*ordered, *extras]
            ]
        )
        st.caption(f"URL column: `{column}` · {len(annotated)} rows")
        st.subheader("Preview")
        st.dataframe(annotated, use_container_width=True)
        stem = csv_file.name.rsplit(".", 1)[0]
        st.download_button(
            "Download annotated CSV",
            data=write_csv_string(annotated, out_fields),
            file_name=f"{stem}-funnel.csv",
            mime="text/csv",
        )
