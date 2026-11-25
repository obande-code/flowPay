from django.contrib import admin
from django.core.mail import send_mail

from apps.audit.services import audit

from .models import Business

# The dashboard lists businesses still waiting for verification above the app list.
admin.site.index_template = "admin/index_pending.html"


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "email", "status", "created_at")
    list_filter = ("status", "business_type")
    search_fields = ("name", "email")
    actions = ("approve_businesses", "suspend_businesses")

    def _set_status(self, request, queryset, status, action):
        businesses = [b for b in queryset if b.status != status]
        Business.objects.filter(pk__in=[b.pk for b in businesses]).update(status=status)
        for business in businesses:
            business.status = status
            audit(action, business=business, by=request.user.pk)
        self.message_user(
            request,
            f"{len(businesses)} business(es) marked {status}.",
        )
        return businesses

    def _notify_approved(self, request, business):
        recipient = business.email or business.owner.email
        if not recipient:
            return
        send_mail(
            subject=f"{business.name} is approved on flowPay",
            message=(
                f"Hello {business.owner.get_username()},\n\n"
                f"Your business {business.name} has been approved and is now active "
                f"on flowPay, so you can start accepting payments.\n\n"
                f"Dashboard: {request.build_absolute_uri('/')}\n"
            ),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=True,
        )

    @admin.action(description="Approve selected businesses")
    def approve_businesses(self, request, queryset):
        for business in self._set_status(request, queryset, "active", "business.approved"):
            self._notify_approved(request, business)

    @admin.action(description="Suspend selected businesses")
    def suspend_businesses(self, request, queryset):
        self._set_status(request, queryset, "suspended", "business.suspended")
