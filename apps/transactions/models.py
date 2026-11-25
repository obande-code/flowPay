from django.db import models


class Transaction(models.Model):
    class Kind(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'

    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='transactions')
    payment = models.ForeignKey('payments.Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    transfer = models.ForeignKey('transfers.Transfer', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kind} {self.amount}"
