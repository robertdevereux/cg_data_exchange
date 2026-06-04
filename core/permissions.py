"""
Permission expansion functions for Layer 1 navigation.

The Permission model supports three grant scopes:
  1. Section-level:  regime set, section set   → specific section only
  2. Regime-level:   regime set, section None  → all sections of that regime
  3. All-regime:     both None                 → all sections across all regimes

get_permitted_sections(actor, user) expands all three scopes and returns a
deduplicated QuerySet of Section objects the actor may access on the user's
behalf.

get_permitted_regimes(actor, user) returns the distinct Regimes reachable from
those sections — used to build the regime selection menu.
"""

from django.db.models import Q

from .models import Permission, Regime, Section


def get_permitted_sections(actor, user, case_id=None):
    """
    Return a distinct QuerySet[Section] of all sections actor may access
    on user's behalf, after expanding the three grant scopes.

    case_id (optional): when provided, permissions that are scoped to a
    specific case (permission.case is not null) are only included when
    that case's case_id matches.  When case_id is None all permissions are
    included regardless of their case field (backward-compatible default).
    """
    perms = Permission.objects.filter(actor=actor, user=user)

    if not perms.exists():
        return Section.objects.none()

    # ── Case filter: drop case-scoped permissions that don't match ────────────
    if case_id is not None:
        perms = perms.filter(
            Q(case__isnull=True) | Q(case_id=case_id)
        )
        if not perms.exists():
            return Section.objects.none()

    # ── Scope 3: all-regime grant (both regime and section are null) ──────────
    if perms.filter(regime__isnull=True, section__isnull=True).exists():
        return Section.objects.all()

    # ── Scope 1: section-level grants ─────────────────────────────────────────
    # permissions is the related_name from Permission.section FK to Section.
    # Filtering via this reverse relation only matches Permission rows where
    # permission.section points to this section (i.e. section is not null).
    perm_ids = list(perms.values_list('pk', flat=True))
    scope1 = Section.objects.filter(
        permissions__pk__in=perm_ids,
        permissions__section__isnull=False,
    )

    # ── Scope 2: regime-level grants (section=None, regime set) ───────────────
    regime_ids = list(
        perms.filter(section__isnull=True, regime__isnull=False)
        .values_list('regime_id', flat=True)
    )
    if regime_ids:
        scope2 = Section.objects.filter(
            Q(regime__in=regime_ids) | Q(schedule__regime__in=regime_ids)
        )
    else:
        scope2 = Section.objects.none()

    return (scope1 | scope2).distinct()


def get_permitted_regimes(actor, user, dept_id=None):
    """
    Return a distinct QuerySet[Regime] of all regimes reachable from the
    actor/user's permitted sections.  Used to build the regime selection menu.

    If dept_id is provided, the result is further filtered to regimes whose
    dept_id matches — used by per-department home views to scope their listing.
    """
    permitted = get_permitted_sections(actor, user)

    # Regimes via direct-section link
    direct_ids = permitted.filter(
        regime__isnull=False
    ).values_list('regime_id', flat=True)

    # Regimes via schedule
    indirect_ids = permitted.filter(
        schedule__isnull=False
    ).values_list('schedule__regime_id', flat=True)

    all_ids = set(list(direct_ids) + list(indirect_ids))
    qs = Regime.objects.exclude(dept_id='PLATFORM').filter(regime_id__in=all_ids)
    if dept_id is not None:
        qs = qs.filter(dept_id=dept_id)
    return qs
