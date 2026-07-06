"""
dept_hmrc/views/iht/orchestrate.py — IHT regime orchestrator.

Responsibility: read state, make decisions, dispatch. Never render.
Rendering is screen.py's job. Presentation (labels, colours) is screen.py's job.

Two-phase action button pattern
────────────────────────────────
Every action button has an ENTRY and an EXIT in iht_orchestrate.

ENTRY — iht_orchestrate sends the user into core:
  start            → S1 (create deceased details, new draft case)
  deceased_details → S1 (amend deceased details)
  reckoner         → S2 then S3 (ready reckoner flow)
  tailor           → S4/S5/S6 (tailor your submission)

EXIT — iht_orchestrate receives the user back from core:
  start            → run matching, create IHT ref or dead end
  deceased_details → run matching, conflict dead end or home
  reckoner         → run reckoner logic, may re-enter S3 or go home
  tailor           → nothing to do, render home

Session flags:
  iht_current_action  — which action button is active
  iht_in_core         — True while user is inside core sections;
                        set on ENTRY, popped on every visit to iht_orchestrate
                        so EXIT code knows it is returning from core

call_sections always sets return_url = regime_home_url so core always
returns here. No post_confirm_redirect used in HMRC IHT.
"""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.interfaces import (
    call_core, create_case, format_answer_for_display,
    get_answers, get_asked_answers_for_section, get_cases,
    reset_section_progress,
)
from core.models import Case, Permission, Regime, Routing, Section, SectionStatus
from core.models import QuestionSetMember
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session
from core.views_gate import choose_user_for_regime
from dept_hmrc.models import IHTReckoner

from .matching import run_iht_matching
from .reckoner import handle_reckoner
from .screen import iht_screen, iht_screen_unverified


IHT_REGIME_ID = 'HMRC_IHT'


def _get_triage_sets():
    """
    Returns the ordered list of triage sections (HMRC_S4/S5/S6) belonging
    to HMRC_SCH1. Section has a direct FK to Schedule (with display_order
    on Section itself) — there is no separate ScheduleSection join model.
    """
    from django.db.models import F
    return list(
        Section.objects
        .filter(schedule_id='HMRC_SCH1')
        .order_by('display_order')
        .values('section_id', name=F('section_name'))
    )

TRIAGE_SETS = _get_triage_sets()
TRIAGE_SECTION_IDS = [t['section_id'] for t in TRIAGE_SETS]

QUESTION_SCHEDULE_MAP = {
    'HMRC_16': 'HMRC_SCH2',
    'HMRC_31': 'HMRC_SCH3',
    'HMRC_17': 'HMRC_SCH4',
    'HMRC_18': 'HMRC_SCH5',
    'HMRC_19': 'HMRC_SCH6',
    'HMRC_21': 'HMRC_SCH7',
    'HMRC_22': 'HMRC_SCH8',
    'HMRC_23': 'HMRC_SCH9',
}


# ══════════════════════════════════════════════════════════════════════════════
# SESSION GATE
# ══════════════════════════════════════════════════════════════════════════════

