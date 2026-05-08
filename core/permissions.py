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


def get_permitted_sections(actor, user):
    """
    Return a distinct QuerySet[Section] of all sections actor may access
    on user's behalf, after expanding the three grant scopes.
    """
    perms = Permission.objects.filter(actor=actor, user=user)

    if not perms.exists():
        return Section.objects.none()

    # ── Scope 3: all-regime grant (both regime and section are null) ──────────
    if perms.filter(regime__isnull=True, section__isnull=True).exists():
        return Section.objects.all()

    # ── Scope 1: section-level grants ─────────────────────────────────────────
    # permissions is the related_name from Permission.section FK to Section.
    # Filtering via this reverse relation only matches Permission rows where
    # permission.section points to this section (i.e. section is not null).
    scope1 = Section.objects.filter(
        permissions__actor=actor,
        permissions__user=user,
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


def get_permitted_regimes(actor, user):
    """
    Return a distinct QuerySet[Regime] of all regimes reachable from the
    actor/user's permitted sections.  Used to build the regime selection menu.
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
    return Regime.objects.filter(regime_id__in=all_ids)
