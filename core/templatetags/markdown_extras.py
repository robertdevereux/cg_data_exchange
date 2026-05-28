import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def render_markdown(value):
    if not value:
        return ''
    return mark_safe(markdown.markdown(
        value,
        extensions=['extra', 'nl2br'],
    ))
