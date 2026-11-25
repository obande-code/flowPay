from django.urls import path

from . import views

app_name = 'transfers'

urlpatterns = [
    path('banks/', views.list_banks, name='banks'),
    path('resolve/', views.resolve_account, name='resolve'),
    path('initiate/', views.initiate_transfer, name='initiate'),
    path('<str:reference>/verify/', views.verify_transfer, name='verify'),
]
