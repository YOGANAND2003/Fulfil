from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
import csv
import io
import uuid
import json
import threading
import requests
import time
from decimal import Decimal, InvalidOperation
from .models import Product, ImportSession, Webhook


def upload_page(request):
    """Main upload page with file upload interface"""
    return render(request, 'product/upload.html')


def product_list(request):
    """Display paginated list of products with filtering"""
    products = Product.objects.all()
    
    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    
    # Apply filters
    if search_query:
        products = products.filter(
            Q(sku__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if status_filter == 'active':
        products = products.filter(active=True)
    elif status_filter == 'inactive':
        products = products.filter(active=False)
    
    # Order by updated_at descending
    products = products.order_by('-updated_at')
    
    # Pagination
    paginator = Paginator(products, 50)  # Show 50 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_products': Product.objects.count(),
        'filtered_count': products.count(),
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'product/product_list.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def upload_csv(request):
    """Handle CSV file upload and start processing"""
    if 'csv_file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    
    csv_file = request.FILES['csv_file']
    
    # Validate file type
    if not csv_file.name.endswith('.csv'):
        return JsonResponse({'error': 'Please upload a CSV file'}, status=400)
    
    # Validate file size (max 100MB)
    if csv_file.size > 100 * 1024 * 1024:
        return JsonResponse({'error': 'File size too large. Maximum 100MB allowed.'}, status=400)
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    try:
        # Read and validate CSV structure
        csv_file.seek(0)
        content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        # Validate required columns
        required_columns = ['sku', 'name', 'price']
        if not all(col.lower() in [field.lower() for field in csv_reader.fieldnames] for col in required_columns):
            return JsonResponse({
                'error': f'CSV must contain columns: {", ".join(required_columns)}'
            }, status=400)
        
        # Count total rows
        csv_file.seek(0)
        total_rows = sum(1 for line in csv_file) - 1  # Subtract header row
        
        # Create import session
        import_session = ImportSession.objects.create(
            session_id=session_id,
            filename=csv_file.name,
            total_rows=total_rows,
            status='pending'
        )
        
        # Start background processing
        csv_file.seek(0)
        content = csv_file.read().decode('utf-8')
        thread = threading.Thread(
            target=process_csv_file,
            args=(content, session_id)
        )
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'total_rows': total_rows,
            'message': 'File upload started successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Error processing file: {str(e)}'}, status=500)


def get_progress(request, session_id):
    """Get upload progress for a session"""
    try:
        session = ImportSession.objects.get(session_id=session_id)
        return JsonResponse({
            'session_id': session_id,
            'status': session.status,
            'total_rows': session.total_rows,
            'processed_rows': session.processed_rows,
            'success_count': session.success_count,
            'error_count': session.error_count,
            'progress_percentage': session.progress_percentage,
            'error_log': session.error_log
        })
    except ImportSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)


def process_csv_file(csv_content, session_id):
    """Process CSV file in background with batch processing"""
    try:
        session = ImportSession.objects.get(session_id=session_id)
        session.status = 'processing'
        session.save()
        
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # Normalize column names to lowercase for case-insensitive matching
        fieldnames = {field.lower(): field for field in csv_reader.fieldnames}
        
        batch_size = 1000  # Process in batches of 1000
        batch = []
        processed_count = 0
        success_count = 0
        error_count = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (after header)
            processed_count += 1  # Count every row as processed, regardless of success/failure
            
            try:
                # Extract data with case-insensitive column matching
                sku = row.get(fieldnames.get('sku', ''), '').strip()
                name = row.get(fieldnames.get('name', ''), '').strip()
                price_str = row.get(fieldnames.get('price', ''), '').strip()
                description = row.get(fieldnames.get('description', ''), '').strip()
                
                # Validate required fields
                if not sku or not name or not price_str:
                    error_count += 1
                    errors.append(f"Row {row_num}: Missing required fields (sku, name, price)")
                    # Update progress for error rows too
                    if processed_count % 100 == 0:
                        session.processed_rows = processed_count
                        session.success_count = success_count
                        session.error_count = error_count
                        session.save()
                    continue
                
                # Validate and convert price
                try:
                    price = Decimal(price_str)
                    if price < 0:
                        raise ValueError("Price cannot be negative")
                except (InvalidOperation, ValueError) as e:
                    error_count += 1
                    errors.append(f"Row {row_num}: Invalid price '{price_str}': {str(e)}")
                    # Update progress for error rows too
                    if processed_count % 100 == 0:
                        session.processed_rows = processed_count
                        session.success_count = success_count
                        session.error_count = error_count
                        session.save()
                    continue
                
                # Create product data
                product_data = {
                    'sku': sku.upper(),  # Store SKU in uppercase for consistency
                    'name': name,
                    'price': price,
                    'description': description,
                    'active': True  # Default to active
                }
                
                batch.append(product_data)
                
                # Process batch when it reaches batch_size
                if len(batch) >= batch_size:
                    batch_success = process_batch(batch)
                    success_count += batch_success
                    batch = []
                
                # Update progress every 100 rows
                if processed_count % 100 == 0:
                    session.processed_rows = processed_count
                    session.success_count = success_count
                    session.error_count = error_count
                    session.save()
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {row_num}: Unexpected error: {str(e)}")
                # Update progress for error rows too
                if processed_count % 100 == 0:
                    session.processed_rows = processed_count
                    session.success_count = success_count
                    session.error_count = error_count
                    session.save()
        
        # Process remaining batch
        if batch:
            batch_success = process_batch(batch)
            success_count += batch_success
        
        # Update final status - ensure processed_rows matches total_rows
        session.processed_rows = session.total_rows  # Set to total for 100% completion
        session.success_count = success_count
        session.error_count = error_count
        session.status = 'completed'
        
        # Store error log (limit to first 100 errors)
        if errors:
            session.error_log = '\n'.join(errors[:100])
            if len(errors) > 100:
                session.error_log += f'\n... and {len(errors) - 100} more errors'
        
        session.save()
        
        # Trigger webhooks for bulk import completion
        if session.status == 'completed':
            trigger_webhooks('bulk_import_completed', {
                'summary': {
                    'total_rows': session.total_rows,
                    'processed_rows': session.processed_rows,
                    'success_count': session.success_count,
                    'error_count': session.error_count,
                    'filename': session.filename
                }
            })
        
    except Exception as e:
        # Handle unexpected errors
        try:
            session = ImportSession.objects.get(session_id=session_id)
            session.status = 'failed'
            session.error_log = f"Processing failed: {str(e)}"
            session.save()
        except:
            pass


