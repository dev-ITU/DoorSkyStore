from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='account_dashboard'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='account_profile'),
    path('orders/', views.orders, name='account_orders'),
    path('addresses/', views.addresses, name='account_addresses'),
    path('addresses/new/', views.address_create, name='account_address_create'),
    path('addresses/<int:pk>/edit/', views.address_edit, name='account_address_edit'),
    path('addresses/<int:pk>/delete/', views.address_delete, name='account_address_delete'),
]
