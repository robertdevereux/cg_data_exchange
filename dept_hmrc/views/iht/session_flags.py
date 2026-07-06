"""
dept_hmrc/views/iht/session_flags.py — IHT session-flag helpers.

Extracted here so reckoner.py can import _enter_core without creating a
circular dependency (orchestrate.py imports from reckoner.py).

Session keys managed here:
  iht_in_core          — True while the user is inside core sections
  iht_current_action   — which action button is active
"""


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
