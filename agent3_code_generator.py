"""
agent3_code_generator.py
========================
Agent 3 of the form-ingestion pipeline.

Takes the reviewed combined YAML output of Agent 2 (which contains sections,
routing, and questions) and generates a Django management command that
populates the platform database using update_or_create.

INPUT:
  combined_yaml    The reviewed Agent 2 output YAML (sections + routing +
                   questions in one file)
  --regime         Existing regime_id to attach sections to (e.g. HMRC_IHT)
  --Q              Highest existing department question ID (e.g. HMRC_96)
  --S              Highest existing section ID (e.g. HMRC_S4)
  --SCH            Highest existing schedule ID (e.g. HMRC_SCH5) — only
                   needed if creating a new schedule
  --schedule       Optional existing schedule_id to attach sections to
                   instead of directly to the regime
  --dept           Department prefix (default: HMRC)
  --command-name   Name for the generated management command

OUTPUT:
  A Django management command Python file, ready to place in
  {app}/management/commands/ and run with manage.py {command-name}

Usage:
    python agent3_code_generator.py IHT405_combined.yaml
        --regime HMRC_IHT --Q HMRC_96 --S HMRC_S4 --SCH HMRC_SCH5
        --command-name load_iht405_data

Dependencies:
    pip install anthropic pyyaml
    ANTHROPIC_API_KEY must be set in environment (e.g. in .env)
"""

import argparse
import json
import os
import re
import sys

import anthropic
import yaml


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a code generator for a UK government digital services platform built
on Django 5.1. You will be given pre-computed lookup tables and structured
JSON data describing questions, sections, and routing for a government form.

Your job is to generate a complete Django management command Python file that
populates the database using update_or_create. The command must be idempotent.

=============================================================================
PLATFORM MODELS
=============================================================================

Question:
  question_id     CharField primary key (e.g. HMRC_97)
  question_text   TextField
  question_type   CharField: text, textarea, number, radio, radio_inline,
                  checkbox, address, date, personal_name, compound
  guidance        TextField nullable
  hint            CharField(255) nullable
  options         TextField nullable — SEMICOLON-DELIMITED string
                  e.g. "Yes;No" or "Freehold;Leasehold"
  answer_type     CharField nullable: text, number, date
  is_platform     BooleanField default False

  answer_type rules:
    number type   -> answer_type = 'number'
    date type     -> answer_type = 'date'
    all others    -> answer_type = 'text'

Section:
  section_id           CharField primary key (e.g. HMRC_S5)
  section_name         CharField
  section_type         IntegerField: 0=basic, 1=table, 2=conditional_table
  display_order        PositiveIntegerField
  schedule             ForeignKey nullable — set if --schedule provided
  regime               ForeignKey nullable — set if no --schedule
  section_guidance     TextField nullable
  display_question_ids TextField nullable — SEMICOLON-DELIMITED question_ids
                       For type 1: all question_ids in order
                       For type 2: NAV/summary column question_ids only
                       For type 0: None
  totals_question_ids  TextField nullable — question_ids for numeric totals
  show_confirmation    BooleanField default True

Routing:
  section              ForeignKey to Section
  current_node         CharField — real question_id (e.g. HMRC_97)
  condition_question_id CharField nullable — ONLY set when routing depends
                       on a DIFFERENT earlier question's answer. Leave None
                       when condition is on the current question's own answer
                       or when routing is unconditional.
  answer_value         TextField nullable — None for unconditional
  next_node            CharField nullable — None means END. Never use the
                       string "END" — use None.
  comparator           CharField nullable — leave None
  order_in_section     PositiveIntegerField — sequential from 1

=============================================================================
LOOKUP TABLES
=============================================================================

You will be given:
  Q-REF TO QUESTION_ID: maps Q1, Q2... to real IDs (HMRC_97, P_1 etc.)
  SECTION REF TO SECTION_ID: maps S1, S2... to real IDs (HMRC_S5 etc.)

Use these consistently for:
  - current_node and next_node in Routing (look up Q-ref)
  - condition_question_id (look up condition_q Q-ref, only when it differs
    from current_q — otherwise leave None)
  - display_question_ids on Section (semicolon-join the looked-up IDs)

Platform questions (P_1 to P_6) appear in the Q-ref lookup but must NOT
get their own Question update_or_create block — they already exist.

=============================================================================
ROUTING RULES
=============================================================================

condition_q in the input is null when:
  (a) routing is unconditional, OR
  (b) the condition is on the current question's own answer
In both cases set condition_question_id = None in the generated code.

condition_q is a Q-ref only when routing depends on a genuinely earlier
question's answer. In that case look up the Q-ref and set
condition_question_id to the real question_id.

