from django.urls import path
from . import views

app_name = 'product'

urlpatterns = [
    path('', views.upload_page, name='upload_page'),
    path('upload/', views.upload_csv, name='upload_csv'),
    path('progress/<str:session_id>/', views.get_progress, name='get_progress'),
    path('products/', views.product_list, name='product_list'),
]
