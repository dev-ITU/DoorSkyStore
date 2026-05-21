from django.urls import path

from . import views

urlpatterns = [
    path('client/', views.client_metrics, name='webanalytics_client_metrics'),
]
