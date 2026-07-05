"""
agent1_structural_analyst.py
============================
Agent 1 of the form-ingestion pipeline.

INPUT:  A PDF file (path provided as command-line argument)
        Optional: a plain-text guidance file containing your structural
        observations about the form before the agent runs.
OUTPUT: A YAML file containing the structural annotation of the form —
        sections, navigation questions, and question inventory.

The output is intended for human review and editing before being passed
to Agent 2 (Question Definer).

Usage:
    python agent1_structural_analyst.py <path_to_pdf> [--guidance <guidance.txt>] [--output <output_yaml>]

Examples:
    # Run without guidance — agent makes its own structural judgments
    python agent1_structural_analyst.py forms/IHT413.pdf

    # Run with your upfront guidance — agent treats it as authoritative
    python agent1_structural_analyst.py forms/IHT405.pdf --guidance guidance/IHT405_notes.txt

    # Specify output path explicitly
    python agent1_structural_analyst.py forms/IHT413.pdf --output iht413_structure.yaml

The guidance file is plain English — no special format required. Use it to:
  - Flag repeating structures the agent might miss
  - Suggest how sections should be grouped or split
  - Note cross-references between boxes (e.g. item numbers in box 8
    refer back to rows in box 6)
  - Override the agent's default structural choices

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
# System prompt — describes the platform model and what Agent 1 must produce
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a structural analyst for a UK government digital services platform.

Your job is to read a scanned or digital UK government tax or benefit form (provided
as extracted text) and produce a YAML structural annotation that will later be used
to configure the form as a digital service on the platform.

## The platform model

The platform captures citizen answers to government questions via a routing engine.
The key concepts you need to understand are:

**Question**
A single question asked of the citizen. Has a type (see below), optional guidance
text, optional hint text, and options (for radio/checkbox types). Questions are
either platform questions (shared across all departments — P_1 to P_6, covering
name, address, DOB, email, phone) or department questions (specific to one department,
e.g. HMRC).

Platform questions that already exist:
  P_1  What is your name?              (type: personal_name)
  P_2  What is your address?           (type: address)
  P_3  What is your date of birth?     (type: date)
  P_4  What is your email address?     (type: text)
  P_5  What is your mobile number?     (type: text)
  P_6  What is your landline number?   (type: text)

If any question on the form maps exactly to one of these, note that in your output
(platform_question: P_1 etc.) rather than defining a new question.

**Question types:**
  radio        — single choice from a list of options (use for Yes/No and other
                 single-choice questions). On its own page.
  radio_inline — single choice Yes/No rendered inline (use in question sets only)
  checkbox     — multi-select from a list of options
  text         — free text, single line
  textarea     — free text, multiple lines (use for open narrative boxes)
  number       — numeric input (currency values, counts etc.)
  date         — day/month/year input (use for all date fields)
  personal_name — compound: title, first name, last name
  address      — compound: line1, line2, city, county, postcode
  compound     — user-defined multi-field (use sparingly; define components)
  table        — multiple rows of structured data (e.g. list of assets with
                 description and value columns)

**Section**
A coherent set of questions on a single subject, presented one question at a time,
with a confirmation page at the end. A section must be one of three types:

  basic             — questions with single answers (all types except table).
                      One question per page, linear or branching routing.
                      Example: personal details, a single Yes/No decision.

  table             — the citizen enters multiple rows of identical structured
                      data. Every row has the same fixed columns. No conditional
                      questions within a row — all columns are always asked.
                      Example: a flat list of bank accounts (bank name, account
                      number, balance).

  conditional_table — the citizen enters multiple rows of data, but the questions
                      asked within each row depend on the answers given during
                      that row. Routing logic (identical to basic section routing)
                      applies within each row. All answers — both unconditional
                      and conditional — are stored together in the same JSON row.
                      After the citizen completes a row and clicks ADD ROW, a
                      summary table is shown. The admin configures which columns
                      appear in the summary (typically the key identifying fields
                      plus simple Yes/No flags for any conditional branches).
                      Full conditional detail is accessible via an 'Other details'
                      link on each row rather than cluttering the summary columns.

Use conditional_table when ALL of the following are true:
  1. The form asks for multiple items of the same kind (properties, assets,
     partnerships etc.) — i.e. the section is inherently repeating per item.
  2. Within each item, some questions are only relevant depending on an earlier
     answer for that item (e.g. "Was this property damaged?" → if Yes, ask
     insurance questions; if No, skip them).
  3. The conditional questions logically belong to the same row as the item
     they qualify — they are per-item detail, not a separate subject.
  4. The form uses item numbers or row references to link the conditional
     questions back to the main table rows (a strong signal that the form
     designer intended this per-item relationship).

IHT405 boxes 6 and 7 are the canonical example: each property row carries
unconditional columns (address, tenure, values) plus conditional branches for
special factors (boxes 8/9/10, only if the property has issues affecting value)
and sale details (box 11, only if the property has been or will be sold). The
item numbers in boxes 8 and 11 are explicit back-references to rows in boxes
6 and 7 — a clear signal of conditional_table structure.

Do NOT use conditional_table for:
  - Simple flat tables with no conditional questions within a row (use table)
  - Sections where the conditional questions belong to a different subject
    and would be better as a separate gated section (use basic + navigation)
  - Single-answer questions even if they have complex routing (use basic)

A section cannot mix basic and table/conditional_table questions at the
top level. If a form box contains a flat table alongside basic questions,
split them into separate sections. If a form box contains a table where
some rows trigger follow-up questions for that row, use conditional_table.

**Schedule**
An optional grouping of sections. Use when multiple sections belong to a common
subject area (e.g. "Partnership details" covering several sections).

**Navigation question**
A gateway question that determines whether a section or group of sections is
relevant to this citizen. Navigation questions are full questions in their own
right (type: radio, options: Yes/No or similar). They sit outside the sections
they gate and route the citizen accordingly.

Example: "Did the deceased hold any interest in a business or partnership?"
  Yes → show business sections
  No  → skip to next part of the return

**Routing**
Within a section, each question can route to the next question conditionally
(based on the citizen's answer) or unconditionally. Routing is defined at
question level, not section level. You do not need to define full routing in
this output — just note where conditional routing exists (e.g. "Yes → go to
box 7, No → go to box 3").

## Repeating structures

Some forms are designed to be completed once per item (e.g. once per business
interest, once per property). Note this at form level and/or section level.
Some sections within a form may also repeat (e.g. partnership details, once
per partnership). Note these repeating sub-structures explicitly.

## What to produce

Produce a YAML file with the following structure:

```yaml
form:
  title: "Human-readable form title"
  hmrc_ref: "IHT413"  # or equivalent
  repeating: false     # true if the whole form repeats per item
  repeat_unit: ""      # e.g. "business interest" if repeating: true
  notes: ""            # any structural observations for the human reviewer

sections:
  - ref: S1            # internal pipeline ref only — not a platform ID
    name: "Short descriptive name"
    type: basic        # basic, table, or conditional_table
    gateway_ref: N1    # ref of the navigation question that gates this section
                       # omit if always shown
    repeating: false   # true if this section repeats (e.g. once per partnership)
    repeat_unit: ""    # e.g. "partnership" if repeating: true
    form_boxes: [1, 2, 3]   # the form box numbers included in this section
    summary_columns: []      # for conditional_table only: list the form box
                             # numbers/labels that should appear as visible
                             # summary columns after ADD ROW. Omit for basic/table.
                             # Example: [6A, 6B, 6C, 6H, 8_flag, 11_flag]
                             # where _flag denotes a Yes/No summary of a
                             # conditional branch rather than the full detail.
    notes: ""          # anything the human reviewer should consider

navigation:
  - ref: N1
    question: "Full text of the gateway question"
    type: radio        # almost always radio
    options: [Yes, No] # or richer options if needed
    consequences:
      Yes: [S1, S2]    # section refs shown if Yes
      No: []           # section refs shown if No
    notes: ""

question_inventory:
  # A flat list of all form boxes, for human review.
  # Agent 2 will flesh these out into full question definitions.
  - box: 1
    form_text: "Exact or near-exact text of the question as it appears on the form"
    type_hint: radio   # your best guess at the question type
    platform_question: ""  # fill in e.g. P_1 if this maps to a platform question
    notes: ""          # e.g. "conditional on box 1 = Yes", "table with 2 columns"
```

## Rules

1. Every form box must appear in exactly one section AND in the question_inventory.
2. Navigation questions appear in the navigation block AND in the question_inventory
   (with a ref like N1 in the box field).
3. Sections must be basic, table, or conditional_table — never mixed. If you find
   a table box in an otherwise basic section, split it out.
4. If the form repeats per item, set form.repeating: true and note the repeat_unit.
5. If a section within the form repeats, set section.repeating: true.
6. Where the form text says "Go to box N" or "If Yes, go to..." note this in the
   question_inventory notes field. Do not try to define full routing here.
7. Where a question clearly maps to a platform question (P_1 to P_6), say so.
8. If you are uncertain about anything, use the notes field rather than guessing.
9. Produce only valid YAML. No markdown code fences, no commentary outside the YAML.
10. A strong signal for conditional_table is when later boxes use item numbers or
    row references that point back to rows in an earlier table box. When you see
    this pattern, absorb the later boxes as conditional columns within the earlier
    table section rather than creating separate sections for them.
11. For conditional_table sections, populate summary_columns with your best guess
    at which columns the admin would want visible in the row summary — typically
    the key identifying field (address, name, description), any currency totals,
    and one Yes/No flag per conditional branch. Full conditional detail goes
    behind 'Other details', not in summary_columns.

## Human reviewer guidance

If the user message contains a HUMAN REVIEWER GUIDANCE section, treat it as
authoritative. It contains structural decisions made by someone with domain
knowledge of both the form and the platform. Prefer it over your own inference
in all cases where it speaks to a structural question. Where it is silent,
use your own judgment and note any uncertainty in the notes fields.
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
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

    response = client.messages.create(
        model=model,
        max_tokens=4096,
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
        description="Agent 1 — Structural Analyst. Reads a PDF form and outputs a YAML structural annotation."
    )
    parser.add_argument("pdf_path", help="Path to the PDF form")
    parser.add_argument(
        "--guidance", "-g",
        help="Path to a plain-text file containing your structural guidance for this form (optional)",
        default=None
    )
    parser.add_argument(
        "--output", "-o",
        help="Output YAML file path (default: <pdf_name>_structure.yaml)",
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
        base = os.path.splitext(os.path.basename(args.pdf_path))[0]
        output_path = f"{base}_structure.yaml"

    # Extract PDF text
    print(f"Extracting text from {args.pdf_path}...")
    try:
        pdf_text = extract_pdf_text(args.pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    if not pdf_text.strip():
        print("Warning: no text extracted from PDF. The file may be a scanned image.")
        print("Consider running OCR before using this script.")
        sys.exit(1)

    print(f"Extracted {len(pdf_text)} characters of text.")

    # Load optional guidance file
    guidance_text = ""
    if args.guidance:
        print(f"Loading guidance from {args.guidance}...")
        try:
            with open(args.guidance, "r", encoding="utf-8") as f:
                guidance_text = f.read().strip()
        except Exception as e:
            print(f"Error reading guidance file: {e}")
            sys.exit(1)

    # Build user message
    guidance_block = ""
    if guidance_text:
        guidance_block = f"""
HUMAN REVIEWER GUIDANCE:
{guidance_text}

Treat the above guidance as authoritative. Where it speaks to a structural
decision, follow it. Where it is silent, use your own judgment.

"""

    user_message = f"""
Please analyse the following UK government form and produce a YAML structural
annotation following the format described in your instructions.
{guidance_block}
FORM TEXT:
{pdf_text}
"""

    # Call Claude
    if guidance_text:
        print(f"Calling Claude ({args.model}) with guidance...")
    else:
        print(f"Calling Claude ({args.model}) — no guidance provided, agent will use its own judgment...")
    try:
        yaml_output = call_claude(SYSTEM_PROMPT, user_message, model=args.model)
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        sys.exit(1)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(yaml_output)

    print(f"\nDone. Structural annotation written to: {output_path}")
    print("\nNext step: review and edit the YAML, then pass it to agent2_question_definer.py")


if __name__ == "__main__":
    main()
