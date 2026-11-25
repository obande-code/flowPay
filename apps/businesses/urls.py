from django.urls import path

from . import views

app_name = 'businesses'

urlpatterns = [
    path('register/', views.register_business, name='register'),
    path('<uuid:pk>/', views.business_settings, name='settings'),
    path('<uuid:pk>/keys/', views.create_key, name='create_key'),
    path('<uuid:pk>/keys/<int:key_id>/revoke/', views.revoke_key, name='revoke_key'),
]
