from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Product(models.Model):
    sku = models.CharField(
        max_length=100, 
        unique=True, 
        db_index=True,
        help_text="Stock Keeping Unit - must be unique (case-insensitive)"
    )
    name = models.CharField(max_length=255)
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sku']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['active']),
        ]

    def save(self, *args, **kwargs):
        # Ensure SKU is stored in uppercase for case-insensitive uniqueness
        self.sku = self.sku.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} - {self.name}"


class ImportSession(models.Model):
    """Track CSV import sessions for progress monitoring"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    session_id = models.CharField(max_length=100, unique=True)
    filename = models.CharField(max_length=255)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_log = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Import {self.session_id} - {self.status}"

    @property
    def progress_percentage(self):
        if self.total_rows == 0:
            return 0
        return round((self.processed_rows / self.total_rows) * 100, 2)


class Webhook(models.Model):
    """Webhook configuration for external notifications"""
    EVENT_CHOICES = [
        ('product_created', 'Product Created'),
        ('product_updated', 'Product Updated'),
        ('product_deleted', 'Product Deleted'),
        ('bulk_import_completed', 'Bulk Import Completed'),
        ('bulk_delete_completed', 'Bulk Delete Completed'),
    ]
    
    name = models.CharField(max_length=100, help_text="Descriptive name for this webhook")
    url = models.URLField(help_text="The endpoint URL to send webhook notifications")
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, help_text="Event that triggers this webhook")
    is_active = models.BooleanField(default=True, help_text="Whether this webhook is active")
    secret_key = models.CharField(max_length=255, blank=True, null=True, help_text="Optional secret key for webhook verification")
    
    # Test results
    last_test_at = models.DateTimeField(blank=True, null=True)
    last_test_status = models.CharField(max_length=20, blank=True, null=True)
    last_test_response_time = models.FloatField(blank=True, null=True, help_text="Response time in seconds")
    last_test_response_code = models.IntegerField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['event_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.event_type})"