def _iht_gate(request, regime):
    """
    Inline identity/estate picker for IHT.  Always returns a response.

    Leading option is "Begin a new estate" → select_self → iht_start_new_estate
    (select_self writes user_id/actor_id to the PSS session before continuing).
    Existing verified estates appear as additional candidates, each setting
    case_id from perm.case_id via select_identity.
    """
    new_url  = reverse('dept_hmrc:iht_start_new_estate')
    self_url = f"{reverse('core:select_self')}?{urlencode({'next': new_url})}"
    return choose_user_for_regime(
        request,
        regime=regime,
        leading_option={
            'label':      'Begin a new estate',
            'action_url': self_url,
        },
        next_url=reverse('dept_hmrc:regime_home',
                         kwargs={'regime_id': regime.regime_id}),
    )


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def iht_orchestrate(request):
    """
    IHT regime controller. Reads state, dispatches — never renders directly.
    Called on every visit to /hmrc/regime/HMRC_IHT/.
    """
    regime, actor, _actor_default_user, pss, crumbs = _setup(request)
    if not pss.get('user_id'):
        return _iht_gate(request, regime)

    current_action      = _get_current_action(request)
    returning_from_core = request.session.pop('iht_in_core', False)
    request.session.modified = True

    # Resolve the active case (if any) and derive `user` directly from it —
    # case.user is the single source of truth for who owns this case's data,
    # correct for both draft (user=actor) and verified (user=deceased) states.
    # We deliberately do not cache this in session: promotion updates case.user
    # in the DB, and the next request picks it up automatically.
    case_id = request.session.get('case_id')
    case = Case.objects.filter(case_id=case_id, regime=regime).first() if case_id else None

    if case:
        user = case.user
        verified_case = case if case.reference else None
    else:
        verified_cases = list(_get_verified_cases(actor, regime))
        if verified_cases:
            return _iht_gate(request, regime)
        user = _actor_default_user
        verified_case = None

    # ── Bootstrap: very first visit, no case, no action set ───────────────────
    if not verified_case and not current_action:
        _set_current_action(request, 'start')
        current_action = 'start'

    active_items = _get_active_triage_items(verified_case)

    # ── ENTRY — send user into core ────────────────────────────────────────────
    if not returning_from_core:
        if current_action == 'start':
            return _entry_start(request, regime, actor, user, pss, crumbs)
        if current_action == 'deceased_details':
            return _entry_deceased_details(request, regime, actor, user)
        if current_action == 'reckoner':
            return _entry_reckoner(request, regime, actor, user)
        if current_action == 'tailor':
            return _entry_tailor(request, regime, actor, user)
        if current_action in {t['section_id'].lower() for t in TRIAGE_SETS}:
            return _entry_triage_assets(request, regime, actor, user,
                                        verified_case, active_items,
                                        current_action.upper())
        # No current_action — fresh home page visit
        return _render_home(request, regime, actor, user, verified_case, crumbs)

    # ── EXIT — returned from core, do post-processing ─────────────────────────
    if current_action == 'start':
        return _exit_start(request, regime, actor, user, pss, crumbs)
    if current_action == 'deceased_details':
        return _exit_deceased_details(request, verified_case, regime, actor,
                                      user, crumbs)
    if current_action == 'reckoner':
        result = _exit_reckoner(request, regime, actor, user, verified_case)
        if result is not None:
            return result
    if current_action == 'tailor':
        pass  # nothing to do on exit
    if current_action in {t['section_id'].lower() for t in TRIAGE_SETS}:
        pass  # no post-processing needed

    # ── HOME ───────────────────────────────────────────────────────────────────
    _clear_current_action(request)
    return _render_home(request, regime, actor, user, verified_case, crumbs)


# ══════════════════════════════════════════════════════════════════════════════
# ACTION BUTTON VIEWS — thin wrappers that set current_action and redirect home
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def iht_action_deceased(request):
    """Deceased's details — View/amend."""
    _set_current_action(request, 'deceased_details')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_action_reckoner(request):
    """Estate ready reckoner."""
    _set_current_action(request, 'reckoner')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_action_tailor(request):
    """Tailor your submission."""
    _set_current_action(request, 'tailor')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_action_hmrc_s4(request):
    """Triage set S4 — enter built schedules for Yes-answered S4 items."""
    _set_current_action(request, 'hmrc_s4')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_action_hmrc_s5(request):
    """Triage set S5 — enter built schedules for Yes-answered S5 items."""
    _set_current_action(request, 'hmrc_s5')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_action_hmrc_s6(request):
    """Triage set S6 — enter built schedules for Yes-answered S6 items."""
    _set_current_action(request, 'hmrc_s6')
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


