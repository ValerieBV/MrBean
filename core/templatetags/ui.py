from django import template
from django import forms
register = template.Library()


@register.filter
def bootstrap_field(field):
    """Apply the reference UI widgets without changing form validation."""
    widget = field.field.widget
    if widget.is_hidden:
        return field
    if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
        css = 'form-check-input'
    elif isinstance(widget, forms.Select):
        css = 'form-select'
    else:
        css = 'form-control'
    classes = widget.attrs.get('class', '').split()
    if css not in classes:
        classes.append(css)
    attrs = {'class': ' '.join(classes)}
    if field.errors:
        attrs['aria-invalid'] = 'true'
    return field.as_widget(attrs=attrs)


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    query = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value is None: query.pop(key, None)
        else: query[key] = value
    return query.urlencode()


@register.simple_tag(takes_context=True)
def page_query(context, key, number):
    query = context['request'].GET.copy()
    query[key] = number
    return query.urlencode()
