from django.db import models


class WebhookEvent(models.Model):
    provider = models.ForeignKey('providers.Provider', on_delete=models.CASCADE, related_name='webhook_events')
    event_type = models.CharField(max_length=100)
    # SHA-256 of the raw body; a unique digest makes a redelivered event a no-op.
    digest = models.CharField(max_length=64, unique=True, null=True, blank=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider.code}: {self.event_type}"