@login_required
def iht_start_new_estate(request):
    """
    Create a brand-new draft case and enter S1 directly.

    Belt-and-braces: clears any stale SectionStatus rows for this actor+regime
    before creating the new draft, so the fresh estate always starts at 0-of-N.
    Bypasses the pre-verified summary by calling call_core directly.
    """
    regime, actor, user, pss, crumbs = _setup(request)
    # Clear stale completion flags — ensures new estate never inherits progress
    # from a prior estate whose SectionStatus was not yet re-keyed (e.g. if
    # _promote_case_to_verified ran before this defensive clear was added).
    reset_section_progress(user, regime)
    new_case = create_case(user, regime)
    request.session['case_id'] = str(new_case.case_id)
    for key in ('iht_current_action', 'iht_in_core'):
        request.session.pop(key, None)
    # _setup captured regime_home_url from this view's own request.path
    # (/hmrc/iht/cases/new/), not the orchestrator URL.  Override it in both
    # the PSS (read by section_done when all regime sections are complete) and
    # the top-level session (read by call_core to set PSS return_url for the
    # mid-journey redirect).  Without this, completing S1 sends the user back
    # here, creating a second draft case on every S1 completion.
    orchestrator_url = reverse(
        'dept_hmrc:regime_home', kwargs={'regime_id': regime.regime_id}
    )
    update_session(request, {'regime_home_url': orchestrator_url})  # PSS
    request.session['regime_home_url'] = orchestrator_url           # top-level for call_core
    # Set current_action so _exit_start fires when the user returns from S1.
    # Without this the orchestrator has no context on return and falls through
    # to _render_home with verified_case=None → AttributeError.
    request.session['iht_current_action'] = 'start'
    request.session.modified = True
    # Go straight into S1 — skip the intermediate pre-verified summary page.
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=[{'type': 'section', 'id': 'HMRC_S1'}],
        url_prefix='hmrc',
    )
    return redirect(entry_url)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY FUNCTIONS — set iht_in_core and send user into core sections
# ══════════════════════════════════════════════════════════════════════════════

def _entry_start(request, regime, actor, user, pss, crumbs):
    """
    First visit or explicit start — ensure draft case exists, enter S1.
    """
    draft_case = _get_or_create_draft_case(request, user, regime)
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=[{'type': 'section', 'id': 'HMRC_S1'}],
        url_prefix='hmrc',
    )
    statuses = _get_statuses(actor, user, regime)
    # Render pre-verified home so user sees context before entering S1
    return iht_screen_unverified(
        request, regime, statuses, entry_url, pss, crumbs
    )


def _entry_deceased_details(request, regime, actor, user):
    """
    View/amend deceased details — enter S1.
    """
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=[{'type': 'section', 'id': 'HMRC_S1'}],
        url_prefix='hmrc',
    )
    return redirect(entry_url)


def _entry_reckoner(request, regime, actor, user):
    """
    Estate ready reckoner — enter S2 so user can review/amend
    HMRC_13 (reckoner preference) and HMRC_14 (marital status).
    Exit logic in _exit_reckoner / handle_reckoner decides whether
    to proceed to S3 or return home.
    """
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=[{'type': 'section', 'id': 'HMRC_S2'}],
        url_prefix='hmrc',
    )
    return redirect(entry_url)


def _entry_tailor(request, regime, actor, user):
    """
    Tailor your submission — enter S4/S5/S6 section list.
    """
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=[{'type': 'schedule', 'id': 'HMRC_SCH1'}],
        title='Tailor your submission',
        url_prefix='hmrc',
    )
    return redirect(entry_url)


def _entry_triage_assets(request, regime, actor, user, verified_case,
                         active_items, section_id):
    """
    Triage set assets — build schedule list from Yes-answered questions for
    the given triage section, filtered to schedules that have at least one
    section built. If nothing is built yet, return None (falls through to home).
    """
    triage_set = next((t for t in TRIAGE_SETS if t['section_id'] == section_id), None)
    title = triage_set['name'] if triage_set else section_id
    items = _get_built_schedule_items(active_items, section_id, QUESTION_SCHEDULE_MAP)
    if not items:
        return None
    _enter_core(request)
    entry_url = call_core(
        request, regime, actor, user,
        items=items,
        title=title,
        url_prefix='hmrc',
    )
    return redirect(entry_url)


