"""
dept_hmrc/views/iht/screen.py — IHT home page renderer.

Responsibility: presentation only. Receives lean logical state from
orchestrate.py and decorates it with labels, colours, and link text
before passing to the template.

Two render functions:
  iht_screen           — verified case home page (has action list)
  iht_screen_unverified — pre-verified home page (no action list yet)

The template (dept_hmrc/iht/home.html) expects each action dict to have:
    id              str
    label           str
    hint            str | None
    status          str
    status_label    str
    status_colour   str
    url             str | None
    link_label      str | None
    flash_message   str | None
"""
from django.shortcuts import render

from core.session import get_acting_for_name, get_session


# ── Label lookup ───────────────────────────────────────────────────────────────
# Maps action row id → display label.
# Triage set rows use Section.section_name from the DB (see _decorate_actions).
ACTION_LABELS = {
    'deceased_details': "Deceased's details",
    'reckoner':         'Estate ready reckoner',
    'tailor':           'Tailor your submission',
}

# ── Status display ─────────────────────────────────────────────────────────────
STATUS_DISPLAY = {
    'complete':       ('Complete',       'green'),
    'in_progress':    ('In progress',    'blue'),
    'not_started':    ('Not started',    'grey'),
    'not_configured': ('Not configured', 'red'),
    'no_permission':  ('No permission',  'orange'),
}

# ── Conclusion messages ────────────────────────────────────────────────────────
CONCLUSION_MESSAGES = {
    'not_payable':    (
        'Based on your answers, no Inheritance Tax is payable on this estate.'
    ),
    'may_be_payable': (
        'Based on your answers, Inheritance Tax may be payable on this estate.'
    ),
    'knock_out':      (
        'Based on your answers, you will need to complete a full IHT return.'
    ),
}


def iht_screen(request, regime, verified_case, details, actions, crumbs):
    """
    Render the IHT home page for a verified case.
    Decorates the lean action list before passing to the template.
    Never reads the DB — all state is passed in.
    """
    from core.models import Section

    # Pre-fetch Section names for triage rows in one query
    triage_section_ids = [
        a['extra']['section_id']
        for a in actions
        if a.get('extra', {}).get('section_id')
    ]
    section_name_map = {}
    if triage_section_ids:
        section_name_map = {
            s.section_id: s.section_name
            for s in Section.objects.filter(section_id__in=triage_section_ids)
        }

    decorated = _decorate_actions(actions, section_name_map)

    pss = get_session(request)
    return render(request, 'dept_hmrc/iht/home.html', {
        'regime':        regime,
        'verified_case': verified_case,
        'deceased_name': details['name_display'],
        'deceased_dob':  details['dob_display'],
        'deceased_dod':  details['dod_display'],
        'deceased_nino': details['nino'],
        'reference':     verified_case.reference,
        'actions':       decorated,
        'acting_for':    get_acting_for_name(pss),
        'breadcrumbs':   crumbs,
    })


def iht_screen_unverified(request, regime, statuses, entry_url, pss, crumbs):
    """
    Render the IHT home page before a verified case exists.
    No action list — just the entry point to start S1.
    """
    total        = statuses.count()
    complete     = statuses.filter(status='complete').count()

    return render(request, 'dept_hmrc/iht/home.html', {
        'regime':        regime,
        'verified_case': None,
        'total':         total,
        'complete':      complete,
        'all_complete':  total > 0 and complete == total,
        'entry_url':     entry_url,
        'acting_for':    get_acting_for_name(pss),
        'breadcrumbs':   crumbs,
    })


def _decorate_actions(actions, section_name_map):
    """
    Add presentation fields to each lean action dict.
    Returns a new list — does not mutate the input.
    """
    decorated = []
    for action in actions:
        status = action['status']
        status_label, status_colour = STATUS_DISPLAY.get(
            status, ('Not started', 'grey')
        )

        # Label — from ACTION_LABELS, or Section name for triage rows
        section_id = action.get('extra', {}).get('section_id')
        if section_id:
            label = section_name_map.get(section_id, section_id)
        else:
            label = ACTION_LABELS.get(action['id'], action['id'])

        # Link label
        link_label = _link_label(action['id'], status, action['url'])

        # Flash — reckoner row gets persistent conclusion message as fallback
        flash = action.get('flash_message')
        if action['id'] == 'reckoner' and not flash:
            conclusion = action.get('extra', {}).get('conclusion')
            flash = CONCLUSION_MESSAGES.get(conclusion)

        decorated.append({
            'id':            action['id'],
            'label':         label,
            'hint':          action.get('hint'),
            'status':        status,
            'status_label':  status_label,
            'status_colour': status_colour,
            'url':           action['url'],
            'link_label':    link_label,
            'flash_message': flash,
        })

    return decorated


def _link_label(action_id, status, url):
    """
    Return the appropriate link label for an action row.
    Returns None if there is no URL or status prevents linking.
    """
    if not url or url == '#':
        return None
    if status in ('not_configured', 'no_permission'):
        return None
    if status == 'not_started':
        return 'Start'
    return 'View / amend'
