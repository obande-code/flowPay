from django.db import models


class Transfer(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'

    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='transfers')
    beneficiary = models.ForeignKey('beneficiaries.Beneficiary', on_delete=models.PROTECT, related_name='transfers')
    provider = models.ForeignKey('providers.Provider', on_delete=models.PROTECT, related_name='transfers')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference
