"""
agent1b_set_builder.py
======================
Agent 1B of the form-ingestion pipeline.

A pure Python script (no Claude call needed) that inserts user-defined
Sets into the Agent 1 output, updating Sections and Routing consistently.

INPUT:
  read_txt     The reviewed Agent 1 output (_read.txt)
  sets_txt     A plain-text file defining the Sets, one per line:
               SET1, [Q13, Q14, Q15, Q16, Q17], "Letting details"
               SET2, [Q20, Q21, Q22, Q23], "Other land letting details"

OUTPUT:
  An updated _read.txt with:
    - A new Sets block inserted after Questions
    - Sections updated: Q refs that form a complete Set replaced by SET ref
    - Routing updated:
        * Any next_q pointing to the FIRST Q of a Set → replaced by SET ref
        * Any current_q that is the LAST Q of a Set → replaced by SET ref
          (so the SET itself becomes the routing node, not its last question)
        * Routing rules for Qs internal to a Set are removed (they are
          implicit — all Qs in a Set are shown together on one page)

Usage:
    python agent1b_set_builder.py <read_txt> <sets_txt> [--output <output.txt>]

Example:
    python agent1b_set_builder.py IHT405_read.txt IHT405_sets.txt
    python agent1b_set_builder.py IHT405_read.txt IHT405_sets.txt --output IHT405_read_v2.txt

Sets file format — one line per Set:
    SET{n}, [Q{n}, Q{n}, ...], "Set title"

Example sets file:
    SET1, [Q13, Q14, Q15, Q16, Q17], "Letting details"
    SET2, [Q22, Q23, Q24, Q25], "Other land letting details"
"""

