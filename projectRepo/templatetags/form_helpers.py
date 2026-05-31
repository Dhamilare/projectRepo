from django import template

register = template.Library()

@register.filter(name='replace_underscore')
def replace_underscore(value):
    """Swaps underscores out for clean spacing profiles."""
    if isinstance(value, str):
        return value.replace('_', ' ')
    return value