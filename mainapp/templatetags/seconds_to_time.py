from django import template
import math

register = template.Library()

@register.filter()
def formatSeconds(s):
    mins = math.floor(s / 60)
    secs = math.floor(s - (mins * 60))
    return "%d:%02d" % (mins, secs)