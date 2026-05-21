from django.urls import path

from . import views

urlpatterns = [
    path('<int:pk>/<uuid:public_key>/payment/', views.payment_simulation, name='payment_simulation'),
    path('<int:pk>/payment/', views.payment_simulation, name='payment_staff_simulation'),
    path('<int:pk>/<uuid:public_key>/', views.order_detail, name='order_detail'),
    path('<int:pk>/', views.order_detail, name='order_staff_detail'),
]
