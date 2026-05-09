"""
core/views_layer1.py — DEPRECATED (Part 3 refactoring)

Layer 1 navigation now lives entirely in department apps (e.g. dept_demo/).
The platform provides:
  - core/interfaces.py     — get_or_create_case, bootstrap_section_statuses
  - core/nav_reference.py  — resolve_layer1_entry_url, reference pattern views
  - core/permissions.py    — get_permitted_sections, get_permitted_regimes
  - core/session.py        — get_session, update_session

This file is retained as an empty stub to avoid import errors during the
transition period.  It will be deleted in a future cleanup.
"""
