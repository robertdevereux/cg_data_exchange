"""
Session helpers for the PSS (Public Sector Services) session namespace.

All Layer 2 state lives under request.session['pss'] so it does not
collide with Django's own session keys or any future Layer 1 state.

Session dict structure:
    user_id        int    — FK to core.User (subject of the case)
    actor_id       int    — FK to core.User (currently logged-in filer;
                            equals user_id when citizen self-files)
    regime_id      str    — e.g. 'DEMO_SIMPLE'
    case_id        str    — UUID string primary key of the Case record
    schedule_id    str|None
    section_id     str    — current section being processed

    # Loaded fresh at section_start, cleared at section_confirm:
    routing_table  list[dict]   current_question_id / answer_value /
                                next_question_id (None = END)
    question_table dict         question_id -> {question_text, question_type,
                                guidance, hint, options}
    asked_ids      list[str]    question_ids on the citizen's actual path
    basic_answers  dict         question_id -> answer value (may contain
                                stale branch answers — filtered by asked_ids
                                at confirm time, never explicitly pruned)
"""


SESSION_KEY = 'pss'


def get_session(request) -> dict:
    """Return (and lazily create) the PSS session namespace."""
    return request.session.setdefault(SESSION_KEY, {})


def update_session(request, data: dict) -> None:
    """Merge data into the PSS session namespace and mark as modified."""
    session = get_session(request)
    session.update(data)
    request.session.modified = True


def get_acting_for_name(pss: dict):
    """Return full name of the subject user, or None if actor is acting for themselves."""
    user_id  = pss.get('user_id')
    actor_id = pss.get('actor_id')
    if not user_id or not actor_id or user_id == actor_id:
        return None
    from .models import User  # local import to avoid circular dependency
    try:
        return User.objects.get(pk=user_id).get_full_name()
    except User.DoesNotExist:
        return None


def clear_working_session(request) -> None:
    """Wipe all PSS working-context state (used when an agent switches client).

    Removes every key from the PSS namespace so no state from a previous
    client leaks into the next session.  The namespace itself (the 'pss' dict)
    is preserved so subsequent update_session calls still work.
    """
    session = get_session(request)
    session.clear()
    request.session.modified = True


def clear_section_session(request) -> None:
    """Remove the section-scoped keys after a section is confirmed.

    Preserves the outer context keys (user_id, actor_id, regime_id,
    case_id, schedule_id, section_id) so Layer 1 can read them on
    return from Layer 2.
    """
    session = get_session(request)
    for key in ('routing_table', 'question_table', 'asked_ids', 'basic_answers'):
        session.pop(key, None)
    request.session.modified = True