# ══════════════════════════════════════════════════════════════════════════════
# EXIT FUNCTIONS — post-processing after core returns
# ══════════════════════════════════════════════════════════════════════════════

def _exit_start(request, regime, actor, user, pss, crumbs):
    """
    Returned from S1 first time.
    Run matching — promote to verified if unique, dead end if duplicate.
    """
    from core.interfaces import get_answers as _get_raw_answers
    from .matching import _promote_case_to_verified

    # At this point S1 answers are in DB but no verified case exists yet.
    # Find the draft case to match against.
    draft_case = (
        get_cases(actor, regime)
        .filter(reference__isnull=True)
        .first()
    )
    if not draft_case:
        # Something went wrong — restart
        _clear_current_action(request)
        return redirect(reverse('dept_hmrc:regime_home',
                                kwargs={'regime_id': IHT_REGIME_ID}))

    result, duplicate_case = run_iht_matching(draft_case)

    if result == 'duplicate':
        # Part 3: clean up the rejected draft so deceased details cannot
        # surface as pre-population suggestions on alice's future estates.
        from core.models import Answer as _Answer
        _Answer.objects.filter(case=draft_case, user=actor).delete()
        request.session.pop('case_id', None)
        request.session.modified = True
        draft_case.delete()
        _clear_current_action(request)
        return _render_duplicate(request, duplicate_case, crumbs)

    # Unique — promote the draft to a verified estate, creating a distinct
    # User for the deceased and re-keying answer rows to that User.
    deceased_name_raw = _get_raw_answers(draft_case, ['HMRC_1']).get('HMRC_1') or {}
    _promote_case_to_verified(draft_case, actor, deceased_name_raw)

    request.session['iht_flash'] = {
        'row':  'deceased_details',
        'text': (
            f'We have created a new case for this estate. '
            f'Your reference number is {draft_case.reference}.'
        ),
    }
    request.session.modified = True
    _clear_current_action(request)
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


def _exit_deceased_details(request, verified_case, regime, actor, user, crumbs):
    """
    Returned from S1 amend.
    Run matching — if now conflicts with another estate, dead end.
    If still unique, flash confirmation and return home.
    Existing IHT reference is never changed.
    """
    result, duplicate_case = run_iht_matching(verified_case)

    if result == 'duplicate':
        _clear_current_action(request)
        return _render_duplicate_amend(request, verified_case,
                                       duplicate_case, crumbs)

    request.session['iht_flash'] = {
        'row':  'deceased_details',
        'text': "Deceased's details have been updated.",
    }
    request.session.modified = True
    _clear_current_action(request)
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': IHT_REGIME_ID}))


def _exit_reckoner(request, regime, actor, user, verified_case):
    """
    Returned from S2 or S3.
    Delegates to handle_reckoner which either:
      - returns a redirect into S3 (sets iht_in_core again) → caller returns it
      - returns None (reckoner complete) → caller falls through to home
    """
    result = handle_reckoner(request, regime, actor, user, verified_case)
    if result is not None:
        # Re-entering core (S3) — set iht_in_core again
        _enter_core(request)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# HOME PAGE STATE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_home(request, regime, actor, user, verified_case, crumbs):
    """Build lean action state and pass to iht_screen. Never renders directly."""
    if verified_case:
        hmrc_s1 = Section.objects.get(section_id='HMRC_S1')
        deceased_rows = [
            {
                'label': row['question_text'],
                'value': format_answer_for_display(row['question_type'], row['answer']),
            }
            for row in get_asked_answers_for_section(verified_case, hmrc_s1)
        ]
    else:
        deceased_rows = []
    statuses = _get_statuses(actor, user, regime)

    s1_status           = _section_status(statuses, 'HMRC_S1')
    s2_status           = _section_status(statuses, 'HMRC_S2')
    reckoner_conclusion = _get_reckoner_conclusion(verified_case)
    active_items        = _get_active_triage_items(verified_case)
    flash               = _pop_flash(request)

    actions = _build_action_list(
        request, regime, actor, user,
        verified_case, statuses,
        s1_status, s2_status,
        reckoner_conclusion, active_items, flash,
    )
    return iht_screen(request, regime, verified_case, deceased_rows, actions, crumbs)


