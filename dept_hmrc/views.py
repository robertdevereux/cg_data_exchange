"""
dept_hmrc/views.py — HMRC department views.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.interfaces import call_regime, create_case, get_cases
from core.views_layer1 import regime_schedule_sections, regime_schedules  # noqa: F401 — re-exported for urls.py
from core.models import Answer, Case, Regime, SectionStatus
from core.nav_reference import _resolve_user
from core.permissions import get_permitted_sections
from core.session import get_acting_for_name, get_session, update_session


# ── IHT helpers ───────────────────────────────────────────────────────────────

def _generate_iht_reference():
    """Return the next sequential IHT reference (IHT-000000001, IHT-000000002, …)."""
    from django.db.models import Max
    last = (
        Case.objects
        .filter(reference__startswith='IHT-')
        .aggregate(max_ref=Max('reference'))
        ['max_ref']
    )
    if last:
        try:
            next_num = int(last[4:]) + 1  # strip 'IHT-', parse int
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    return f'IHT-{next_num:09d}'


def _format_date(answer):
    """Format a date-type answer dict {day, month, year} as DD/MM/YYYY."""
    if not isinstance(answer, dict):
        return str(answer) if answer else ''
    day   = str(answer.get('day', '')).zfill(2)
    month = str(answer.get('month', '')).zfill(2)
    year  = answer.get('year', '')
    return f'{day}/{month}/{year}'


def _get_iht_answers(case):
    """
    Return a dict of deceased's details for a given Case.
    Keys: name_display, dob_display, dod_display, nino, last_name, dod_raw.
    """
    def _ans(qid):
        try:
            return Answer.objects.get(case=case, question_id=qid).answer
        except Answer.DoesNotExist:
            return None

    name_raw = _ans('HMRC_1')  # personal_name dict
    dod_raw  = _ans('HMRC_2')  # date dict  — date of death
    dob_raw  = _ans('HMRC_3')  # date dict  — date of birth
    nino_raw = _ans('HMRC_4')  # plain text

    if isinstance(name_raw, dict):
        parts = [
            name_raw.get('title', ''),
            name_raw.get('first_name', ''),
            name_raw.get('middle_name', ''),
            name_raw.get('last_name', ''),
        ]
        name_display = ' '.join(p for p in parts if p).strip()
        last_name    = name_raw.get('last_name', '').lower().strip()
    else:
        name_display = str(name_raw) if name_raw else ''
        last_name    = name_display.split()[-1].lower() if name_display else ''

    return {
        'name_display': name_display,
        'dob_display':  _format_date(dob_raw),
        'dod_display':  _format_date(dod_raw),
        'nino':         nino_raw or '',
        'last_name':    last_name,
        'dod_raw':      dod_raw,
    }


def run_iht_matching(case):
    """
    Compare the current case's deceased details against all verified IHT cases.

    Match criterion (PoC): same last name AND same date of death (exact dict match).

    Returns:
        ('unique',    None)          — no matching verified case found
        ('duplicate', matching_case) — a verified case matches
    """
    current = _get_iht_answers(case)
    if not current['last_name'] or not current['dod_raw']:
        return ('unique', None)

    verified = Case.objects.filter(
        regime_id='HMRC_IHT',
        reference__isnull=False,
    ).exclude(case_id=case.case_id)

    for vc in verified:
        other = _get_iht_answers(vc)
        if (other['last_name'] == current['last_name']
                and other['dod_raw'] == current['dod_raw']):
            return ('duplicate', vc)

    return ('unique', None)


# ── IHT post-confirm matching view ────────────────────────────────────────────

@login_required
def iht_matching_result(request, case_id):
    """
    Called by section_done via post_confirm_redirect after HMRC_S1 is confirmed.

    Runs the duplicate-estate check:
    - unique   → assign reference, save, redirect to regime home
    - duplicate → render iht_duplicate.html
    """
    case = get_object_or_404(Case, case_id=case_id, regime_id='HMRC_IHT')

    result, duplicate_case = run_iht_matching(case)

    if result == 'unique':
        case.reference = _generate_iht_reference()
        case.save(update_fields=['reference'])
        return redirect(reverse('dept_hmrc:regime_home', kwargs={'regime_id': 'HMRC_IHT'}))

    # Duplicate found
    return render(request, 'dept_hmrc/iht_duplicate.html', {
        'case':           case,
        'duplicate_case': duplicate_case,
        'breadcrumbs': [
            {'label': 'HMRC',              'url': '/hmrc/'},
            {'label': 'Inheritance Tax',   'url': reverse('dept_hmrc:regime_home', kwargs={'regime_id': 'HMRC_IHT'})},
            {'label': 'Duplicate estate',  'url': None},
        ],
    })


@login_required
def dept_home(request):
    """HMRC department landing page — lists all HMRC regimes.
    Permission enforcement happens at the section level, not here.
    """
    request.session['active_dept'] = 'HMRC'
    actor = request.user
    pss   = get_session(request)
    update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
    pss = get_session(request)
    user  = _resolve_user(pss, actor)

    regimes = Regime.objects.filter(dept_id='HMRC').order_by('display_order', 'regime_name')

    return render(request, 'dept_hmrc/dept_home.html', {
        'regimes':     regimes,
        'acting_for':  get_acting_for_name(pss),
        'breadcrumbs': [
            {'label': 'HMRC', 'url': None},
        ],
    })


@login_required
def regime_list(request):
    """Redirect to dept_home — the landing page is the regime list for HMRC."""
    return redirect('dept_hmrc:dept_home')


@login_required
def regime_home(request, regime_id):
    """HMRC regime landing page — start/continue button and completion status."""
    request.session['active_dept'] = 'HMRC'
    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'),
        regime_id=regime_id,
    )
    actor = request.user
    pss   = get_session(request)
    user  = _resolve_user(pss, actor)

    crumbs = [
        {'label': 'HMRC',             'url': '/hmrc/'},
        {'label': regime.regime_name, 'url': None},
    ]

    # ── HMRC_IHT bespoke flow ─────────────────────────────────────────────────
    if regime_id == 'HMRC_IHT':
        # Check for a verified (reference-assigned) case for this user/regime
        verified_case = (
            get_cases(user, regime)
            .filter(reference__isnull=False)
            .first()
        )

        if verified_case:
            # Estate already verified — show summary homepage, no new case
            details = _get_iht_answers(verified_case)

            # Still call call_regime so session keys (permitted sections etc.)
            # are set for any "Change" links
            entry_url = call_regime(request, regime, actor, user, url_prefix='hmrc')
            pss = get_session(request)
            update_session(request, {
                'breadcrumbs':     crumbs,
                'regime_home_url': request.path,
                'active_dept':     'HMRC',
                'regime_id':       regime.regime_id,
            })

            permitted = get_permitted_sections(actor, user).filter(
                Q(regime=regime) | Q(schedule__regime=regime)
            )
            statuses     = SectionStatus.objects.filter(user=user, regime=regime, section__in=permitted)
            s1_status    = statuses.filter(section_id='HMRC_S1').first()
            s1_status_lbl = (s1_status.status if s1_status else 'not_started')

            return render(request, f'dept_hmrc/{regime_id}_home.html', {
                'regime':        regime,
                'verified_case': verified_case,
                'deceased_name': details['name_display'],
                'deceased_dob':  details['dob_display'],
                'deceased_dod':  details['dod_display'],
                'deceased_nino': details['nino'],
                'reference':     verified_case.reference,
                'entry_url':     entry_url,
                's1_status':     s1_status_lbl,
                'acting_for':    get_acting_for_name(pss),
                'breadcrumbs':   crumbs,
            })

        else:
            # No verified case — create a fresh draft and wire the matching hook
            draft_case = create_case(user, regime)
            # Set up full session via call_regime (bootstraps permitted sections,
            # writes case_id, return_url etc.) — then overwrite case_id with the
            # freshly created draft so the hook knows which case to match.
            entry_url = call_regime(request, regime, actor, user, url_prefix='hmrc')
            request.session['case_id']              = draft_case.case_id
            request.session['post_confirm_redirect'] = (
                reverse('dept_hmrc:iht_matching_result',
                        kwargs={'case_id': draft_case.case_id})
            )
            request.session.modified = True

            pss = get_session(request)
            update_session(request, {
                'breadcrumbs':     crumbs,
                'regime_home_url': request.path,
                'active_dept':     'HMRC',
                'regime_id':       regime.regime_id,
            })

            permitted = get_permitted_sections(actor, user).filter(
                Q(regime=regime) | Q(schedule__regime=regime)
            )
            statuses     = SectionStatus.objects.filter(user=user, regime=regime, section__in=permitted)
            total        = statuses.count()
            complete     = statuses.filter(status='complete').count()
            all_complete = total > 0 and complete == total

            return render(request, f'dept_hmrc/{regime_id}_home.html', {
                'regime':        regime,
                'verified_case': None,
                'total':         total,
                'complete':      complete,
                'all_complete':  all_complete,
                'entry_url':     entry_url,
                'acting_for':    get_acting_for_name(pss),
                'breadcrumbs':   crumbs,
            })

    # ── Generic HMRC regime home ──────────────────────────────────────────────
    entry_url = call_regime(request, regime, actor, user, url_prefix='hmrc')

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime=regime) | Q(schedule__regime=regime)
    )
    statuses = SectionStatus.objects.filter(
        user=user, regime=regime, section__in=permitted,
    )
    total        = statuses.count()
    complete     = statuses.filter(status='complete').count()
    all_complete = total > 0 and complete == total

    pss = get_session(request)
    update_session(request, {
        'breadcrumbs':     crumbs,
        'regime_home_url': request.path,
        'active_dept':     'HMRC',
        'regime_id':       regime.regime_id,
    })

    templates = [
        f'dept_hmrc/{regime_id}_home.html',
        'dept_hmrc/regime_home.html',
    ]
    return render(request, templates, {
        'regime':       regime,
        'total':        total,
        'complete':     complete,
        'all_complete': all_complete,
        'entry_url':    entry_url,
        'acting_for':   get_acting_for_name(pss),
        'breadcrumbs':  crumbs,
    })


@login_required
def select_section(request, regime_id):
    """
    Pattern B task-list: all permitted sections in this HMRC regime (no schedule).
    Sets return_url so section_done redirects back here.
    """
    actor  = request.user
    pss    = get_session(request)
    user   = _resolve_user(pss, actor)
    regime = get_object_or_404(Regime.objects.filter(dept_id='HMRC'), regime_id=regime_id)

    permitted = get_permitted_sections(actor, user).filter(
        Q(regime_id=regime_id) | Q(schedule__regime_id=regime_id)
    )

    section_statuses = {
        ss.section_id: ss.status
        for ss in SectionStatus.objects.filter(
            user=user, regime=regime, section__in=permitted,
        )
    }

    _status_label = {
        'not_started': 'Not started',
        'in_progress': 'In progress',
        'complete':    'Complete',
    }

    section_data = []
    for section in permitted.order_by('display_order', 'section_name'):
        status = section_statuses.get(section.section_id, 'not_started')
        if section.section_type in (1, 2):
            action_url = f'/section/{section.section_id}/table/'
        else:
            action_url = f'/section/{section.section_id}/start/'
        section_data.append({
            'section':        section,
            'status':         status,
            'status_display': _status_label.get(status, 'Not started'),
            'action_url':     action_url,
        })

    regime_home_url = pss.get(
        'regime_home_url',
        reverse('dept_hmrc:regime_home', kwargs={'regime_id': regime_id}),
    )
    back_url   = reverse('dept_hmrc:dept_home')
    return_url = reverse('dept_hmrc:select_section', kwargs={'regime_id': regime_id})
    crumbs = pss.get('breadcrumbs') or [
        {'label': 'HMRC',             'url': '/hmrc/'},
        {'label': regime.regime_name, 'url': regime_home_url},
    ]

    update_session(request, {
        'return_url':        return_url,
        'schedule_id':       None,
        'breadcrumbs':       crumbs,
        'regime_home_url':   regime_home_url,
        'schedule_list_url': None,
    })

    return render(request, 'core/select_section.html', {
        'regime':      regime,
        'schedule':    None,
        'sections':    section_data,
        'back_url':    back_url,
        'breadcrumbs': crumbs,
        'acting_for':  get_acting_for_name(pss),
    })
