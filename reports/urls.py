from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='reports_dashboard'),
    path('sales.xlsx', views.sales_report_xlsx, name='sales_report_xlsx'),
    path('stock.xlsx', views.stock_report_xlsx, name='stock_report_xlsx'),
    path('orders/<int:pk>/<uuid:public_key>/documents.zip', views.order_documents_zip, name='order_public_documents_zip'),
    path(
        'orders/<int:pk>/<uuid:public_key>/<str:document_type>.pdf',
        views.order_document_pdf,
        name='order_public_document_pdf',
    ),
    path('orders/<int:pk>/documents.zip', views.order_documents_zip, name='order_documents_zip'),
    path('orders/<int:pk>/<str:document_type>.pdf', views.order_document_pdf, name='order_document_pdf'),
]
