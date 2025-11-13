from django.contrib import admin
from .models import Product, ImportSession

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'price', 'active', 'created_at']
    list_filter = ['active', 'created_at']
    search_fields = ['sku', 'name']
    list_editable = ['active']
    ordering = ['sku']

@admin.register(ImportSession)
class ImportSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'filename', 'status', 'progress_percentage', 'success_count', 'error_count', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['session_id', 'progress_percentage', 'created_at', 'updated_at']
    search_fields = ['session_id', 'filename']
