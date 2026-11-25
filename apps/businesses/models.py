import uuid

from django.conf import settings
from django.db import models


class Business(models.Model):
    BUSINESS_TYPES = [
        ("individual", "Individual"),
        ("registered", "Registered Business"),
        ("company", "Limited Liability Company"),
        ("enterprise", "Enterprise"),
    ]

    BUSINESS_STATUSES = [
        ("pending", "Pending Verification"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="businesses"
    )

    name = models.CharField(max_length=255)

    email = models.EmailField()

    business_type = models.CharField(
        max_length=30,
        choices=BUSINESS_TYPES,
        default="individual"
    )

    registration_number = models.CharField(
        max_length=100,
        blank=True
    )

    country = models.CharField(
        max_length=2,
        default="NG"
    )

    currency = models.CharField(
        max_length=3,
        default="NGN"
    )

    webhook_url = models.URLField(
        blank=True,
        help_text="Where flowPay posts payment updates for this business."
    )

    status = models.CharField(
        max_length=20,
        choices=BUSINESS_STATUSES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
