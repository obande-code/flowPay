from django.db import models


class Beneficiary(models.Model):
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='beneficiaries')
    name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    bank_code = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.account_number})"
