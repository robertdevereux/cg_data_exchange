"""
agent1_form_reader.py
=====================
Agent 1 of the form-ingestion pipeline.

INPUT:  A PDF file (path provided as command-line argument)
        Optional: a plain-text guidance file containing your observations
        about the form before the agent runs.

OUTPUT: A plain-text file with three sections:

        Questions   — one line per identified question:
                      Q{n}, {box_ref|null}, {BASIC|TABLE}, {NAV|""}, {question text}

        Sections    — one line per section:
                      S{n}, {type}, [Q{n}, Q{n}, ...], "Section title"

        Routing     — one line per routing rule:
                      S{n}, Q{current}, Q{condition}|null, {answer}|null, Q{next}|END

This output is intentionally minimal — just enough for human review and
correction before passing to Agent 2 (Question Definer).

Usage:
    python agent1_form_reader.py <path_to_pdf> [--guidance <guidance.txt>] [--output <output.txt>]

Examples:
    python agent1_form_reader.py forms/IHT405.pdf
    python agent1_form_reader.py forms/IHT413.pdf --guidance guidance/IHT413_notes.txt
    python agent1_form_reader.py forms/IHT405.pdf --output iht405_read.txt

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
You are a form reader for a UK government digital services platform.

You will be given the text of a UK government tax or benefit form. Your job
is to produce a structured plain-text output with exactly three sections:
Questions, Sections, and Routing.

This output will be reviewed and corrected by a human before being passed
to the next stage of processing. Keep it minimal and readable — no extra
commentary, no nested structures, no YAML or JSON.

After completing all three sections, you must run a series of self-consistency
checks (defined at the end of these instructions) and fix any errors before
producing your final output.

=============================================================================
SECTION 1: Questions
=============================================================================

List every question or data field on the form, one per line, in the order
they appear. Assign each a sequential reference Q1, Q2, Q3 etc.

Format — five comma-separated fields:
  Q{n}, {box_ref}, {kind}, {nav}, {question text}

Field 1: Q{n}
  Sequential question number starting at Q1.

Field 2: {box_ref}
  The box number or label from the form (e.g. 1, 6, H, 6B).
  Use null if the question has no explicit box number or label.

Field 3: {kind}
  Either BASIC or TABLE.
  BASIC — a standalone question answered once (not part of a repeating
          table row). Used for all questions in basic sections.
  TABLE — a column within a repeating table row. All questions in a
          table or conditional_table section must be TABLE.

Field 4: {nav}
  Either NAV or empty (leave blank, not the word "empty").
  NAV marks any question that creates a branch in the routing — i.e.
  its answer determines which question comes next, or gates a section
  or a set of conditional columns. Use NAV whether the branching is
  explicit on the form or inferred by you.

  NAV applies to:
    - Questions that gate an entire section
      (e.g. "Is the contact different from IHT400 box 17?")
    - Questions within a table row that branch to conditional columns
      (e.g. "Is this property freehold or leasehold?",
             "Were there any special factors affecting value?")
    - Questions that route differently based on a named option
      (e.g. "In which country is the property?" → England/Wales/Scotland)
    - Questions implied by form instructions that are not explicitly
      numbered but are needed to explain a conditional route

  Leave blank for all questions whose answer does not affect routing.

Field 5: {question text}
  The question text as it appears on the form, kept brief and readable.
  No prefixes (TABLE COL:, NAV:, HEADER: etc.) — the kind and nav
  fields carry that information.
  For table columns, use a short column header label
  (e.g. "Item number", "Open market value at date of death").
  For header fields at the top of the form (name, date, reference),
  use plain labels ("Name of the deceased", "Date of death").

=============================================================================
RULES FOR IDENTIFYING QUESTIONS
=============================================================================

1. One question per line. If the form has a field containing BOTH a
   person/firm name AND an address, always split into exactly two separate
   Q lines with the same box_ref:
     - First line:  the name only, question text describes the name,
                    Agent 2 will assign type personal_name
     - Second line: the address only, question text describes the address,
                    Agent 2 will assign type address
   Never combine name and address into a single question. Never use the
   phrase "name and address" in a question text — that is the signal to
   split, not to combine.
   Example — box 1 says "Name and address of the firm or person":
     Q4, 1, BASIC, , Name of the firm or person dealing with the valuation
     Q5, 1, BASIC, , Address of the firm or person dealing with the valuation
   Not:
     Q4, 1, BASIC, , Name and address of the firm or person  ← wrong
   A personal name (title, first name, last name) is always ONE question —
   do not split a name into its sub-components (title, first, last).

2. A set of address sub-fields (line 1, line 2, city, county, postcode)
   counts as ONE question — do not split address into sub-fields.

3. A personal name (title, first name, last name) counts as ONE question.

4. Table columns are individual questions. List each column of a table as
   a separate Q line (kind=TABLE), all sharing the same box_ref (e.g. 6A,
   6B, 6C etc., or just 6 if columns are not individually labelled).

5. If a table column or box presents a choice between named options AND
   indicates that one option requires follow-up detail (e.g. "freehold or
   leasehold — if leasehold, give length of lease and ground rent"), split
   into: (a) the choice question (kind=TABLE, nav=NAV), then (b) one
   question per follow-up item (kind=TABLE, nav blank), each conditional
   on the relevant choice.
   Example: "Tenure (freehold or leasehold; if leasehold, length and ground
   rent)" becomes three questions:
     Q{n},   6D, TABLE, NAV, Is this property freehold or leasehold?
     Q{n+1}, 6D, TABLE,    , How many years are left on the lease?
     Q{n+2}, 6D, TABLE,    , What is the annual ground rent?
   with routing: Q{n} "Leasehold" → Q{n+1}; Q{n} "Freehold" → Q{n+3}.

6. Gateway questions implied by the form text (e.g. "Only fill in this
   section if...") must be created as explicit questions even if not
   numbered on the form. Use null as box_ref, kind=BASIC (if gating a
   section) or TABLE (if gating conditional columns within a row), and
   nav=NAV always. Phrase as a direct citizen-facing question — never
   copy the form instruction verbatim.
   Example: "Only fill in this section if the contact differs from IHT400
   box 17" → Q{n}, null, BASIC, NAV, Is the valuation contact different
   from the person named on form IHT400, box 17?

7. Do not list form instructions, guidance text, or cross-references to
   other forms as questions.

8. SECOND PASS — implied questions: after completing your initial question
   list, re-read the form text for every box and check whether any routing
   conditions imply a question not yet in your list. Common pattern: the
   form says "if [some state] go to box N" where that state has not been
   asked explicitly. If so, insert a new NAV question, adjust Q numbering,
   and update routing accordingly. This check is mandatory.

=============================================================================
SECTION 2: Sections
=============================================================================

Group the questions into logical sections. A section is a coherent set of
questions on a single subject that a citizen would complete together.

Format:
  S{n}, {type}, [Q{n}, Q{n}, Q{n}, ...], "Section title"

{type} is one of: basic, table, conditional_table
  basic             — contains only BASIC questions (with or without NAV
                      branching within the section)
  table             — contains only TABLE questions; all routing within
                      the section is unconditional
  conditional_table — contains only TABLE questions; routing within the
                      section has one or more conditional branches (NAV
                      questions present)

"Section title" — short plain-English citizen-facing name, 4-6 words.
  Do not use form box numbers. Example: "Residential properties",
  "Details of the deceased", "Valuation contact details".

Key rules:
  1. Every Q must appear in exactly one S.
  2. All TABLE questions belonging to the same table must be in the
     same section.
  3. A section cannot mix BASIC and TABLE questions.
  4. If a section contains any NAV question among TABLE questions,
     it must be conditional_table, not table.
  5. A NAV question must never be the only question in a TABLE section.
  6. BASIC sections may contain NAV questions (branching within the
     section is fine).
  7. Header questions (name, date, reference at top of form) go in S1.

=============================================================================
SECTION 3: Routing
=============================================================================

Define how the citizen moves from one question to the next, one rule per line.

Format:
  S{n}, Q{current}, Q{condition}|null, {answer}|null, Q{next}|END

  S{n}          The section this routing rule belongs to.
  Q{current}    The question the citizen has just answered.
  Q{condition}  The question whose answer determines the route.
                Use null if the route is unconditional OR if the
                condition is on Q{current}'s own answer.
                Only set to a different Q ref when the route depends
                on the answer to an EARLIER question (e.g. a country
                selection made at the start that affects later routing).
  {answer}      The answer that triggers this route, in double quotes.
                Use null for unconditional routes.
  Q{next}|END   Next question ref, or END if the section ends.

Key rules:
  1. Every Q in every S must have at least one routing rule as Q{current}.
  2. Unconditional (always go to next):
       S1, Q2, null, null, Q3
  3. Conditional on own answer:
       S2, Q5, null, "Yes", Q6
       S2, Q5, null, "No", Q9
  4. Conditional on an earlier question's answer:
       S3, Q11, Q8, "Yes", Q12
       (Q11 is only reached because Q8 was Yes; condition is Q8 not Q11)
  5. End of section:
       S1, Q3, null, null, END
  6. For TABLE questions, routing represents the within-row column
     sequence. Use the same format.
  7. Where the form says "Go to box N" or "If Yes, go to...", translate
     that into routing rules.
  8. If routing cannot be determined with confidence, write:
       S{n}, Q{n}, UNCERTAIN, UNCERTAIN, UNCERTAIN
     Do not guess — flag for human reviewer.

=============================================================================
OUTPUT FORMAT
=============================================================================

Produce exactly this structure, with no other text:

Questions
Q1, null, BASIC, , Name of the deceased
Q2, null, BASIC, , Date of death
Q3, null, BASIC, NAV, Is the valuation contact different from IHT400 box 17?
Q4, 6A, TABLE, , Item number
Q5, 6D, TABLE, NAV, Is this property freehold or leasehold?
Q6, 6D, TABLE, , How many years are left on the lease?
...

Sections
S1, basic, [Q1, Q2], "Details of the deceased"
S2, basic, [Q3, Q4, Q5], "Valuation contact details"
S3, conditional_table, [Q6, Q7, Q8], "Residential properties"
...

Routing
S1, Q1, null, null, Q2
S1, Q2, null, null, END
S2, Q3, null, "Yes", Q4
S2, Q3, null, "No", END
S3, Q5, null, "Leasehold", Q6
S3, Q5, null, "Freehold", Q8
...

Do not add headers, explanations, comments, or any other text outside
this structure. No YAML, JSON, or markdown. Plain text only.

=============================================================================
SELF-CONSISTENCY CHECKS
=============================================================================

After completing the three sections, run ALL of the following checks.
Fix any errors found before producing your final output.

QUESTIONS CHECKS:
  QC1. Every TABLE question must be in a section containing ONLY TABLE
       questions. Flag any TABLE question in a mixed section.
  QC2. Every BASIC question must be in a section containing no TABLE
       questions. Flag any BASIC question in a mixed section.
  QC3. No section may be a mix of BASIC and TABLE questions.

SECTIONS CHECKS:
  SC1. A section whose routing contains any conditional branch (any rule
       with a non-null answer) must be conditional_table or basic —
       never table. Fix type to conditional_table if all questions are
       TABLE; fix to basic if any question is BASIC.
  SC2. A section with all unconditional TABLE routing must be table,
       not conditional_table.
  SC3. A NAV question must never be the only question in a TABLE section.

ROUTING CHECKS:
  RC1. Only NAV questions may have more than one routing entry as
       Q{current}. If a non-NAV question has multiple routing entries,
       it should be marked NAV or the routing is wrong — fix it.
  RC2. Q{condition} must be null whenever the condition is on Q{current}'s
       own answer. Only set Q{condition} to a different ref when routing
       depends on a genuinely earlier question's answer.
  RC3. No routing rule for Q{n} may reference a Q{condition} with a
       higher number than Q{n}. That question has not yet been answered.
       Fix the question order or the routing rule.
  RC4. Every Q in every S must appear at least once as Q{current} in
       routing. No orphaned questions.
  RC5. Every Q{next} (other than END) must exist in the Questions list.
       No dangling references.
  RC6. Every Q{condition} (other than null) must exist in the Questions
       list and must be marked NAV. If not, fix the routing or add the
       missing NAV question.

=============================================================================
HUMAN REVIEWER GUIDANCE
=============================================================================

If the user message contains a HUMAN REVIEWER GUIDANCE section, treat it
as authoritative. Follow it in preference to your own judgment wherever it
speaks to a structural or grouping decision. Where it is silent, use your
own judgment and flag uncertainty in the relevant routing line with UNCERTAIN.
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
        description="Agent 1 — Form Reader. Reads a PDF form and outputs a minimal "
                    "Questions / Sections / Routing text file for human review."
    )
    parser.add_argument("pdf_path", help="Path to the PDF form")
    parser.add_argument(
        "--guidance", "-g",
        help="Path to a plain-text file containing your structural guidance (optional)",
        default=None
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: <pdf_name>_read.txt)",
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
        output_path = f"{base}_read.txt"

    # Extract PDF text
    print(f"Extracting text from {args.pdf_path}...")
    try:
        pdf_text = extract_pdf_text(args.pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    if not pdf_text.strip():
        print("Warning: no text extracted from PDF. The file may be a scanned image.")
        sys.exit(1)

    print(f"Extracted {len(pdf_text)} characters of text.")

    # Load optional guidance
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

Treat the above as authoritative where it speaks to a structural decision.

"""

    user_message = f"""Please read the following UK government form and produce the
Questions, Sections, and Routing output as instructed. Remember to run
all self-consistency checks before producing your final output.
{guidance_block}
FORM TEXT:
{pdf_text}
"""

    # Call Claude
    if guidance_text:
        print(f"Calling Claude ({args.model}) with guidance...")
    else:
        print(f"Calling Claude ({args.model})...")

    try:
        output = call_claude(SYSTEM_PROMPT, user_message, model=args.model)
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        sys.exit(1)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\nDone. Output written to: {output_path}")
    print("\nNext steps:")
    print("  1. Review and correct the Questions, Sections, and Routing")
    print("  2. Pass the corrected file to agent2_question_definer.py")


if __name__ == "__main__":
    main()
