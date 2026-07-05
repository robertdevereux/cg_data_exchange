"""
dept_hmrc/views/iht/matching.py — IHT estate duplicate-check and reference assignment.
"""
from core.models import Answer, Case, Permission, SectionStatus, User

from .utils import _get_iht_answers


IHT_REGIME_ID = 'HMRC_IHT'

def _generate_iht_reference():
    """Return the next sequential IHT reference (IHT-000000001, …)."""
    from django.db.models import Max
    last = (
        Case.objects
        .filter(reference__startswith='IHT-')
        .aggregate(max_ref=Max('reference'))
        ['max_ref']
    )
    if last:
        try:
            next_num = int(last[4:]) + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    return f'IHT-{next_num:09d}'


def _promote_case_to_verified(case, actor, deceased_name):
    """
    On a unique S1 match, promote the draft case to a verified estate.

    Creates a distinct, inactive User representing the deceased, re-keys all
    Answer rows from the actor to that User (preventing deceased details from
    surfacing as pre-population suggestions on the actor's own future estates),
    assigns an IHT reference, transfers Case ownership, and grants the actor
    continued access via a case-scoped Permission.

    Returns the newly created deceased User.
    """
    if isinstance(deceased_name, dict):
        first_name = deceased_name.get('first_name', '')
        last_name  = deceased_name.get('last_name', '')
    else:
        parts      = str(deceased_name).split() if deceased_name else []
        first_name = parts[0] if len(parts) > 1 else ''
        last_name  = parts[-1] if parts else ''

    deceased = User(
        username   = f'ihtsubject_{case.case_id}',
        first_name = first_name,
        last_name  = last_name,
        is_active  = False,
    )
    deceased.set_unusable_password()
    deceased.save()

    # Re-key answers and section statuses: deceased is now the subject; actor's
    # data is no longer associated with this case, so neither pre-population
    # nor completion flags bleed across estates.
    # SectionStatus has a unique constraint on (user, regime, section) with no
    # case_id — safe to re-key all of actor's IHT statuses here because only
    # one draft is active at a time (single session case_id).
    Answer.objects.filter(case=case, user=actor).update(user=deceased)
    SectionStatus.objects.filter(user=actor, regime=case.regime).update(user=deceased)

    # Transfer case ownership and assign reference
    case.user      = deceased
    case.reference = _generate_iht_reference()
    case.save()

    # Grant actor continued access to work on the deceased's case
    Permission.objects.create(
        actor=actor,
        user=deceased,
        regime=case.regime,
        case=case,
        section=None,
        can_delegate=False,
    )

    return deceased


def run_iht_matching(case):
    """
    Compare the current case's deceased details against all verified IHT cases.
    Returns ('unique', None) or ('duplicate', matching_case).
    """
    current = _get_iht_answers(case)
    if not current['last_name'] or not current['dod_raw']:
        return ('unique', None)

    verified = Case.objects.filter(
        regime_id=IHT_REGIME_ID,
        reference__isnull=False,
    ).exclude(case_id=case.case_id)

    for vc in verified:
        other = _get_iht_answers(vc)
        if (other['last_name'] == current['last_name']
                and other['dod_raw'] == current['dod_raw']):
            return ('duplicate', vc)

    return ('unique', None)


