from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    """
    Custom user model extending AbstractUser with no additional fields.
    Defined here from the start so AUTH_USER_MODEL = 'core.User' is set
    before any migrations are created — changing this later requires
    squashing or rebuilding migrations.
    """

    class Meta:
        db_table = 'core_user'


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECTS 1–3: STRUCTURAL HIERARCHY
# ─────────────────────────────────────────────────────────────────────────────

class Regime(models.Model):
    """FA Object 1. Configuration record for a single public service."""

    regime_id = models.CharField(max_length=100, primary_key=True)
    regime_name = models.CharField(max_length=255)
    dept_id = models.CharField(max_length=100, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'regime_name']

    def __str__(self):
        return self.regime_name


class Department(models.Model):
    """Participating department. dept_id matches Regime.dept_id."""
    dept_id   = models.CharField(max_length=20, primary_key=True)
    dept_name = models.CharField(max_length=100)

    def __str__(self):
        return self.dept_name


class Schedule(models.Model):
    """FA Object 2. Optional named grouping of Sections within a Regime."""

    schedule_id = models.CharField(max_length=100, primary_key=True)
    schedule_name = models.CharField(max_length=255)
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
        related_name='schedules',
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'schedule_name']

    def __str__(self):
        return self.schedule_name


class Section(models.Model):
    """
    FA Object 3. Unit of citizen interaction: one coherent subject,
    concluded by a check-your-answers confirmation.

    Belongs to either a Schedule or directly to a Regime — never both,
    never neither. Enforced by clean().
    """

    SECTION_TYPE_CHOICES = [
        (0, 'Standard'),           # one question per page; routing determines sequence
        (1, 'Table'),              # flat columns; no per-row routing
        (2, 'Table with routing'), # repeating rows, each row has its own routing path
    ]

    section_id = models.CharField(max_length=100, primary_key=True)
    section_name = models.CharField(max_length=255)
    section_type = models.IntegerField(choices=SECTION_TYPE_CHOICES, default=0)
    display_order = models.PositiveIntegerField(default=0)

    schedule = models.ForeignKey(
        Schedule,
        to_field='schedule_id',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sections',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='direct_sections',
    )

    # Table-section fields
    section_guidance = models.TextField(blank=True, null=True)
    column_question_ids = models.TextField(
        blank=True,
        null=True,
        help_text='Semicolon-delimited question IDs defining table column display order',
    )
    totals_question_ids = models.TextField(
        blank=True,
        null=True,
        help_text='Semicolon-delimited question IDs whose numeric values are totalled',
    )

    class Meta:
        ordering = ['display_order', 'section_name']

    def clean(self):
        if self.schedule_id is None and self.regime_id is None:
            raise ValidationError(
                'A Section must belong to either a Schedule or a Regime directly.'
            )
        if self.schedule_id is not None and self.regime_id is not None:
            raise ValidationError(
                'A Section cannot belong to both a Schedule and a Regime directly.'
            )

    def get_regime(self):
        """Return the parent Regime whether this section sits under a Schedule or directly under a Regime."""
        if self.schedule_id:
            return self.schedule.regime
        return self.regime

    def __str__(self):
        return self.section_name


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECT 4: QUESTION BANK
# ─────────────────────────────────────────────────────────────────────────────

class Question(models.Model):
    """
    FA Object 4. A single question defined once and reused across regimes.
    Reuse is the mechanism by which a previous answer in one regime
    can be offered as a suggestion in another.
    """

    QUESTION_TYPE_CHOICES = [
        ('text', 'Text'),
        ('textarea', 'Text Area'),
        ('number', 'Number'),
        ('radio', 'Radio'),
        ('checkbox', 'Checkbox'),
        ('address', 'Address'),
        ('date', 'Date'),
    ]
    ANSWER_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
    ]

    question_id = models.CharField(max_length=100, primary_key=True)
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    guidance = models.TextField(blank=True, null=True)
    hint = models.CharField(max_length=255, blank=True, null=True)
    options = models.TextField(
        blank=True,
        null=True,
        help_text='Semicolon-delimited options for radio and checkbox questions',
    )
    answer_type = models.CharField(
        max_length=20, choices=ANSWER_TYPE_CHOICES, blank=True, null=True
    )

    def __str__(self):
        return f'{self.question_id} — {self.question_text[:60]}'


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION SETS — multi-field pages
# ─────────────────────────────────────────────────────────────────────────────

class QuestionSet(models.Model):
    """
    A named group of questions presented together on one screen.
    set_id values follow the convention S1, S2, S3, etc.
    """
    set_id    = models.CharField(max_length=100, primary_key=True)
    set_title = models.CharField(max_length=255)
    set_hint  = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f'{self.set_id} — {self.set_title}'


