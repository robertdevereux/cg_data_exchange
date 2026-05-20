class PlatformRouter:
    """
    Routes Question, QuestionSet, and QuestionSetMember reads/writes
    to the 'platform' database. Everything else goes to 'default'.
    """
    platform_models = {'question', 'questionset', 'questionsetmember'}

    def db_for_read(self, model, **hints):
        if model._meta.model_name in self.platform_models:
            return 'platform'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.model_name in self.platform_models:
            return 'platform'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name in self.platform_models:
            return db == 'platform'
        return db == 'default'
