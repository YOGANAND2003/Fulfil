from django.urls import path
from . import views

app_name = 'product'

urlpatterns = [
    path('', views.upload_page, name='upload_page'),
    path('upload/', views.upload_csv, name='upload_csv'),
    path('progress/<str:session_id>/', views.get_progress, name='get_progress'),
    path('products/', views.product_list, name='product_list'),
    path('api/products/create/', views.create_product, name='create_product'),
    path('api/products/<int:product_id>/update/', views.update_product, name='update_product'),
    path('api/products/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    path('api/products/bulk-delete/', views.bulk_delete_products, name='bulk_delete_products'),
    path('api/products/delete-selected/', views.delete_selected_products, name='delete_selected_products'),
    path('api/products/counts/', views.get_product_counts, name='get_product_counts'),
    path('webhooks/', views.webhook_list, name='webhook_list'),
    path('api/webhooks/create/', views.create_webhook, name='create_webhook'),
    path('api/webhooks/<int:webhook_id>/update/', views.update_webhook, name='update_webhook'),
    path('api/webhooks/<int:webhook_id>/delete/', views.delete_webhook, name='delete_webhook'),
    path('api/webhooks/<int:webhook_id>/test/', views.test_webhook, name='test_webhook'),
]
