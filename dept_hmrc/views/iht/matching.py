"""
dept_hmrc/views/iht/matching.py — IHT estate duplicate-check and reference assignment.
"""
from core.models import Case

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


