from django import template

from apps.businesses.models import Business

register = template.Library()


@register.simple_tag
def pending_businesses():
    """Businesses awaiting verification, oldest first."""
    return (
        Business.objects.filter(status="pending")
        .select_related("owner")
        .order_by("created_at")
    )