def _build_action_list(request, regime, actor, user, verified_case,
                       statuses, s1_status, s2_status,
                       reckoner_conclusion, active_items, flash):
    """
    Build the lean action list for the home page.
    Returns logical state only — no labels, colours, or link text.
    Presentation is added by screen.py / _decorate_actions.
    """
    def _flash_for(row_id):
        if flash and flash.get('row') == row_id:
            return flash.get('text')
        return None

    actions = []

    # ── 1. Deceased's details ──────────────────────────────────────────────────
    actions.append({
        'id':            'deceased_details',
        'status':        s1_status,
        'url':           reverse('dept_hmrc:iht_action_deceased'),
        'flash_message': _flash_for('deceased_details'),
        'hint':          None,
        'extra':         {},
    })

    # ── 2. Estate ready reckoner ───────────────────────────────────────────────
    if not Section.objects.filter(
            section_id='HMRC_S2', regime_id=IHT_REGIME_ID).exists():
        reckoner_status = 'not_configured'
        reckoner_url    = None
    elif not get_permitted_sections(actor, user).filter(
            section_id='HMRC_S2').exists():
        reckoner_status = 'no_permission'
        reckoner_url    = None
    else:
        s3_status = _section_status(statuses, 'HMRC_S3')
        if s2_status == 'complete' and s3_status == 'in_progress':
            reckoner_status = 'in_progress'
        else:
            reckoner_status = s2_status
        reckoner_url = reverse('dept_hmrc:iht_action_reckoner')

    actions.append({
        'id':            'reckoner',
        'status':        reckoner_status,
        'url':           reckoner_url,
        'flash_message': _flash_for('reckoner'),
        'hint':          None,
        'extra':         {'conclusion': reckoner_conclusion},
    })

    # ── 3. Tailor your submission ──────────────────────────────────────────────
    if _should_show_tailor(s2_status, reckoner_conclusion, verified_case):
        triage_status_objs    = statuses.filter(
            section_id__in=TRIAGE_SECTION_IDS
        )
        triage_complete_count = triage_status_objs.filter(
            status='complete'
        ).count()
        triage_in_progress    = triage_status_objs.filter(
            status='in_progress'
        ).exists()

        if triage_complete_count == len(TRIAGE_SECTION_IDS):
            tailor_status = 'complete'
        elif triage_complete_count > 0 or triage_in_progress:
            tailor_status = 'in_progress'
        else:
            tailor_status = 'not_started'

        actions.append({
            'id':            'tailor',
            'status':        tailor_status,
            'url':           reverse('dept_hmrc:iht_action_tailor'),
            'flash_message': _flash_for('tailor'),
            'hint':          'Tell us which assets and liabilities are in the estate',
            'extra':         {},
        })

        # ── 4+. Triage set rows — once all triage sections complete ───────────
        if triage_complete_count == len(TRIAGE_SECTION_IDS):
            for triage_set in TRIAGE_SETS:
                sid       = triage_set['section_id']
                set_items = active_items.get(sid, [])
                rollup    = _triage_set_rollup(sid, set_items, statuses)

                built_items = _get_built_schedule_items(
                    active_items, sid, QUESTION_SCHEDULE_MAP
                )
                action_url = reverse(f'dept_hmrc:iht_action_{triage_set["section_id"].lower()}') \
                    if built_items else '#'
                actions.append({
                    'id':            triage_set['section_id'].lower(),
                    'status':        rollup,
                    'url':           action_url,
                    'flash_message': _flash_for(triage_set['section_id'].lower()),
                    'hint':          None,
                    'extra':         {
                        'section_id': sid,
                        'items':      set_items,
                    },
                })

    return actions


