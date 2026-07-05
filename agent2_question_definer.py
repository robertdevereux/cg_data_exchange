"""
agent2_question_definer.py
==========================
Agent 2 of the form-ingestion pipeline.

INPUT:  The plain-text Questions/Sections/Routing file produced and reviewed
        after Agent 1.
        The original PDF form (used for guidance text, hint text, and option
        wording directly from the form).

OUTPUT: A YAML file containing full question definitions only. Sections and
        routing are already defined in the Agent 1 output and do not need
        to be reproduced here.

Usage:
    python agent2_question_definer.py <read_txt> <pdf_path> [--output <output.yaml>]

Example:
    python agent2_question_definer.py IHT405_read.txt IHT405.pdf
    python agent2_question_definer.py IHT405_read.txt IHT405.pdf --output IHT405_questions.yaml

Dependencies:
    pip install anthropic pdfplumber
    ANTHROPIC_API_KEY must be set in environment (e.g. in .env)
"""

import argparse
import os
import sys

import anthropic
import pdfplumber

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a question definer for a UK government digital services platform.

You will be given:
  1. A plain-text file with three sections — Questions, Sections, and Routing —
     produced and reviewed by a human analyst. This is your authoritative source
     for what questions exist. Do not add, remove, reorder, or rename any
     questions. Do not alter the sections or routing — you will not reproduce
     them in your output.
  2. The full text of the original PDF form. Use this only to extract guidance
     text, hint text, option wording, and validation rules. Do not use it to
     change the question list or routing in any way.

Your job is to produce a YAML file containing three top-level blocks:
sections, routing, and questions.

The sections and routing blocks are transcribed directly from the Agent 1
input — convert them from the plain-text format into clean YAML. Do not
alter, add, or remove any sections or routing rules.

The questions block contains full question definitions, one per Q in the
input Questions list, in the same order.

=============================================================================
BLOCK 1: sections
=============================================================================

Transcribe every S line from the input Sections block into YAML.

Format:

sections:
  - ref: S1
    type: basic
    title: "Details of the deceased"
    question_refs: [Q1, Q2, Q3]

Fields:
  ref           The S reference (S1, S2 etc.)
  type          The section type from the input: basic, table, or
                conditional_table — copy exactly as given.
  title         The quoted section title from the input — copy exactly.
  question_refs The list of Q refs from the input, in order.

Do not add, remove, or alter any sections.

=============================================================================
BLOCK 2: routing
=============================================================================

Transcribe every routing rule from the input Routing block into YAML.

Format:

routing:
  - section: S1
    current_q: Q1
    condition_q: null
    condition_answer: null
    next_q: Q2

  - section: S2
    current_q: Q4
    condition_q: null
    condition_answer: "Yes"
    next_q: Q5

Fields:
  section           S ref
  current_q         Q ref of the question just answered
  condition_q       Q ref whose answer determines the route, or null.
                    Copy exactly from the input — null when the input
                    shows null, a Q ref when the input shows one.
  condition_answer  The answer in double quotes, or null
  next_q            Q ref of the next question, or END

Do not alter, add, or remove any routing rules.

=============================================================================
BLOCK 3: questions
=============================================================================

QUESTION FIELDS
=============================================================================

For every Q in the input, produce:

questions:
  - ref: Q1
    box: null
    question_id: HMRC_1
    question_text: "..."
    type: radio
    options: []
    guidance: ""
    hint: ""
    required: true
    currency: false
    validation: ""
    notes: ""

ref
  The Q reference from the input (Q1, Q2 etc.). Required.

box
  The box_ref from the input (1, 6B, null etc.). Required.

question_id
  Assign sequentially: HMRC_1, HMRC_2 etc.
  Questions where field 4 (nav) = NAV: HMRC_N1, HMRC_N2 etc.
  Questions where field 5 (question text) is a header label
  (name of deceased, date of death etc.): HMRC_H1, HMRC_H2 etc.
  Platform questions (see below): keep their P_N id.

question_text
  The question as shown to the citizen. GDS style:
    - Plain English, second person
    - One thing per question
    - "Did the deceased..." / "What is..." / "Was the..."
    - Remove form references ("as listed in column A above" etc.)
    - For TABLE COL questions: use a short column header label
      (e.g. "Item number", "Open market value") — these are column
      headers, not full page questions.
    - For HEADER questions: plain labels ("Name of the deceased").
    - For NAV questions: keep the citizen-facing question from the
      input, refining wording only if needed for clarity.

type
  One of: radio, radio_inline, checkbox, text, textarea, number,
  date, personal_name, address, compound.

  radio         single choice, one per line, own page
  radio_inline  single choice inline (use for TABLE questions — field 3
                = TABLE — that offer a named choice. Do NOT use text
                for these.)
  checkbox      multi-select
  text          single line free text
  textarea      multi-line free text (use for open narrative,
                descriptions, details)
  number        numeric
  date          day/month/year
  personal_name title, first name, last name
  address       line1, line2, city, county, postcode
  compound      multi-field — define sub-fields in notes.
              IMPORTANT: never use compound when Agent 1 has already
              split a name+address into two separate Q lines with the
              same box_ref. In that case assign personal_name to the
              name question and address to the address question.
              compound is only for genuinely novel multi-field inputs
              that do not fit any other type.

  CRITICAL RULE — radio vs text:
  If a question or table column presents a choice between named
  options — even if the form column heading does not make this
  explicit — ALWAYS use radio (for standalone questions) or
  radio_inline (for TABLE COL questions). NEVER use text for
  a field where the citizen must choose between defined options.

  Examples that must be radio or radio_inline, not text:
    - "Tenure" where the options are Freehold / Leasehold
    - "Sale status" where options are Already sold / On market / Will be sold
    - Any Yes/No field
    - Any field where the form says "tick one" or lists options

  Use radio for BASIC questions, radio_inline for TABLE questions.
  A TABLE question marked NAV (field 4) that has named options must
  always be radio_inline — it is a within-row branch point.

