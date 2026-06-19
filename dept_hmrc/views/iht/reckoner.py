"""
dept_hmrc/views/iht/reckoner.py

Orchestration logic for the IHT Ready Reckoner.

Entry point: handle_reckoner(request, regime, actor, user, case)
  Called from regime_home after HMRC_S2 is confirmed complete.
  Returns an HttpResponseRedirect into the appropriate reckoner section,
  or None if no reckoner action is needed (caller then renders home page).

HMRC_13 answer values:
  "Yes, I'd like help working that out"
  "No, I know a full return is required and want to get started"

HMRC_14 answer values (marital status):
  "Single"
  "Married or in a civil partnership"
  "Widowed or a surviving civil partner"

Section routing:
  HMRC_13 = No                         → None (main flow — home page renders)
  HMRC_13 = Yes + HMRC_14 = Single     → HMRC_S3
  HMRC_13 = Yes + HMRC_14 = Married    → None (Part 2 — not yet built)
  HMRC_13 = Yes + HMRC_14 = Widowed    → None (Part 3 — not yet built)
  HMRC_13 missing / HMRC_14 missing    → None (home page renders with warning)
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.interfaces import call_sections, get_answers, get_cases

IHT_REGIME_ID = 'HMRC_IHT'

# HMRC_13 answer value constants
HMRC13_YES = "Yes, I'd like help working that out"
HMRC13_NO  = "No, I know a full return is required and want to get started"

# HMRC_14 answer value constants
HMRC14_SINGLE  = "Neither of the above — for example single, divorced, or living with a partner but not married"
HMRC14_MARRIED = "Married, with their spouse surviving them"
HMRC14_WIDOWED = "Themselves a widow or widower, their spouse having died before them and not subsequently remarried"

# Reckoner section IDs by marital status
RECKONER_SECTION = {
    HMRC14_SINGLE: 'HMRC_S3',
    # HMRC14_MARRIED: 'HMRC_S4',
    # HMRC14_WIDOWED: 'HMRC_S5',
}



def _save_conclusion(request, case, conclusion):
    """
    Write reckoner conclusion to IHTReckoner and redirect to regime home.
    conclusion: 'not_payable' | 'may_be_payable' | 'knock_out'
    """
    from django.urls import reverse
    from dept_hmrc.models import IHTReckoner

    IHTReckoner.objects.update_or_create(
        case=case,
        defaults={
            'conclusion':     conclusion,
            'question_text':  '',
            'threshold':      None,
            'answer':         '',
        },
    )
    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': 'HMRC_IHT'}))


def get_reckoner_state(request, regime, actor, user, case):
    """
    Called after HMRC_S3 is complete and no IHTReckoner row exists yet.
    Reads S3 answers, determines outcome, and either:
      - saves a knock-out conclusion directly to IHTReckoner, or
      - computes the threshold and redirects to the bespoke threshold view.
    """
    from django.urls import reverse
    from core.interfaces import get_answers

    s3_ans = get_answers(case, [
        'HMRC_10', 'HMRC_11', 'HMRC_15', 'HMRC_7', 'HMRC_8', 'HMRC_9'
    ])

    hmrc10 = s3_ans.get('HMRC_10') or []
    hmrc11 = s3_ans.get('HMRC_11') or []
    hmrc15 = s3_ans.get('HMRC_15') or {}
    hmrc9  = s3_ans.get('HMRC_9')

    # Normalise checkbox answers to lists
    if isinstance(hmrc10, str):
        hmrc10 = [hmrc10]
    if isinstance(hmrc11, str):
        hmrc11 = [hmrc11]

    # ── Knock-out check ───────────────────────────────────────────────────────
    KNOCK_OUT_OPTIONS = {
        'Transfers into trust',
        'Assets sold at undervalue',
        'Unused pension funds',
        'Gifts with reservation',
    }
    if any(opt in KNOCK_OUT_OPTIONS for opt in hmrc11):
        return _save_conclusion(request, case, 'knock_out')

    # ── Compute RNRB from home share ──────────────────────────────────────────
    rnrb = 0
    if hmrc9:
        try:
            home_value = float(str(hmrc9).replace(',', '').replace('£', '').strip())
            rnrb = min(home_value, 175000)
        except (ValueError, TypeError):
            rnrb = 0

    # ── Compute taper-adjusted gift total ────────────────────────────────────
    TAPER_RATES = [
        ('Year 1 — gifts made in the year before death', 1.0),
        ('Year 2 — gifts made 2 years before death',    1.0),
        ('Year 3 — gifts made 3 years before death',    1.0),
        ('Year 4 — gifts made 4 years before death',    0.8),
        ('Year 5 — gifts made 5 years before death',    0.6),
        ('Year 6 — gifts made 6 years before death',    0.4),
        ('Year 7 — gifts made 7 years before death',    0.2),
    ]

    taper_gifts = 0
    if isinstance(hmrc15, dict):
        for label, rate in TAPER_RATES:
            try:
                val = float(str(hmrc15.get(label) or '0')
                            .replace(',', '').replace('£', '').strip())
                taper_gifts += val * rate
            except (ValueError, TypeError):
                pass

    # ── Compute threshold ─────────────────────────────────────────────────────
    threshold = int(325000 + rnrb - taper_gifts)

    # Store threshold in session for the bespoke view
    request.session['iht_reckoner_threshold'] = threshold
    request.session['iht_reckoner_case_id']   = str(case.case_id)
    request.session.modified = True

    return redirect(reverse('dept_hmrc:iht_reckoner_threshold'))


@login_required
def iht_reckoner_compute(request):
    """
    Intercepts section_done after S3 completion (via post_confirm_redirect).
    Deletes any stale IHTReckoner row and calls get_reckoner_state fresh.
    This ensures the threshold view is always shown after S3 confirms,
    whether on first entry or after View / amend.
    """
    from core.models import Regime
    from core.session import get_session, update_session
    from core.nav_reference import _resolve_user
    from dept_hmrc.models import IHTReckoner
    from django.shortcuts import get_object_or_404

    regime = get_object_or_404(
        Regime.objects.filter(dept_id='HMRC'),
        regime_id=IHT_REGIME_ID,
    )
    actor = request.user
    update_session(request, {'user_id': actor.pk, 'actor_id': actor.pk})
    pss  = get_session(request)
    user = _resolve_user(pss, actor)

    verified_case = (
        get_cases(user, regime)
        .filter(reference__isnull=False)
        .first()
    )

    if not verified_case:
        return redirect(reverse('dept_hmrc:regime_home',
                                kwargs={'regime_id': 'HMRC_IHT'}))

    # Delete stale conclusion so get_reckoner_state runs fresh
    IHTReckoner.objects.filter(case=verified_case).delete()

    return get_reckoner_state(request, regime, actor, user, verified_case)


def handle_reckoner(request, regime, actor, user, case):
    """
    Called from regime_home when HMRC_S2 is complete.

    Reads HMRC_13 and HMRC_14 answers and decides what to do next.

    Returns:
      HttpResponseRedirect  — if we should go straight into a reckoner section
      None                  — if the home page should render normally
    """
    ans    = get_answers(case, ['HMRC_13', 'HMRC_14'])
    hmrc13 = ans['HMRC_13']
    hmrc14 = ans['HMRC_14']


    # HMRC_13 = No (or missing) → main flow, home page renders
    if hmrc13 != HMRC13_YES:
        return None

    # HMRC_13 = Yes → look up which reckoner section to call
    section_id = RECKONER_SECTION.get(hmrc14)

    if section_id is None:
        # Married or Widowed — reckoner parts not yet built;
        # home page renders with "not yet available" messaging
        return None

    # If section already complete → post-section orchestration
    from core.models import SectionStatus
    status = SectionStatus.objects.filter(
        user=case.user, regime=regime, section_id=section_id
    ).first()
    if status and status.status == 'complete':
        from dept_hmrc.models import IHTReckoner
        if IHTReckoner.objects.filter(case=case).exists():
            return None
        return get_reckoner_state(request, regime, actor, user, case)

    # Section not yet complete → redirect straight in
    request.session['iht_in_core'] = True
    request.session.modified = True
    entry_url = call_sections(
        request, regime, actor, user,
        section_ids=[section_id],
        url_prefix='hmrc',
    )
    return redirect(entry_url)


@login_required
@require_http_methods(['GET', 'POST'])
def iht_reckoner_threshold(request):
    """
    Bespoke dept view — renders a single computed radio question:
    "Was the total value of the estate less than £X?"

    Threshold is passed via session from get_reckoner_state.
    On POST, stores conclusion to IHTReckoner and redirects to regime home.
    """
    from django.shortcuts import render
    from django.urls import reverse
    from core.models import Case
    from dept_hmrc.models import IHTReckoner

    threshold = request.session.get('iht_reckoner_threshold')
    case_id   = request.session.get('iht_reckoner_case_id')

    # Guard: if session data missing, redirect home
    if not threshold or not case_id:
        return redirect(reverse('dept_hmrc:regime_home',
                                kwargs={'regime_id': 'HMRC_IHT'}))

    try:
        case = Case.objects.get(case_id=case_id)
    except Case.DoesNotExist:
        return redirect(reverse('dept_hmrc:regime_home',
                                kwargs={'regime_id': 'HMRC_IHT'}))

    threshold_display = f'£{int(threshold):,}'
    question_text     = (f'Was the total value of the estate less than '
                         f'{threshold_display}?')
    hint = ('Include all assets — property, savings, investments, and '
            'personal possessions — but not gifts already declared above.')
    back_url = reverse('dept_hmrc:regime_home',
                       kwargs={'regime_id': 'HMRC_IHT'})

    if request.method == 'GET':
        # Check for a previously stored answer (re-entry)
        existing = IHTReckoner.objects.filter(case=case).first()
        current_answer = existing.answer if existing else None

        return render(request, 'core/question_radio.html', {
            'question_text':  question_text,
            'options':        ['Yes', 'No'],
            'back_url':       back_url,
            'hint':           hint,
            'error':          None,
            'guidance':       None,
            'provenance':     None,
            'current_answer': current_answer,
        })

    # POST
    answer = request.POST.get('answer')
    if not answer:
        return render(request, 'core/question_radio.html', {
            'question_text':  question_text,
            'options':        ['Yes', 'No'],
            'back_url':       back_url,
            'hint':           hint,
            'error':          'Please select an answer.',
            'guidance':       None,
            'provenance':     None,
            'current_answer': None,
        })

    conclusion = 'not_payable' if answer == 'Yes' else 'may_be_payable'

    IHTReckoner.objects.update_or_create(
        case=case,
        defaults={
            'conclusion':    conclusion,
            'question_text': question_text,
            'threshold':     int(threshold),
            'answer':        answer,
        },
    )

    # Clear session threshold data
    request.session.pop('iht_reckoner_threshold', None)
    request.session.pop('iht_reckoner_case_id',   None)
    request.session.modified = True

    return redirect(reverse('dept_hmrc:regime_home',
                            kwargs={'regime_id': 'HMRC_IHT'}))
