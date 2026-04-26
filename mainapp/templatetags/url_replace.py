from django import template

register = template.Library()


@register.simple_tag
def url_replace(request, field, value):
    dict_ = request.GET.copy()
    dict_[field] = value
    # Removing share values from request during pagination
    if dict_.get("shareId"):
        dict_.pop("shareId")
    if dict_.get("shareMoment"):
        dict_.pop("shareMoment")
    return dict_.urlencode()