# ══════════════════════════════════════════════════════════════════════════════
# DUPLICATE RENDERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_duplicate(request, duplicate_case, crumbs):
    """First-time matching conflict — estate already exists. Draft has been deleted."""
    return render(request, 'dept_hmrc/iht/duplicate.html', {
        'duplicate_case': duplicate_case,
        'breadcrumbs':    crumbs,
    })


def _render_duplicate_amend(request, case, duplicate_case, crumbs):
    """
    Amend matching conflict — amended details now match another estate.
    Existing IHT reference preserved. User told HMRC will be in touch.
    """
    return render(request, 'dept_hmrc/iht/duplicate_amend.html', {
        'case':           case,
        'duplicate_case': duplicate_case,
        'breadcrumbs':    crumbs,
    })


# ══════════════════════════════════════════════════════════════════════════════
# TRIAGE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_triage_question_ids(section_id):
    """
    Return ordered question IDs for the QuestionSet belonging to a section.
    Reads the first routing node (the Set), then its QuestionSetMember records.
    """
    first_node = (
        Routing.objects
        .filter(section_id=section_id)
        .order_by('order_in_section')
        .values_list('current_node', flat=True)
        .first()
    )
    if not first_node:
        return []
    return list(
        QuestionSetMember.objects
        .filter(question_set_id=first_node)
        .order_by('display_order')
        .values_list('question_id', flat=True)
    )


def _get_active_triage_items(verified_case):
    """
    Build the active items dict: {section_id: [item, ...]}
    Only Yes-answered questions appear.
    """
    if not verified_case:
        return {t['section_id']: [] for t in TRIAGE_SETS}

    result = {}
    for triage_set in TRIAGE_SETS:
        sid   = triage_set['section_id']
        q_ids = _get_triage_question_ids(sid)
        if not q_ids:
            result[sid] = []
            continue
        answers = get_answers(verified_case, q_ids)
        result[sid] = [
            {
                'question_id':    qid,
                'detail_section': None,  # wired per-button when built
            }
            for qid in q_ids
            if answers.get(qid) == 'Yes'
        ]
    return result


def _triage_set_rollup(section_id, set_items, statuses):
    """Rollup status for one triage set's Level 1 row."""
    if not set_items:
        obj    = statuses.filter(section_id=section_id).first()
        status = obj.status if obj else 'not_started'
        return 'complete' if status == 'complete' else 'not_started'

    for item in set_items:
        detail_sid = item['detail_section']
        if detail_sid is None:
            return 'not_started'
        obj    = statuses.filter(section_id=detail_sid).first()
        status = obj.status if obj else 'not_started'
        if status != 'complete':
            return 'in_progress'
    return 'complete'


def _get_built_schedule_items(active_items, section_id, schedule_map):
    """
    Return call_core items list for one triage set's action button.
    Maps Yes-answered question IDs to schedule IDs via schedule_map,
    then filters to schedules that have at least one section built.
    Preserves the triage question display order.
    Returns [] if nothing is built yet.
    """
    from core.models import Section as CoreSection
    yes_questions = [
        item['question_id']
        for item in active_items.get(section_id, [])
    ]
    candidate_schedule_ids = [
        schedule_map[qid]
        for qid in yes_questions
        if qid in schedule_map
    ]
    if not candidate_schedule_ids:
        return []
    built = set(
        CoreSection.objects
        .filter(schedule__schedule_id__in=candidate_schedule_ids)
        .values_list('schedule__schedule_id', flat=True)
    )
    return [
        {'type': 'schedule', 'id': sid}
        for sid in candidate_schedule_ids
        if sid in built
    ]


