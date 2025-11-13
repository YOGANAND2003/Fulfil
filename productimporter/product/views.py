from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
from django.conf import settings
import csv
import io
import uuid
import json
import threading
from decimal import Decimal, InvalidOperation
from .models import Product, ImportSession


def upload_page(request):
    """Main upload page with file upload interface"""
    return render(request, 'product/upload.html')


def product_list(request):
    """Display paginated list of products"""
    products = Product.objects.all().order_by('-updated_at')
    paginator = Paginator(products, 50)  # Show 50 products per page
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_products': products.count()
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
                    continue
                
                # Validate and convert price
                try:
                    price = Decimal(price_str)
                    if price < 0:
                        raise ValueError("Price cannot be negative")
                except (InvalidOperation, ValueError) as e:
                    error_count += 1
                    errors.append(f"Row {row_num}: Invalid price '{price_str}': {str(e)}")
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
                
                processed_count += 1
                
                # Update progress every 100 rows
                if processed_count % 100 == 0:
                    session.processed_rows = processed_count
                    session.success_count = success_count
                    session.error_count = error_count
                    session.save()
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {row_num}: Unexpected error: {str(e)}")
        
        # Process remaining batch
        if batch:
            batch_success = process_batch(batch)
            success_count += batch_success
        
        # Update final status
        session.processed_rows = processed_count
        session.success_count = success_count
        session.error_count = error_count
        session.status = 'completed'
        
        # Store error log (limit to first 100 errors)
        if errors:
            session.error_log = '\n'.join(errors[:100])
            if len(errors) > 100:
                session.error_log += f'\n... and {len(errors) - 100} more errors'
        
        session.save()
        
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
