# Project instructions for Claude Code

This file is read automatically at the start of every session. Keep it short —
link to the fuller documents rather than duplicating their content here.

## Document map

- **Design papers** (`260729_Paper_1/2/3*.md` + annexes) — the source of
  *intent*. What the system is meant to do and why.
- **Build docs** (`260729_Build_*.md`) — the source of *current mechanism*.
  How the live code actually works right now.
- **Backlog** (`260730_Backlog.md`) — the source of *the gap*: what's done,
  what's next, and what's known to be broken or deferred.
- **`file_dump.txt`** — a point-in-time export of the live codebase. Treat it
  as a snapshot, not ground truth — it goes stale the moment a commit lands
  after it was generated. Regenerate it at the start of any session doing
  substantive investigation or design-vs-build reconciliation work.

If any of these disagree with what the live code actually does, the live
code wins. Flag the disagreement rather than silently trusting the document.

## Running tests

Always use the full conda path:

```
/Users/robert/anaconda3/envs/env_python_django_psql/bin/python manage.py test --keepdb
```

Never use `python manage.py test`, `source activate`, or `conda run`. The
correct environment is `env_python_django_psql` (note the `_psql` suffix).

**Never run two `manage.py test` invocations concurrently** against the Neon
test DB. Sequential only. Several test classes (`TestRoutingAdminTools`,
`TestConditionalTableSection`, likely others) use fixed-ID fixtures in
`setUpTestData` and will fail with spurious unique-constraint errors under
concurrent execution — this is a known test-infrastructure limitation, not a
code bug worth chasing.

## After every commit

Append **one line** to `260730_Backlog.md`'s dated "Completed" log — commit
hash, a one-line description, and which document(s) the change makes stale
(a build-doc section, a design-paper section, or "none"). Do this
immediately, even if the actual document edit happens later as a batched
pass. Example:

```
- `90f3f45` — address rendering fix, table_routed_set.html. Doc impact:
  build doc §4d (address type coverage).
```

This log is what gets read back at session end (or at the start of the next
session) to catch up the fuller documents — it should be possible to
reconstruct "what changed and what needs updating" from this log alone,
without reconstructing it from the conversation transcript.

## If a design paper turns out to be wrong

Not just incomplete — actually incorrect, in a way discovered through
building or live-testing it. Flag this **immediately**, not at session end.
Subsequent work in the same session may depend on the corrected
understanding, and building further on a known-wrong design compounds the
problem in a way a stale build doc or backlog entry does not.

Record the correction as a dated, labelled addendum to the design paper
(what was wrong, what it's corrected to, why) — don't silently edit the
original text. A reader should be able to see that the design changed and
why, not just see the current state as if it were always so.

## Verify before assuming

- Before diagnosing a routing/data problem as a code bug, check the
  simpler explanation first: does the exact wording of a `Question.options`
  entry match the exact wording of the corresponding `Routing.answer_value`
  rows? Small drift here has caused real incidents (silent row-abandonment)
  and is easy to introduce when a question and its routing are configured
  as separate manual steps.
- Before assuming a section is correctly wired for a user journey, check
  both `regime_id`/`schedule_id` on the `Section` record directly — don't
  assume one implies the other, or that a fix to one resolves the other.
- A stale reference to file/document content (e.g. `file_dump.txt`) is
  always possible mid-session if commits have landed since it was
  generated. If line numbers or template content don't match what's
  expected, re-check live rather than assume the reference is current.