def process_batch(batch):
    """Process a batch of products with bulk operations"""
    success_count = 0
    
    try:
        with transaction.atomic():
            for product_data in batch:
                try:
                    # Use update_or_create for efficient upsert operation
                    product, created = Product.objects.update_or_create(
                        sku=product_data['sku'],
                        defaults={
                            'name': product_data['name'],
                            'price': product_data['price'],
                            'description': product_data['description'],
                            'active': product_data['active']
                        }
                    )
                    success_count += 1
                except Exception as e:
                    # Log individual product errors but continue processing
                    continue
                    
    except Exception as e:
        # If the entire batch fails, try individual processing
        for product_data in batch:
            try:
                product, created = Product.objects.update_or_create(
                    sku=product_data['sku'],
                    defaults={
                        'name': product_data['name'],
                        'price': product_data['price'],
                        'description': product_data['description'],
                        'active': product_data['active']
                    }
                )
                success_count += 1
            except:
                continue
    
    return success_count


@csrf_exempt
@require_http_methods(["POST"])
def create_product(request):
    """Create a new product"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        sku = data.get('sku', '').strip().upper()
        name = data.get('name', '').strip()
        price_str = data.get('price', '').strip()
        description = data.get('description', '').strip()
        active = data.get('active', True)
        
        if not sku or not name or not price_str:
            return JsonResponse({'error': 'SKU, name, and price are required'}, status=400)
        
        # Validate price
        try:
            price = Decimal(price_str)
            if price < 0:
                raise ValueError("Price cannot be negative")
        except (InvalidOperation, ValueError):
            return JsonResponse({'error': 'Invalid price format'}, status=400)
        
        # Check if SKU already exists
        if Product.objects.filter(sku=sku).exists():
            return JsonResponse({'error': 'Product with this SKU already exists'}, status=400)
        
        # Create product
        product = Product.objects.create(
            sku=sku,
            name=name,
            price=price,
            description=description,
            active=active
        )
        
        # Trigger webhooks
        trigger_webhooks('product_created', {
            'product': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'price': str(product.price),
                'description': product.description,
                'active': product.active
            }
        })
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'price': str(product.price),
                'description': product.description,
                'active': product.active,
                'created_at': product.created_at.isoformat(),
                'updated_at': product.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error creating product: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def update_product(request, product_id):
    """Update an existing product"""
    try:
        product = get_object_or_404(Product, id=product_id)
        data = json.loads(request.body)
        
        # Update fields if provided
        if 'sku' in data:
            new_sku = data['sku'].strip().upper()
            if new_sku != product.sku and Product.objects.filter(sku=new_sku).exists():
                return JsonResponse({'error': 'Product with this SKU already exists'}, status=400)
            product.sku = new_sku
        
        if 'name' in data:
            product.name = data['name'].strip()
        
        if 'price' in data:
            try:
                price = Decimal(str(data['price']))
                if price < 0:
                    raise ValueError("Price cannot be negative")
                product.price = price
            except (InvalidOperation, ValueError):
                return JsonResponse({'error': 'Invalid price format'}, status=400)
        
        if 'description' in data:
            product.description = data['description'].strip()
        
        if 'active' in data:
            product.active = bool(data['active'])
        
        product.save()
        
        # Trigger webhooks
        trigger_webhooks('product_updated', {
            'product': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'price': str(product.price),
                'description': product.description,
                'active': product.active
            }
        })
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'price': str(product.price),
                'description': product.description,
                'active': product.active,
                'created_at': product.created_at.isoformat(),
                'updated_at': product.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error updating product: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_product(request, product_id):
    """Delete a product"""
    try:
        product = get_object_or_404(Product, id=product_id)
        product_data = {
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'active': product.active
        }
        product_sku = product.sku
        product.delete()
        
        # Trigger webhooks
        trigger_webhooks('product_deleted', {
            'product': product_data
        })
        
        return JsonResponse({
            'success': True,
            'message': f'Product {product_sku} deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Error deleting product: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def bulk_delete_products(request):
    """Delete all products with confirmation"""
    try:
        data = json.loads(request.body)
        confirm = data.get('confirm', False)
        
        if not confirm:
            return JsonResponse({'error': 'Confirmation required'}, status=400)
        
        # Get count before deletion
        count = Product.objects.count()
        
        # Delete all products
        Product.objects.all().delete()
        
        # Trigger webhooks
        trigger_webhooks('bulk_delete_completed', {
            'summary': {
                'total_deleted': count,
                'message': f'Successfully deleted {count} products'
            }
        })
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {count} products'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error deleting products: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_product_counts(request):
    """Get current product counts for dynamic updates"""
    print(f"get_product_counts called with params: {request.GET}")  # Debug log
    
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    
    # Get all products
    products = Product.objects.all()
    
    # Apply search filter if provided
    if search_query:
        products = products.filter(
            Q(sku__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Apply status filter if provided
    if status_filter == 'active':
        products = products.filter(active=True)
    elif status_filter == 'inactive':
        products = products.filter(active=False)
    
    counts = {
        'total_products': Product.objects.count(),
        'filtered_count': products.count(),
        'active_count': Product.objects.filter(active=True).count(),
        'inactive_count': Product.objects.filter(active=False).count(),
    }
    
    print(f"Returning counts: {counts}")  # Debug log
    return JsonResponse(counts)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_selected_products(request):
    """Delete selected products"""
    try:
        data = json.loads(request.body)
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return JsonResponse({'error': 'No products selected'}, status=400)
        
        # Validate product IDs
        if not all(isinstance(pid, int) for pid in product_ids):
            return JsonResponse({'error': 'Invalid product IDs'}, status=400)
        
        # Get products before deletion for webhook data
        products_to_delete = Product.objects.filter(id__in=product_ids)
        deleted_products = []
        
        for product in products_to_delete:
            deleted_products.append({
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'price': str(product.price),
                'description': product.description,
                'active': product.active
            })
        
        # Delete selected products
        deleted_count = products_to_delete.count()
        products_to_delete.delete()
        
        # Trigger webhooks for each deleted product
        for product_data in deleted_products:
            trigger_webhooks('product_deleted', {
                'product': product_data
            })
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully deleted {deleted_count} selected products'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error deleting selected products: {str(e)}'}, status=500)


# Webhook Management Views
def webhook_list(request):
    """Display list of webhooks"""
    webhooks = Webhook.objects.all().order_by('-created_at')
    paginator = Paginator(webhooks, 20)  # Show 20 webhooks per page
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_webhooks': webhooks.count(),
        'event_choices': Webhook.EVENT_CHOICES,
    }
    return render(request, 'product/webhook_list.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def create_webhook(request):
    """Create a new webhook"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        name = data.get('name', '').strip()
        url = data.get('url', '').strip()
        event_type = data.get('event_type', '').strip()
        is_active = data.get('is_active', True)
        secret_key = data.get('secret_key', '').strip()
        
        if not name or not url or not event_type:
            return JsonResponse({'error': 'Name, URL, and event type are required'}, status=400)
        
        # Validate event type
        valid_events = [choice[0] for choice in Webhook.EVENT_CHOICES]
        if event_type not in valid_events:
            return JsonResponse({'error': 'Invalid event type'}, status=400)
        
        # Create webhook
        webhook = Webhook.objects.create(
            name=name,
            url=url,
            event_type=event_type,
            is_active=is_active,
            secret_key=secret_key if secret_key else None
        )
        
        return JsonResponse({
            'success': True,
            'webhook': {
                'id': webhook.id,
                'name': webhook.name,
                'url': webhook.url,
                'event_type': webhook.event_type,
                'is_active': webhook.is_active,
                'created_at': webhook.created_at.isoformat(),
                'updated_at': webhook.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error creating webhook: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def update_webhook(request, webhook_id):
    """Update an existing webhook"""
    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)
        data = json.loads(request.body)
        
        # Update fields if provided
        if 'name' in data:
            webhook.name = data['name'].strip()
        
        if 'url' in data:
            webhook.url = data['url'].strip()
        
        if 'event_type' in data:
            event_type = data['event_type'].strip()
            valid_events = [choice[0] for choice in Webhook.EVENT_CHOICES]
            if event_type not in valid_events:
                return JsonResponse({'error': 'Invalid event type'}, status=400)
            webhook.event_type = event_type
        
        if 'is_active' in data:
            webhook.is_active = bool(data['is_active'])
        
        if 'secret_key' in data:
            secret_key = data['secret_key'].strip()
            webhook.secret_key = secret_key if secret_key else None
        
        webhook.save()
        
        return JsonResponse({
            'success': True,
            'webhook': {
                'id': webhook.id,
                'name': webhook.name,
                'url': webhook.url,
                'event_type': webhook.event_type,
                'is_active': webhook.is_active,
                'created_at': webhook.created_at.isoformat(),
                'updated_at': webhook.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error updating webhook: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_webhook(request, webhook_id):
    """Delete a webhook"""
    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)
        webhook_name = webhook.name
        webhook.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Webhook "{webhook_name}" deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Error deleting webhook: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def test_webhook(request, webhook_id):
    """Test a webhook by sending a sample payload"""
    try:
        webhook = get_object_or_404(Webhook, id=webhook_id)
        
        # Create test payload based on event type
        test_payload = {
            'event': webhook.event_type,
            'timestamp': time.time(),
            'test': True,
            'data': {
                'message': f'Test webhook for {webhook.event_type}',
                'webhook_id': webhook.id,
                'webhook_name': webhook.name
            }
        }
        
        # Add event-specific test data
        if webhook.event_type in ['product_created', 'product_updated', 'product_deleted']:
            test_payload['data']['product'] = {
                'id': 1,
                'sku': 'TEST-SKU-001',
                'name': 'Test Product',
                'price': '99.99',
                'active': True
            }
        elif webhook.event_type in ['bulk_import_completed', 'bulk_delete_completed']:
            test_payload['data']['summary'] = {
                'total_processed': 100,
                'success_count': 95,
                'error_count': 5
            }
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ProductImporter-Webhook/1.0'
        }
        
        # Add secret key header if configured
        if webhook.secret_key:
            headers['X-Webhook-Secret'] = webhook.secret_key
        
        # Send test request
        start_time = time.time()
        try:
            response = requests.post(
                webhook.url,
                json=test_payload,
                headers=headers,
                timeout=10
            )
            response_time = time.time() - start_time
            
            # Update webhook test results
            webhook.last_test_at = timezone.now()
            webhook.last_test_status = 'success' if response.status_code < 400 else 'failed'
            webhook.last_test_response_time = response_time
            webhook.last_test_response_code = response.status_code
            webhook.save()
            
            return JsonResponse({
                'success': True,
                'status_code': response.status_code,
                'response_time': round(response_time, 3),
                'message': f'Webhook test completed with status {response.status_code}'
            })
            
        except requests.exceptions.RequestException as e:
            response_time = time.time() - start_time
            
            # Update webhook test results
            webhook.last_test_at = timezone.now()
            webhook.last_test_status = 'failed'
            webhook.last_test_response_time = response_time
            webhook.last_test_response_code = None
            webhook.save()
            
            return JsonResponse({
                'success': False,
                'error': f'Request failed: {str(e)}',
                'response_time': round(response_time, 3)
            })
        
    except Exception as e:
        return JsonResponse({'error': f'Error testing webhook: {str(e)}'}, status=500)


# Webhook trigger functions
def trigger_webhooks(event_type, data):
    """Trigger all active webhooks for a specific event type"""
    webhooks = Webhook.objects.filter(event_type=event_type, is_active=True)
    
    for webhook in webhooks:
        # Run webhook in background thread to avoid blocking
        thread = threading.Thread(
            target=send_webhook_notification,
            args=(webhook, event_type, data)
        )
        thread.daemon = True
        thread.start()


def send_webhook_notification(webhook, event_type, data):
    """Send webhook notification in background"""
    try:
        payload = {
            'event': event_type,
            'timestamp': time.time(),
            'data': data
        }
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ProductImporter-Webhook/1.0'
        }
        
        if webhook.secret_key:
            headers['X-Webhook-Secret'] = webhook.secret_key
        
        requests.post(
            webhook.url,
            json=payload,
            headers=headers,
            timeout=10
        )
        
    except Exception as e:
        # Log error but don't raise to avoid breaking main functionality
        print(f"Webhook notification failed for {webhook.name}: {str(e)}")