class QuestionSetMember(models.Model):
    """
    Ordered membership of a Question in a QuestionSet.
    required=False means a blank submission is accepted for this field.
    """
    question_set  = models.ForeignKey(
        QuestionSet,
        on_delete=models.CASCADE,
        related_name='members',
    )
    question      = models.ForeignKey(
        Question,
        to_field='question_id',
        on_delete=models.CASCADE,
        related_name='set_memberships',
    )
    display_order = models.PositiveIntegerField(default=0)
    required      = models.BooleanField(default=True)

    class Meta:
        unique_together = ['question_set', 'question']
        ordering        = ['display_order']

    def __str__(self):
        return f'{self.question_set_id} / {self.question_id} (order {self.display_order})'


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECT 5: ROUTING
# ─────────────────────────────────────────────────────────────────────────────

class Routing(models.Model):
    """
    FA Object 5. Conditional routing logic held as data, not code.

    Each row expresses: given this Section, at this node, if the answer
    is this value, the next node is this. A null next_node means END
    (the citizen proceeds to the check-your-answers page).
    Null answer_value means the route is unconditional.

    current_node and next_node are string identifiers that resolve to
    either a Question.question_id (prefix Q) or a QuestionSet.set_id
    (prefix S). Referential integrity is enforced by the consistency
    checker at login time, not by a database FK.
    """

    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
        related_name='routing_rules',
    )
    current_node = models.CharField(
        max_length=100,
        help_text='Q-prefixed question ID or S-prefixed set ID for this screen',
    )
    answer_value = models.TextField(
        blank=True,
        null=True,
        help_text='Answer that triggers this route; null means unconditional',
    )
    next_node = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Next screen node ID; null means END (proceed to check your answers)',
    )
    order_in_section = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['section', 'current_node', 'answer_value'],
                name='unique_routing_rule',
            )
        ]
        ordering = ['order_in_section']

    def __str__(self):
        return (
            f'{self.section_id} | {self.current_node}'
            f' → {self.next_node or "END"}'
            f' (if {self.answer_value!r})'
        )


# ─────────────────────────────────────────────────────────────────────────────
# CASE — A CITIZEN'S INSTANCE OF A REGIME
# ─────────────────────────────────────────────────────────────────────────────

class Case(models.Model):
    """
    A citizen's specific instance of working through a Regime.
    case_id will be populated as a UUID string by the application layer.
    """

    DRAFT     = 'draft'
    SUBMITTED = 'submitted'
    LAPSED    = 'lapsed'

    STATUS_CHOICES = [
        (DRAFT,     'Draft'),
        (SUBMITTED, 'Submitted'),
        (LAPSED,    'Lapsed'),
    ]

    case_id = models.CharField(max_length=100, primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='cases',
        help_text='The citizen this case belongs to',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
        related_name='cases',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f'Case {self.case_id} ({self.user} / {self.regime_id})'


# ─────────────────────────────────────────────────────────────────────────────
# STATUS TRACKING (drives Layer 1 navigation indicators)
# ─────────────────────────────────────────────────────────────────────────────

class SectionStatus(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='section_statuses'
    )
    regime = models.ForeignKey(
        Regime, to_field='regime_id', on_delete=models.CASCADE
    )
    section = models.ForeignKey(
        Section, to_field='section_id', on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='not_started'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'regime', 'section'],
                name='unique_section_status',
            )
        ]

    def __str__(self):
        return f'{self.user} | {self.section_id} | {self.status}'


class ScheduleStatus(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='schedule_statuses'
    )
    regime = models.ForeignKey(
        Regime, to_field='regime_id', on_delete=models.CASCADE
    )
    schedule = models.ForeignKey(
        Schedule, to_field='schedule_id', on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='not_started'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'regime', 'schedule'],
                name='unique_schedule_status',
            )
        ]

    def __str__(self):
        return f'{self.user} | {self.schedule_id} | {self.status}'


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECT 7: PERMISSION AND DELEGATION
# ─────────────────────────────────────────────────────────────────────────────

