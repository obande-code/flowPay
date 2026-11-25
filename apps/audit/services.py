from .models import AuditLog


def audit(action, business=None, **metadata):
    """Record a security-relevant event. Never pass secrets or full card data in metadata."""
    AuditLog.objects.create(business=business, action=action, metadata=metadata)