import argparse
import re
import sys


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_sets_file(sets_path: str) -> list:
    """
    Parse the user-defined sets file.
    Returns a list of dicts:
      { 'ref': 'SET1', 'questions': ['Q13','Q14',...], 'title': '...' }
    """
    sets = []
    with open(sets_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Parse: SET1, [Q13, Q14, Q15], "Title"
            m = re.match(
                r'^(SET\d+)\s*,\s*\[([^\]]+)\]\s*,\s*"([^"]*)"',
                line
            )
            if not m:
                print(f"Warning: could not parse sets file line {line_num}: {line!r}")
                continue
            ref = m.group(1).strip()
            qs = [q.strip() for q in m.group(2).split(',')]
            title = m.group(3).strip()
            sets.append({'ref': ref, 'questions': qs, 'title': title})
    return sets


def parse_read_file(read_path: str) -> dict:
    """
    Parse the Agent 1 _read.txt into its three blocks.
    Returns:
      {
        'questions_lines': [...],   # raw lines from Questions block
        'sections_lines':  [...],   # raw lines from Sections block
        'routing_lines':   [...],   # raw lines from Routing block
      }
    """
    questions_lines = []
    sections_lines  = []
    routing_lines   = []

    current_block = None
    with open(read_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            if line.strip() == 'Questions':
                current_block = 'questions'
                continue
            elif line.strip() == 'Sections':
                current_block = 'sections'
                continue
            elif line.strip() == 'Routing':
                current_block = 'routing'
                continue

            if not line.strip():
                continue

            if current_block == 'questions':
                questions_lines.append(line.strip())
            elif current_block == 'sections':
                sections_lines.append(line.strip())
            elif current_block == 'routing':
                routing_lines.append(line.strip())

    return {
        'questions_lines': questions_lines,
        'sections_lines':  sections_lines,
        'routing_lines':   routing_lines,
    }


def parse_section_line(line: str) -> dict:
    """
    Parse a Sections line:
      S1, basic, [Q1, Q2, Q3], "Title"
    Returns dict with ref, type, questions, title.
    """
    m = re.match(
        r'^(S\d+)\s*,\s*(\w+)\s*,\s*\[([^\]]*)\]\s*,\s*"([^"]*)"',
        line
    )
    if not m:
        return None
    qs = [q.strip() for q in m.group(3).split(',') if q.strip()]
    return {
        'ref':       m.group(1).strip(),
        'type':      m.group(2).strip(),
        'questions': qs,
        'title':     m.group(4).strip(),
        'raw':       line,
    }


def parse_routing_line(line: str) -> dict:
    """
    Parse a Routing line:
      S1, Q1, null, null, Q2
    Returns dict with section, current_q, condition_q, condition_answer, next_q.
    """
    parts = [p.strip() for p in line.split(',', 4)]
    if len(parts) != 5:
        return None
    return {
        'section':          parts[0],
        'current_q':        parts[1],
        'condition_q':      parts[2],
        'condition_answer': parts[3],
        'next_q':           parts[4],
        'raw':              line,
    }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def build_set_lookup(sets: list) -> dict:
    """
    Build lookup structures for efficient processing.
    Returns:
      {
        'by_first_q':  { 'Q13': set_dict, ... }  # first Q of each set
        'by_last_q':   { 'Q17': set_dict, ... }  # last Q of each set
        'internal_qs': { 'Q14', 'Q15', 'Q16' }  # Qs internal to any set
        'all_qs':      { 'Q13', ..., 'Q17' }     # all Qs in any set
        'by_ref':      { 'SET1': set_dict, ... }
      }
    """
    by_first  = {}
    by_last   = {}
    internal  = set()
    all_qs    = set()
    by_ref    = {}

    for s in sets:
        qs = s['questions']
        if not qs:
            continue
        by_first[qs[0]]  = s
        by_last[qs[-1]]  = s
        for q in qs[1:-1]:   # internal = everything except first and last
            internal.add(q)
        # If only one Q, it's both first and last — not really a Set
        # but we handle it gracefully
        all_qs.update(qs)
        by_ref[s['ref']] = s

    return {
        'by_first_q':  by_first,
        'by_last_q':   by_last,
        'internal_qs': internal,
        'all_qs':      all_qs,
        'by_ref':      by_ref,
    }


def update_sections(sections_lines: list, sets: list, lookup: dict) -> list:
    """
    Update section question_refs: replace contiguous runs of Set Qs
    with the SET ref.
    """
    updated = []
    for line in sections_lines:
        parsed = parse_section_line(line)
        if not parsed:
            updated.append(line)
            continue

        # Walk through the question list, replacing Set Q runs with SET ref
        qs = parsed['questions']
        new_qs = []
        i = 0
        while i < len(qs):
            q = qs[i]
            # Is this Q the first in a Set?
            if q in lookup['by_first_q']:
                s = lookup['by_first_q'][q]
                set_qs = s['questions']
                # Check all Set Qs appear consecutively here
                if qs[i:i+len(set_qs)] == set_qs:
                    new_qs.append(s['ref'])
                    i += len(set_qs)
                    continue
            new_qs.append(q)
            i += 1

        q_str = ', '.join(new_qs)
        updated.append(
            f'{parsed["ref"]}, {parsed["type"]}, [{q_str}], "{parsed["title"]}"'
        )

    return updated


def update_routing(routing_lines: list, lookup: dict) -> list:
    """
    Update routing rules:
    1. Remove rules where current_q is internal to a Set
       (internal Qs are shown together — no routing between them)
    2. Replace next_q pointing to first-Q-of-Set with SET ref
    3. Replace current_q that is last-Q-of-Set with SET ref
       (the SET becomes the routing node after all its Qs are answered)
    """
    updated = []
    for line in routing_lines:
        parsed = parse_routing_line(line)
        if not parsed:
            updated.append(line)
            continue

        current_q = parsed['current_q']
        next_q    = parsed['next_q']

        # Drop rules where current_q is internal to a Set
        if current_q in lookup['internal_qs']:
            continue

        # Replace current_q if it's the last Q of a Set
        if current_q in lookup['by_last_q']:
            current_q = lookup['by_last_q'][current_q]['ref']

        # Replace next_q if it's the first Q of a Set
        if next_q in lookup['by_first_q']:
            next_q = lookup['by_first_q'][next_q]['ref']

        updated.append(
            f'{parsed["section"]}, {current_q}, '
            f'{parsed["condition_q"]}, {parsed["condition_answer"]}, {next_q}'
        )

    return updated


def format_sets_block(sets: list) -> list:
    """Format the Sets block lines."""
    lines = []
    for s in sets:
        q_str = ', '.join(s['questions'])
        lines.append(f'{s["ref"]}, [{q_str}], "{s["title"]}"')
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent 1B — Set Builder. Inserts user-defined Sets into "
                    "the Agent 1 output and updates Sections and Routing."
    )
    parser.add_argument("read_txt",
                        help="Path to the reviewed Agent 1 output (_read.txt)")
    parser.add_argument("sets_txt",
                        help="Path to the plain-text Sets definition file")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path (default: <read_txt_base>_sets.txt)"
    )
    args = parser.parse_args()

    # Resolve output path
    if args.output:
        output_path = args.output
    else:
        base = args.read_txt.rsplit('.', 1)[0]
        output_path = f"{base}_sets.txt"

    # Parse inputs
    print(f"Loading Agent 1 output from {args.read_txt}...")
    blocks = parse_read_file(args.read_txt)

    print(f"Loading Sets definitions from {args.sets_txt}...")
    sets = parse_sets_file(args.sets_txt)

    if not sets:
        print("No valid Set definitions found. Exiting.")
        sys.exit(1)

    print(f"  {len(sets)} Set(s) defined:")
    for s in sets:
        print(f"    {s['ref']}: {s['questions']} — \"{s['title']}\"")

    # Build lookup structures
    lookup = build_set_lookup(sets)

    # Validate: check all referenced Qs exist in the questions block
    known_qs = set()
    for line in blocks['questions_lines']:
        m = re.match(r'^(Q\d+)', line)
        if m:
            known_qs.add(m.group(1))

    errors = []
    for s in sets:
        for q in s['questions']:
            if q not in known_qs:
                errors.append(f"  {s['ref']}: Q ref '{q}' not found in Questions block")

    if errors:
        print("\nErrors in Sets definitions:")
        for e in errors:
            print(e)
        print("\nPlease fix the Sets file and re-run.")
        sys.exit(1)

    # Warn if any Set has only one question
    for s in sets:
        if len(s['questions']) == 1:
            print(f"Warning: {s['ref']} has only one question — "
                  f"a Set with one question is equivalent to that question alone.")

    # Update blocks
    print("\nUpdating Sections...")
    updated_sections = update_sections(blocks['sections_lines'], sets, lookup)

    print("Updating Routing...")
    original_routing_count = len(blocks['routing_lines'])
    updated_routing = update_routing(blocks['routing_lines'], lookup)
    removed = original_routing_count - len(updated_routing)
    print(f"  {removed} internal-Set routing rule(s) removed.")

    sets_block = format_sets_block(sets)

    # Assemble output
    output_lines = (
        ['Questions']
        + blocks['questions_lines']
        + ['']
        + ['Sets']
        + sets_block
        + ['']
        + ['Sections']
        + updated_sections
        + ['']
        + ['Routing']
        + updated_routing
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines) + '\n')

    print(f"\nDone. Updated output written to: {output_path}")
    print("\nNext step: review the updated file, then pass to agent2_question_definer.py")


if __name__ == "__main__":
    main()
