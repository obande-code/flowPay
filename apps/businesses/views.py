from urllib.parse import urlparse

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.api_keys.models import ApiKey
from apps.api_keys.services import create_api_key
from apps.audit.services import audit

from .models import Business


class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'email', 'business_type', 'registration_number', 'webhook_url']

    def clean_webhook_url(self):
        url = self.cleaned_data.get('webhook_url', '')
        if url and urlparse(url).scheme != 'https':
            raise forms.ValidationError('Webhook URL must use https.')
        return url


@login_required
def register_business(request):
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            business = form.save(commit=False)
            business.owner = request.user
            business.save()
            audit('business.registered', business=business, name=business.name)
            messages.success(request, 'Business registered. It is pending verification.')
            return redirect('businesses:settings', pk=business.pk)
    else:
        form = BusinessForm()

    return render(request, 'businesses/register.html', {'form': form})
    business = get_object_or_404(Business, pk=pk, owner=request.user)
    new_key = request.session.pop('new_api_key', None)

    if request.method == 'POST':
        form = BusinessForm(request.POST, instance=business)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business settings saved.')
            return redirect('businesses:settings', pk=business.pk)
    else:
        form = BusinessForm(instance=business)

    return render(request, 'businesses/settings.html', {
        'business': business,
        'form': form,
        'api_keys': business.api_keys.order_by('-created_at'),
        'new_key': new_key,
    })


@login_required
def business_settings(request, pk):
    business = get_object_or_404(Business, pk=pk, owner=request.user)
    new_key = request.session.pop('new_api_key', None)

    if request.method == 'POST':
        form = BusinessForm(request.POST, instance=business)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business settings saved.')
            return redirect('businesses:settings', pk=business.pk)
    else:
        form = BusinessForm(instance=business)

    return render(request, 'businesses/settings.html', {
        'business': business,
        'form': form,
        'api_keys': business.api_keys.order_by('-created_at'),
        'new_key': new_key,
    })


@login_required
@require_POST
def create_key(request, pk):
    business = get_object_or_404(Business, pk=pk, owner=request.user)
    name = request.POST.get('name', '').strip()[:100] or 'API key'
    request.session['new_api_key'] = create_api_key(business, name)
    return redirect('businesses:settings', pk=business.pk)


@login_required
@require_POST
def revoke_key(request, pk, key_id):
    business = get_object_or_404(Business, pk=pk, owner=request.user)
    key = get_object_or_404(ApiKey, pk=key_id, business=business)
    key.is_active = False
    key.save(update_fields=['is_active'])
    messages.success(request, f'Revoked key {key.key_prefix}…')
    return redirect('businesses:settings', pk=business.pk)
