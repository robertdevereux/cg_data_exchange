from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Answer,
    AnswerHistory,
    AnswerTable,
    AnswerTableHistory,
    Case,
    Department,
    Permission,
    Question,
    Regime,
    Routing,
    Schedule,
    ScheduleStatus,
    Section,
    SectionQuestionGuidance,
    SectionStatus,
    User,
)


# ─────────────────────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('dept_id', 'dept_name')
    ordering = ('dept_id',)


# ─────────────────────────────────────────────────────────────────────────────
# REGIME
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Regime)
class RegimeAdmin(admin.ModelAdmin):
    list_display = ('regime_id', 'regime_name', 'dept_id', 'display_order')
    list_editable = ('display_order',)
    ordering = ('display_order', 'regime_id')


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('schedule_id', 'schedule_name', 'regime', 'display_order')
    list_editable = ('display_order',)
    list_filter = ('regime',)
    ordering = ('regime', 'display_order')


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING INLINE (used inside SectionAdmin)
# ─────────────────────────────────────────────────────────────────────────────

class RoutingInline(admin.TabularInline):
    model = Routing
    extra = 1
    fields = ('order_in_section', 'current_node', 'answer_value', 'next_node')
    ordering = ('order_in_section',)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = (
        'section_id', 'section_name', 'section_type', 'get_regime',
        'schedule', 'display_order',
    )
    list_editable = ('display_order',)
    list_filter = ('section_type', 'schedule__regime')
    ordering = ('section_id',)
    inlines = (RoutingInline,)

    # Surface get_regime in the list as a readable column header
    @admin.display(description='Regime')
    def get_regime(self, obj):
        return obj.get_regime()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION QUESTION GUIDANCE OVERRIDES
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(SectionQuestionGuidance)
class SectionQuestionGuidanceAdmin(admin.ModelAdmin):
    list_display = ('section', 'question', 'guidance_preview', 'hint_override')
    list_filter = ('section',)
    search_fields = ('section__section_id', 'question__question_id')
    ordering = ('section', 'question')

    @admin.display(description='Guidance (preview)')
    def guidance_preview(self, obj):
        if obj.guidance_override:
            return obj.guidance_override[:80] + ('…' if len(obj.guidance_override) > 80 else '')
        return '—'


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_id', 'question_text', 'question_type', 'answer_type')
    list_filter = ('question_type',)
    search_fields = ('question_id', 'question_text')
    ordering = ('question_id',)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING (standalone list — the inline on Section is the primary editor)
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Routing)
class RoutingAdmin(admin.ModelAdmin):
    list_display = (
        'section', 'order_in_section', 'current_node',
        'answer_value', 'next_node',
    )
    list_filter = ('section',)
    ordering = ('section', 'order_in_section')


# ─────────────────────────────────────────────────────────────────────────────
# CASE
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('case_id', 'user', 'regime', 'status', 'started_at')
    list_filter = ('status', 'regime')
    readonly_fields = ('case_id', 'started_at', 'submitted_at')


# ─────────────────────────────────────────────────────────────────────────────
# SECTION STATUS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(SectionStatus)
class SectionStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'regime', 'section', 'status')
    list_filter = ('status', 'regime')
    ordering = ('user', 'regime', 'section')


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULE STATUS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ScheduleStatus)
class ScheduleStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'regime', 'schedule', 'status')
    list_filter = ('status', 'regime')


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSION
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = (
        'actor', 'user', 'regime', 'section',
        'can_delegate', 'granted_by', 'granted_at',
    )
    list_filter = ('regime', 'can_delegate')
    ordering = ('user', 'actor')
    readonly_fields = ('granted_at',)


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'actor', 'regime', 'case', 'section',
        'question', 'answer', 'updated_at',
    )
    list_filter = ('regime', 'section')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('user', 'regime', 'updated_at')


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(AnswerHistory)
class AnswerHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'actor', 'regime', 'section',
        'question', 'answer', 'confirmed_at',
    )
    list_filter = ('regime', 'section')
    readonly_fields = ('confirmed_at',)
    ordering = ('-confirmed_at',)


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER TABLE
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(AnswerTable)
class AnswerTableAdmin(admin.ModelAdmin):
    list_display = ('user', 'actor', 'regime', 'case', 'section', 'updated_at')
    list_filter = ('regime', 'section')
    readonly_fields = ('created_at', 'updated_at')


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER TABLE HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(AnswerTableHistory)
class AnswerTableHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'actor', 'regime', 'section', 'confirmed_at')
    list_filter = ('regime', 'section')
    readonly_fields = ('confirmed_at',)
    ordering = ('-confirmed_at',)