class Permission(models.Model):
    """
    FA Object 7. A grant by a User to a named Actor to complete specific
    Sections on the User's behalf.

    Scope rules:
    - section and regime both null  → actor has access to all regimes for this user
    - section null, regime set      → actor has access to all sections of that regime
    - both set                      → actor has access to that specific section only

    Delegation chain: granted_by is null when the grant comes directly from
    the user; otherwise it points to the actor who delegated.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='permissions_as_subject',
        help_text='The citizen whose data is at stake',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='permissions_as_actor',
        help_text='The individual granted access',
    )
    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='permissions',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='permissions',
    )
    can_delegate = models.BooleanField(default=False)
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grants_made',
        help_text='Null means granted directly by the user; otherwise the delegating actor',
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['actor', 'user', 'regime', 'section'],
                name='unique_permission',
            )
        ]

    def __str__(self):
        scope = self.section_id or self.regime_id or 'all regimes'
        return f'{self.actor} → {self.user} [{scope}]'


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECT 6: ANSWERS — STANDARD SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

class Answer(models.Model):
    """
    FA Object 6 (standard sections). One record per question per case.

    Answers are never silently overwritten: on section confirmation the
    previous value is archived to AnswerHistory before the new value is
    committed here.

    The (user, question, updated_at) index supports cross-regime
    pre-population lookups: find the most recently confirmed answer
    for a given question across all of a user's cases.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='answers',
        help_text='The citizen whose answer this is',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='answers_provided',
        help_text='The individual who provided this answer (may differ from user)',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
        related_name='answers',
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        Question,
        to_field='question_id',
        on_delete=models.CASCADE,
        related_name='answers',
    )
    answer = models.JSONField(
        help_text='Scalar value or list (for checkbox answers)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'regime', 'case', 'question', 'actor'],
                name='unique_answer',
            )
        ]
        indexes = [
            models.Index(
                fields=['user', 'regime', 'case', 'question', 'updated_at'],
                name='idx_answer_case_lookup',
            ),
            models.Index(
                fields=['user', 'question', 'updated_at'],
                name='idx_answer_prepop_lookup',
            ),
        ]

    def __str__(self):
        return f'{self.user} | {self.question_id} | {self.regime_id}'


class AnswerHistory(models.Model):
    """
    Archived previous values of standard-section answers.
    Written on section confirmation whenever an existing Answer is displaced.
    A null answer value records that the answer was removed by a routing change
    (the citizen took a shorter path on re-entry).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='answer_history',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='history_authored',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='answer_history',
    )
    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
    )
    question = models.ForeignKey(
        Question,
        to_field='question_id',
        on_delete=models.CASCADE,
    )
    answer = models.JSONField(
        null=True,
        blank=True,
        help_text='Null means this answer was removed by a routing change',
    )
    confirmed_at = models.DateTimeField(
        help_text='The timestamp at which this value was displaced',
    )

    class Meta:
        indexes = [
            models.Index(
                fields=['user', 'regime', 'case', 'section', 'confirmed_at'],
                name='idx_anshist_section_lookup',
            ),
            models.Index(
                fields=['user', 'question', 'confirmed_at'],
                name='idx_anshist_question_lookup',
            ),
        ]
        ordering = ['-confirmed_at']

    def __str__(self):
        return f'{self.user} | {self.question_id} | {self.confirmed_at}'


# ─────────────────────────────────────────────────────────────────────────────
# FA OBJECT 6 (CONTINUED): ANSWERS — TABLE SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

class AnswerTable(models.Model):
    """
    FA Object 6 (table sections). One record per section per case.
    The answer field holds a list of row dicts — one dict per row
    the citizen has added to the table.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='table_answers',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='table_answers_provided',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='table_answers',
    )
    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
    )
    # List of row dicts. For section_type=1, each dict contains all
    # column questions. For section_type=2, each dict contains only
    # the questions actually reached on that row's routing path
    # (sparse — analogous to asked_ids in a standard section).
    # Structure: [{"question_id": value, ...}, ...]
    answer = models.JSONField(
        default=list,
        help_text='List of row dicts, one per table row entered by the citizen',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'regime', 'case', 'section'],
                name='unique_table_answer',
            )
        ]

    def __str__(self):
        return f'{self.user} | {self.section_id} | {self.regime_id}'


class AnswerTableHistory(models.Model):
    """
    Archived full-table snapshots for table-section answers.
    Written on section confirmation whenever the table state is displaced.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='table_answer_history',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='table_history_authored',
    )
    regime = models.ForeignKey(
        Regime,
        to_field='regime_id',
        on_delete=models.CASCADE,
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='table_answer_history',
    )
    section = models.ForeignKey(
        Section,
        to_field='section_id',
        on_delete=models.CASCADE,
    )
    answer = models.JSONField(
        default=list,
        help_text='Full table snapshot at the point of displacement',
    )
    confirmed_at = models.DateTimeField(
        help_text='The timestamp at which this snapshot was displaced',
    )

    class Meta:
        ordering = ['-confirmed_at']

    def __str__(self):
        return f'{self.user} | {self.section_id} | {self.confirmed_at}'