next_q = END means next_node = None (null) in the database.

order_in_section is sequential across ALL routing rules in a section,
starting from 1.

=============================================================================
GENERATED COMMAND STRUCTURE
=============================================================================

from django.core.management.base import BaseCommand
from core.models import Question, Section, Routing, Regime, Schedule


class Command(BaseCommand):
    help = "Load {form} questions, sections and routing"

    def handle(self, *args, **options):
        regime = Regime.objects.get(regime_id="{regime_id}")

        # Optionally get schedule:
        # schedule = Schedule.objects.get(schedule_id="{schedule_id}")

        # ── Questions ──────────────────────────────────────────────────────
        # One update_or_create per question.
        # Skip platform questions (P_1 to P_6) — they already exist.
        # options field: semicolon-delimited string, e.g. "Yes;No"

        q_HMRC_97, _ = Question.objects.update_or_create(
            question_id='HMRC_97',
            defaults=dict(
                question_text='...',
                question_type='radio',
                guidance='...',
                hint='...',
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )
        # ... repeat for each question

        # ── Sections ───────────────────────────────────────────────────────
        # One update_or_create per section.

        section_s1, _ = Section.objects.update_or_create(
            section_id='HMRC_S5',
            defaults=dict(
                section_name='Details of the deceased',
                section_type=0,
                display_order=1,
                regime=regime,
                schedule=None,
                section_guidance=None,
                display_question_ids=None,
                totals_question_ids=None,
                show_confirmation=True,
            )
        )

        # ── Routing ────────────────────────────────────────────────────────
        # Delete existing routing for each section, then recreate in order.

        Routing.objects.filter(section=section_s1).delete()
        Routing.objects.create(
            section=section_s1,
            current_node='HMRC_97',
            condition_question_id=None,
            answer_value=None,
            next_node='HMRC_98',
            order_in_section=1,
        )
        # ... repeat for each routing rule

        self.stdout.write(self.style.SUCCESS('Done.'))

Use descriptive variable names for Question objects (q_{question_id} with
underscores replacing hyphens) and Section objects (section_{s_ref}).
Add a comment header above each logical block.
Produce only valid, runnable Python. No markdown fences. No commentary
outside the Python file.

CRITICAL: The output MUST contain all three blocks — Questions, Sections,
and Routing — in that order. Do not stop after Questions. The Sections and
Routing blocks are essential and must be complete before the
self.stdout.write(self.style.SUCCESS('Done.')) line.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_highest_id(id_str: str, dept: str, suffix: str = '') -> int:
    """Extract numeric suffix from e.g. HMRC_96, HMRC_S4, HMRC_SCH5."""
    pattern = f"{dept}_{suffix}"
    tail = id_str.replace(pattern, '')
    try:
        return int(tail)
    except ValueError:
        print(f"Error: could not parse number from '{id_str}'")
        sys.exit(1)


def call_claude(system: str, user_message: str,
                model: str = "claude-sonnet-4-6") -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent 3 — Code Generator. Takes the Agent 2 combined YAML "
                    "and generates a Django management command."
    )
    parser.add_argument(
        "combined_yaml",
        help="Path to the reviewed Agent 2 combined YAML file "
             "(sections + routing + questions)"
    )
    parser.add_argument("--regime", required=True,
                        help="Existing regime_id (e.g. HMRC_IHT)")
    parser.add_argument("--Q", required=True,
                        help="Highest existing question ID (e.g. HMRC_96)")
    parser.add_argument("--S", required=True,
                        help="Highest existing section ID (e.g. HMRC_S4)")
    parser.add_argument("--SCH", default=None,
                        help="Highest existing schedule ID (e.g. HMRC_SCH5)")
    parser.add_argument("--schedule", default=None,
                        help="Existing schedule_id to attach sections to")
    parser.add_argument("--dept", default="HMRC",
                        help="Department prefix (default: HMRC)")
    parser.add_argument("--command-name", default=None,
                        help="Management command name")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path")
    parser.add_argument("--model", "-m", default="claude-sonnet-4-6")
    args = parser.parse_args()

    dept = args.dept
    command_name = args.command_name or \
        f"load_{args.regime.lower().replace('-', '_')}_data"
    output_path = args.output or f"{command_name}.py"

    # Parse highest IDs
    next_q_num   = parse_highest_id(args.Q,   dept, '')   + 1
    next_s_num   = parse_highest_id(args.S,   dept, 'S')  + 1
    next_sch_num = (parse_highest_id(args.SCH, dept, 'SCH') + 1
                    if args.SCH else None)

    print(f"Next question number: {dept}_{next_q_num}")
    print(f"Next section number:  {dept}_S{next_s_num}")
    if next_sch_num:
        print(f"Next schedule number: {dept}_SCH{next_sch_num}")

    # Load combined YAML
    print(f"\nLoading combined YAML from {args.combined_yaml}...")
    try:
        with open(args.combined_yaml, "r", encoding="utf-8") as f:
            raw = f.read()
        clean = re.sub(r'^```ya?ml\s*', '', raw, flags=re.MULTILINE)
        clean = re.sub(r'^```\s*$',     '', clean, flags=re.MULTILINE)
        combined_data = yaml.safe_load(clean)
    except Exception as e:
        print(f"Error reading combined YAML: {e}")
        sys.exit(1)

    questions_list = combined_data.get('questions', [])
    sections_list  = combined_data.get('sections',  [])
    routing_list   = combined_data.get('routing',   [])
    print(f"  {len(questions_list)} questions, {len(sections_list)} sections, "
          f"{len(routing_list)} routing rules.")

    # Build Q-ref lookup from questions block.
    # All department questions are assigned sequentially as HMRC_N
    # regardless of their role (nav, header, or ordinary question).
    # Platform questions (P_1 to P_6) keep their existing ID.
    # Any legacy HMRC_N* or HMRC_H* ids from Agent 2 are ignored
    # and replaced with the next sequential number.
    print("Building lookups...")
    q_lookup = {}
    dept_counter = next_q_num - 1
    for q in questions_list:
        ref = q['ref']
        if q.get('platform_question'):
            q_lookup[ref] = q['platform_question']
            continue
        q_id = q.get('question_id', '')
        # Accept the id from Agent 2 only if it's a plain sequential
        # dept id (e.g. HMRC_97). Reject N/H-prefixed ids and reassign.
        import re as _re
        if q_id and _re.match(rf'^{dept}_\d+$', q_id):
            q_lookup[ref] = q_id
        else:
            dept_counter += 1
            q_lookup[ref] = f'{dept}_{dept_counter}'

    # Build section ID lookup
    s_lookup = {}
    for i, s in enumerate(sections_list):
        s_lookup[s['ref']] = f"{dept}_S{next_s_num + i}"

    print(f"  {len(q_lookup)} Q-refs, {len(s_lookup)} S-refs mapped.")

    # Format lookups for prompt
    q_lookup_lines = "\n".join(
        f"  {ref} -> {qid}"
        for ref, qid in sorted(q_lookup.items(),
                                key=lambda x: (int(re.sub(r'\D.*$', '', x[0][1:])), x[0]))
    )
    s_lookup_lines = "\n".join(
        f"  {ref} -> {sid}" for ref, sid in s_lookup.items()
    )
    sch_line = (f"  next schedule #:  {dept}_SCH{next_sch_num}\n"
                if next_sch_num else "")

    # Build compact JSON representations for the prompt
    # (JSON is more token-efficient than re-serialised YAML)
    compact = {
        "sections":  sections_list,
        "routing":   routing_list,
        "questions": questions_list,
    }
    compact_json = json.dumps(compact, indent=2)

    user_message = (
        "Please generate a Django management command that loads the "
        "questions, sections, and routing defined below.\n\n"
        "PARAMETERS:\n"
        f"  regime_id:        {args.regime}\n"
        f"  schedule_id:      {args.schedule or 'None — attach directly to regime'}\n"
        f"  department:       {dept}\n"
        f"  command name:     {command_name}\n"
        f"  next question #:  {dept}_{next_q_num}\n"
        f"  next section #:   {dept}_S{next_s_num}\n"
        f"{sch_line}\n"
        "Q-REF TO QUESTION_ID LOOKUP:\n"
        f"{q_lookup_lines}\n\n"
        "SECTION REF TO SECTION_ID LOOKUP:\n"
        f"{s_lookup_lines}\n\n"
        "FORM DATA (sections, routing, questions):\n"
        f"{compact_json}\n"
    )

    # Call Claude
    print(f"\nCalling Claude ({args.model})...")
    try:
        code_output = call_claude(SYSTEM_PROMPT, user_message, model=args.model)
    except Exception as e:
        print(f"Error calling Claude API: {e}")
        sys.exit(1)

    # Strip any accidental markdown fences
    code_output = re.sub(r'^```python\s*', '', code_output, flags=re.MULTILINE)
    code_output = re.sub(r'^```\s*$',      '', code_output, flags=re.MULTILINE)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(code_output)

    print(f"\nDone. Management command written to: {output_path}")
    print(f"\nTo use:")
    print(f"  cp {output_path} <app>/management/commands/")
    print(f"  python manage.py {command_name}")


if __name__ == "__main__":
    main()