options
  List of options for radio and radio_inline types.
  For Yes/No always use exactly: ["Yes", "No"]
  For richer options use plain English from the form.
  Empty list [] for all other types.
  IMPORTANT: whenever type is radio or radio_inline, options must
  be populated — never leave options empty for these types.

guidance
  Explanatory text shown above the question. Draw from the form's
  own guidance notes where they exist, paraphrased into plain
  English. Omit if self-explanatory. Do not reproduce legal
  citations verbatim — paraphrase. Empty string if not needed.

hint
  Short hint below the question label. Format examples
  ("For example, 31 3 1980") or very brief clarification.
  Must be shorter than guidance. Empty string if not needed.

required
  true unless the form marks the field as optional or "if applicable".

currency
  true for all monetary/currency number fields. false otherwise.
  Only meaningful when type is number; set false for all other types.

validation
  Specific validation rules for the developer. Examples:
    "Must be a valid UK postcode"
    "Must be on or before date of death"
  Empty string if standard type validation applies.

notes
  Residual uncertainty or developer notes. Use rather than guessing.
  Flag anything the human reviewer should check. Empty string if none.

=============================================================================
PLATFORM QUESTIONS
=============================================================================

If a question maps exactly to an existing platform question (P_1 to P_6),
use this abbreviated form:

  - ref: Q6
    box: 2
    question_id: P_1
    platform_question: P_1
    notes: "Maps to P_1 (personal name). Refers to contact, not citizen."

Existing platform questions:
  P_1  Personal name (title, first name, last name)
  P_2  Address (line1, line2, city, county, postcode)
  P_3  Date of birth
  P_4  Email address
  P_5  Mobile number
  P_6  Landline number

Only map to a platform question if the semantic match is exact — same
subject, same person. A contact's name is NOT P_1 (P_1 is the citizen's
own name). A third-party address is NOT P_2. When in doubt, create a
department question.

=============================================================================
OUTPUT FORMAT
=============================================================================

Produce a single valid YAML file with exactly three top-level blocks in
this order: sections, routing, questions.

No markdown code fences. No commentary outside the YAML.
No extra keys beyond those defined above.
Produce only valid YAML.

If uncertain about any field value, use the notes field rather than guessing.
"""

# ---------------------------------------------------------------------------
# Helper: extract text from PDF
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from a PDF using pdfplumber."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                pages.append(f"--- Page {i} ---\n{text}")
    return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# Helper: call Claude
# ---------------------------------------------------------------------------

def call_claude(system: str, user_message: str, model: str = "claude-sonnet-4-6") -> str:
    """Call the Anthropic API and return the response text."""
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent 2 — Question Definer. Takes reviewed Agent 1 output "
                    "and PDF, outputs full question definitions as YAML."
    )
    parser.add_argument("read_txt", help="Path to the reviewed Agent 1 output text file")
    parser.add_argument("pdf_path", help="Path to the original PDF form")
    parser.add_argument(
        "--output", "-o",
        help="Output YAML file path (default: <txt_name>_questions.yaml)",
        default=None
    )
    parser.add_argument(
        "--model", "-m",
        help="Claude model to use (default: claude-sonnet-4-6)",
        default="claude-sonnet-4-6"
    )
    args = parser.parse_args()

    # Resolve output path
    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.read_txt))[0]
        output_path = f"{base}_questions.yaml"

    # Load the Agent 1 text file
    print(f"Loading Agent 1 output from {args.read_txt}...")
    try:
        with open(args.read_txt, "r", encoding="utf-8") as f:
            read_text = f.read().strip()
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)

    # Extract PDF text
    print(f"Extracting text from {args.pdf_path}...")
    try:
        pdf_text = extract_pdf_text(args.pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    if not pdf_text.strip():
        print("Warning: no text extracted from PDF.")
        sys.exit(1)

    print(f"Extracted {len(pdf_text)} characters from PDF.")

    # Build user message
    user_message = f"""Please produce full YAML question definitions for the form
described in the input below. Output the questions block only — do not
reproduce sections or routing.

The Questions/Sections/Routing text is your authoritative source for what
questions exist and their order. The form text is for reference only —
use it for guidance text, hint text, options, and validation rules.

QUESTIONS / SECTIONS / ROUTING:
{read_text}

ORIGINAL FORM TEXT:
{pdf_text}
"""

    # Call Claude
    print(f"Calling Claude ({args.model})...")
    try:
        yaml_output = call_claude(SYSTEM_PROMPT, user_message, model=args.model)
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        sys.exit(1)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(yaml_output)

    print(f"\nDone. Combined YAML written to: {output_path}")
    print("\nNext step: review and edit sections, routing, and questions,")
    print("then pass this single file to agent3_code_generator.py")


if __name__ == "__main__":
    main()
