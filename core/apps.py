from django.apps import AppConfig


def _auto_grant_regimes(sender, instance, created, **kwargs):
    """On new User creation, grant access to all existing non-PLATFORM regimes."""
    if not created:
        return
    from .models import Permission, Regime
    regimes = Regime.objects.exclude(dept_id='PLATFORM')
    for regime in regimes:
        Permission.objects.get_or_create(
            actor=instance, user=instance, regime=regime, section=None,
            defaults={'can_delegate': False, 'granted_by': None},
        )


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_save
        from .models import User
        post_save.connect(_auto_grant_regimes, sender=User)