# ══════════════════════════════════════════════════════════════════════════════
# SMALL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _setup(request):
    """
    Common setup. Returns (regime, actor, user, pss, crumbs).
    Requires choose_user gate to have already run (user_id in session).
    """
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'),
        regime_id=IHT_REGIME_ID,
    )
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    crumbs = _get_crumbs(regime)
    update_session(request, {
        'breadcrumbs':     crumbs,
        'regime_home_url': request.path,
        'active_dept':     'HMRC',
        'regime_id':       regime.regime_id,
    })
    pss = get_session(request)
    return regime, actor, user, pss, crumbs


def _get_crumbs(regime):
    return [
        {'label': 'HMRC',             'url': '/hmrc/'},
        {'label': regime.regime_name, 'url': None},
    ]


def _get_verified_case(user, regime):
    return (
        get_cases(user, regime)
        .filter(reference__isnull=False)
        .first()
    )


def _get_verified_cases(actor, regime):
    """
    All verified IHT cases this actor can work on, most recent first.

    Two sources are unioned:
    - Post-promotion: cases where actor holds a case-scoped Permission
      (actor=alice, user=deceased) created by _promote_case_to_verified.
    - Direct user: cases where actor is themselves the Case subject
      (covers test data and any legacy pre-promotion cases).
    """
    case_ids_via_perm = list(
        Permission.objects
        .filter(actor=actor, regime=regime, case__isnull=False,
                case__reference__isnull=False)
        .values_list('case_id', flat=True)
    )
    return (
        Case.objects.filter(
            Q(case_id__in=case_ids_via_perm) |
            Q(user=actor, regime=regime, reference__isnull=False)
        ).distinct().order_by('-started_at')
    )


def _enter_core(request):
    """Signal that we are sending the user into core sections."""
    request.session['iht_in_core'] = True
    request.session.modified = True


def _clear_in_core(request):
    request.session.pop('iht_in_core', None)
    request.session.modified = True


def _set_current_action(request, action_id):
    request.session['iht_current_action'] = action_id
    request.session.modified = True


def _get_current_action(request):
    return request.session.get('iht_current_action')


def _clear_current_action(request):
    request.session.pop('iht_current_action', None)
    request.session.modified = True


def _get_statuses(actor, user, regime):
    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )
    return SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted
    )


def _section_status(statuses, section_id):
    obj = statuses.filter(section_id=section_id).first()
    return obj.status if obj else 'not_started'


def _get_reckoner_conclusion(verified_case):
    if not verified_case:
        return None
    try:
        return IHTReckoner.objects.get(case=verified_case).conclusion
    except IHTReckoner.DoesNotExist:
        return None


def _should_show_tailor(s2_status, reckoner_conclusion, verified_case):
    """Show tailor when S2 complete AND reckoner says may be payable OR HMRC_13=No."""
    if s2_status != 'complete':
        return False
    if reckoner_conclusion == 'may_be_payable':
        return True
    if verified_case:
        ans = get_answers(verified_case, ['HMRC_13'])
        if 'No' in (ans.get('HMRC_13') or ''):
            return True
    return False


def _pop_flash(request):
    flash = request.session.pop('iht_flash', None)
    if flash:
        request.session.modified = True
    return flash


def _get_or_create_draft_case(request, user, regime):
    """Return existing draft case or create one. Writes case_id to session."""
    existing_case_id = request.session.get('case_id')
    draft_case = None

    if existing_case_id:
        try:
            draft_case = Case.objects.get(
                case_id=existing_case_id,
                user=user,
                regime=regime,
                reference__isnull=True,
            )
        except Case.DoesNotExist:
            pass

    if draft_case is None:
        draft_case = (
            get_cases(user, regime)
            .filter(reference__isnull=True)
            .first()
        )

    if draft_case is None:
        draft_case = create_case(user, regime)

    if request.session.get('case_id') != draft_case.case_id:
        request.session['case_id'] = draft_case.case_id
        request.session.modified = True

    return draft_case
