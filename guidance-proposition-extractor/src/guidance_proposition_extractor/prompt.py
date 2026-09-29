"""The single production prompt.

Won the pairwise contest. The placeholders are filled by string replace
(not str.format) for symmetry with how this prompt used to embed a JSON
shape example. The structured output schema now lives in the tool
definition in ``extract.py`` — this prompt just describes what counts
as a proposition.
"""

PROMPT = """You are extracting legal propositions from a GOV.UK guidance page.

A proposition is:
- ATOMIC — one obligation, permission, prohibition, or statement of fact per
  proposition. If the source says "you must do A and B", emit two propositions,
  not one.
- TESTABLE — it can be evaluated true or false in isolation.
- SELF-CONTAINED — readable on its own. No "see section X". No deictic openers
  ("this regulation", "those animals"). Inline all relevant numbers and dates.
- BRIEF — typically 8–40 words.
- OPERATIVE — contains a modal verb (must, must not, may, shall, required,
  prohibited) OR is a clear statement of fact.

DO NOT emit signposts, procedural how-to steps presented as obligations,
headings/page titles, or compound obligations.

For each proposition, also extract these three metadata fields. They give
the proposition the context it needs to be useful in a list. Leave a field
empty if it's not clearly inferable from the page — do NOT guess.

- subject_area: the broad domain this guidance covers. 2–6 words.
  Examples: "avian influenza control", "landspreading permits", "nitrate
  vulnerable zones", "imports of equines". REUSE the same subject_area
  across propositions on the same page.

- instrument: the specific named licence, permit, regulation, online service,
  form, or scheme the obligation arises under or is performed against.
  Examples: "SR2010 No 4 landspreading permit", "EU Regulation 2016/429",
  "APHA online notification service", "Nitrate Vulnerable Zone Action
  Programme 2025". Empty if the page doesn't name one.

- actor: the role on which the obligation falls. Use the most specific role
  named on the page. Examples: "land manager", "poultry keeper", "licence
  holder", "operator of mobile plant", "competent authority". Avoid bare
  pronouns ("you", "they", "anyone") — resolve them to a named role.

- regulatory_kind: a single value from the closed vocabulary below describing
  the KIND of regulatory artefact this proposition came from. Pick the single
  best fit. Leave empty only if no value applies.
    * statutory_obligation — a duty imposed by primary or secondary
      legislation (Acts, Statutory Instruments, retained or replacing EU
      regulations). Example: "An occupier of land must notify APHA of
      suspected notifiable disease" (Animal Health Act 1981).
    * permit_requirement — a condition attached to a specific permit.
      Example: "The permit holder must not spread waste within 10 metres
      of a watercourse" (SR2010 No 4 landspreading permit).
    * grant_condition — an eligibility criterion or condition for a funding
      scheme. Example: "Slurry stores funded under the grant must provide
      at least 8 months of storage capacity" (Slurry Infrastructure Grant).
    * code_of_practice — a provision from a code of practice — guidance
      with persuasive but non-binding force. Example: "Operators should
      keep records of antibiotic use for at least 5 years" (Code of
      Practice on the Responsible Use of Antibiotics).
    * procedural_step — an instructional how-to step rather than a
      normative obligation. Example: "Sign in to the Rural Payments service
      to start an application."
    * factual_statement — a factual or background claim with no normative
      force. Example: "Bacteria can develop resistance to antibiotics over
      time."
    * definition — a defining clause that fixes the meaning of a term used
      in the regulatory body. Example: "A nitrate vulnerable zone is an
      area of land designated under the Nitrate Pollution Prevention
      Regulations 2015."

- derives_from: a list of strings naming the underlying legislation that this
  guidance proposition explicitly implements, as cited on the page. Copy the
  citation verbatim or near-verbatim from the page. NEVER guess. If the page
  does not name a legal basis for the proposition, return an empty list.
  Empty is the most common case and is the correct answer when in doubt.
  Examples of acceptable values:
    * ["Animal Health Act 1981, section 1"]
    * ["the Nitrate Pollution Prevention Regulations 2015"]
    * ["Regulation (EU) 2016/429"]
    * []

For source_paragraphs: list each verbatim paragraph or list-item this
proposition was drawn from. Never combine an intro paragraph with its bullets.

Call the `emit_propositions` tool with one entry per proposition.

Topic: {topic}
Source: {source_url}

Guidance text:
{body}"""


def render(body: str, source_url: str, topic: str = "guidance") -> str:
    """Substitute the three placeholders. Plain replace, not str.format —
    the prompt contains literal '{' and '}' that .format() would parse."""
    return (
        PROMPT
        .replace("{body}", body)
        .replace("{topic}", topic)
        .replace("{source_url}", source_url)
    )
