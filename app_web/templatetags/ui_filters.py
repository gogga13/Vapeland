from django import template
from django.utils.html import conditional_escape, format_html_join
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter(name="product_title_lines")
def product_title_lines(value, max_chars=16):
    text = str(value or "").strip()
    if not text:
        return ""

    words = [word for word in text.split() if word]
    if len(words) < 3:
        return conditional_escape(text)

    try:
        limit = max(10, int(max_chars))
    except (TypeError, ValueError):
        limit = 16

    lines = []
    current_line = ""

    for word in words:
        candidate = f"{current_line} {word}".strip()
        if current_line and len(candidate) > limit:
            lines.append(current_line)
            current_line = word
        else:
            current_line = candidate

    if current_line:
        lines.append(current_line)

    if len(lines) == 1:
        return conditional_escape(text)

    return mark_safe(
        format_html_join(
            "",
            '<span class="product-title-line">{}</span>',
            ((line,) for line in lines),
        )
    )
