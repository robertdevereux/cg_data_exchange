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
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.interfaces import call_sections, create_case, get_answers, get_cases
from core.models import Case, Regime, Routing, Section, SectionStatus
from core.models import QuestionSetMember
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session
from dept_hmrc.models import IHTReckoner

from .matching import run_iht_matching
from .reckoner import handle_reckoner
from .screen import iht_screen, iht_screen_unverified
from .utils import _get_iht_answers


IHT_REGIME_ID = 'HMRC_IHT'

TRIAGE_SECTION_IDS = ['HMRC_S4', 'HMRC_S5', 'HMRC_S6']

TRIAGE_SETS = [
    {'section_id': 'HMRC_S4', 'id': 'triage_common'},
    {'section_id': 'HMRC_S5', 'id': 'triage_pensions'},
    {'section_id': 'HMRC_S6', 'id': 'triage_other'},
]


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def iht_orchestrate(request):
    """
    IHT regime controller. Reads state, dispatches — never renders directly.
    Called on every visit to /hmrc/regime/HMRC_IHT/.
    """
    regime, actor, user, pss, crumbs = _setup(request)
    current_action      = _get_current_action(request)
    verified_case       = _get_verified_case(user, regime)
    returning_from_core = request.session.pop('iht_in_core', False)
    request.session.modified = True

    # ── Bootstrap: very first visit, no case, no action set ───────────────────
    if not verified_case and not current_action:
        _set_current_action(request, 'start')
        current_action = 'start'

    # ── ENTRY — send user into core ────────────────────────────────────────────
    if not returning_from_core:
        if current_action == 'start':
            return _entry_start(request, regime, actor, user, pss, crumbs)
        if current_action == 'deceased_details':
            return _entry_deceased_details(request, regime, actor, user)
        if current_action == 'reckoner':
            return _entry_reckoner(request, regime, actor, user, verified_case)
        if current_action == 'tailor':
            return _entry_tailor(request, regime, actor, user)
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


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY FUNCTIONS — set iht_in_core and send user into core sections
# ══════════════════════════════════════════════════════════════════════════════

def _entry_start(request, regime, actor, user, pss, crumbs):
    """
    First visit or explicit start — ensure draft case exists, enter S1.
    """
    draft_case = _get_or_create_draft_case(request, user, regime)
    _enter_core(request)
    entry_url = call_sections(
        request, regime, actor, user,
        section_ids=['HMRC_S1'], url_prefix='hmrc',
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
    entry_url = call_sections(
        request, regime, actor, user,
        section_ids=['HMRC_S1'], url_prefix='hmrc',
    )
    return redirect(entry_url)


def _entry_reckoner(request, regime, actor, user, verified_case):
    """
    Estate ready reckoner — enter S2 (S3 follows on exit if needed).
    Delegates to handle_reckoner which decides whether to enter S2 or S3.
    Sets iht_in_core before any redirect into core.
    """
    _enter_core(request)
    result = handle_reckoner(request, regime, actor, user, verified_case)
    if result is not None:
        return result
    # handle_reckoner returned None — reckoner already complete, go home
    _clear_in_core(request)
    _clear_current_action(request)
    return _render_home(request, regime, actor, user, verified_case,
                        _get_crumbs(regime))


def _entry_tailor(request, regime, actor, user):
    """
    Tailor your submission — enter S4/S5/S6 section list.
    """
    _enter_core(request)
    entry_url = call_sections(
        request, regime, actor, user,
        section_ids=TRIAGE_SECTION_IDS,
        title='Tailor your submission',
        url_prefix='hmrc',
    )
    return redirect(entry_url)


# ══════════════════════════════════════════════════════════════════════════════
# EXIT FUNCTIONS — post-processing after core returns
# ══════════════════════════════════════════════════════════════════════════════

def _exit_start(request, regime, actor, user, pss, crumbs):
    """
    Returned from S1 first time.
    Run matching — create IHT reference if unique, dead end if duplicate.
    """
    # At this point S1 answers are in DB but no verified case exists yet.
    # Find the draft case to match against.
    draft_case = (
        get_cases(user, regime)
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
        _clear_current_action(request)
        return _render_duplicate(request, draft_case, duplicate_case, crumbs)

    # Unique — assign reference
    from .matching import _generate_iht_reference
    draft_case.reference = _generate_iht_reference()
    draft_case.save(update_fields=['reference'])

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
    details  = _get_iht_answers(verified_case)
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
    return iht_screen(request, regime, verified_case, details, actions, crumbs)


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
        if s2_status == 'complete' and s3_status in ('complete', 'in_progress'):
            reckoner_url = '/section/HMRC_S3/review/'
        else:
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

                actions.append({
                    'id':            triage_set['id'],
                    'status':        rollup,
                    'url':           '#',
                    'flash_message': _flash_for(triage_set['id']),
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

def _render_duplicate(request, case, duplicate_case, crumbs):
    """First-time matching conflict — estate already exists."""
    return render(request, 'dept_hmrc/iht/duplicate.html', {
        'case':           case,
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
            return 'in_progress'
        obj    = statuses.filter(section_id=detail_sid).first()
        status = obj.status if obj else 'not_started'
        if status != 'complete':
            return 'in_progress'
    return 'complete'


# ══════════════════════════════════════════════════════════════════════════════
# SMALL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _setup(request):
    """Common setup. Returns (regime, actor, user, pss, crumbs)."""
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'),
        regime_id=IHT_REGIME_ID,
    )
    actor = request.user
    update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
    pss  = get_session(request)
    user = _resolve_user(pss, actor)

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
