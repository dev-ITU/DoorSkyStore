from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='backoffice_dashboard'),
    path('analytics/', views.analytics, name='backoffice_analytics'),
    path('web-analytics/', views.web_analytics, name='backoffice_web_analytics'),
    path('orders/', views.orders_list, name='backoffice_orders'),
    path('orders/<int:pk>/', views.order_detail, name='backoffice_order_detail'),
    path('catalog/', views.catalog_list, name='backoffice_catalog'),
    path('catalog/new/', views.product_create, name='backoffice_product_create'),
    path('catalog/<int:pk>/edit/', views.product_edit, name='backoffice_product_edit'),
    path('categories/', views.categories, name='backoffice_categories'),
    path('users/', views.users_list, name='backoffice_users'),
    path('users/new/', views.user_create, name='backoffice_user_create'),
    path('users/<int:pk>/', views.user_edit, name='backoffice_user_edit'),
]
