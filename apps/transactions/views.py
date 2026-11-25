from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from apps.payments.models import Payment

PAGE_SIZE = 20


@login_required
def transaction_list(request):
    payments = (
        Payment.objects.filter(business__owner=request.user)
        .select_related('business')
        .order_by('-created_at', '-id')
    )

    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    business_id = request.GET.get('business', '')

    if query:
        payments = payments.filter(
            Q(reference__icontains=query) | Q(business__name__icontains=query)
        )
    if status in Payment.Status.values:
        payments = payments.filter(status=status)
    if business_id:
        payments = payments.filter(business__pk=business_id)

    page = Paginator(payments, PAGE_SIZE).get_page(request.GET.get('page'))

    # Keep the filters when moving between pages.
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'transactions/list.html', {
        'page': page,
        'query': query,
        'status': status,
        'business_id': business_id,
        'statuses': Payment.Status.choices,
        'businesses': request.user.businesses.all(),
        'filter_qs': params.urlencode(),
    })
