from django import template

register = template.Library()

@register.filter
def file_extension(value):
    if not value:
        return ''
    return str(value).split('.')[-1].lower()