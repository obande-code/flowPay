from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'

    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='payments')
    provider = models.ForeignKey('providers.Provider', on_delete=models.PROTECT, related_name='payments')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference


class PaymentEvent(models.Model):
    """One entry in a payment's history: what happened, and where it came from."""

    class Source(models.TextChoices):
        INITIATE = 'initiate', 'Checkout started'
        WEBHOOK = 'webhook', 'Paystack webhook'
        CALLBACK = 'callback', 'Customer return'
        RECONCILE = 'reconcile', 'Reconciliation'

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='events')
    source = models.CharField(max_length=20, choices=Source.choices)
    status = models.CharField(max_length=20, choices=Payment.Status.choices)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.payment.reference}: {self.message}'
