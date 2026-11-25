from django.urls import path

from . import views

app_name = 'webhooks'

urlpatterns = [
    path('paystack/', views.paystack_webhook, name='paystack'),
    path('flutterwave/', views.flutterwave_webhook, name='flutterwave'),
]
