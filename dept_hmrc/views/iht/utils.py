"""
dept_hmrc/views/iht/utils.py — shared IHT helpers.
"""
from core.interfaces import format_date, get_answers


def _get_iht_answers(case):
    """
    Return a dict of deceased's details for a given Case.
    Keys: name_display, dob_display, dod_display, nino, last_name, dod_raw.
    """
    answers  = get_answers(case, ['HMRC_1', 'HMRC_2', 'HMRC_3', 'HMRC_4'])
    name_raw = answers['HMRC_1']
    dod_raw  = answers['HMRC_2']
    dob_raw  = answers['HMRC_3']
    nino_raw = answers['HMRC_4']

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
        'dob_display':  format_date(dob_raw),
        'dod_display':  format_date(dod_raw),
        'nino':         nino_raw or '',
        'last_name':    last_name,
        'dod_raw':      dod_raw,
    }
