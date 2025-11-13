# Product Importer - CSV to Database Web Application

A scalable Django web application designed to efficiently import large CSV files (up to 500,000 products) into a SQL database with real-time progress tracking, product management, and webhook notifications.

## 🚀 Features

### ✅ Story 1 - File Upload via UI
- **Large File Support**: Upload CSV files up to 100MB (approximately 500,000 products)
- **Intuitive Interface**: Clean drag-and-drop file upload component
- **Real-time Progress**: Live progress tracking with percentage, status messages, and visual indicators
- **Duplicate Handling**: Automatic overwrite based on case-insensitive SKU matching
- **Optimized Processing**: Background processing with batch operations for performance

### ✅ Story 1A - Upload Progress Visibility
- **Real-time Updates**: Dynamic progress bar with percentage completion
- **Detailed Statistics**: Shows total rows, processed count, success/error counts
- **Status Messages**: Clear visual feedback ("Parsing CSV", "Validating", "Import Complete")
- **Error Reporting**: Comprehensive error logging with retry options
- **Background Processing**: Non-blocking uploads using threading

### ✅ Story 2 - Product Management UI
- **Complete CRUD Operations**: Create, read, update, and delete products
- **Advanced Filtering**: Search by SKU, name, description, and active status
- **Paginated Views**: Efficient browsing of large product catalogs (50 per page)
- **Inline Editing**: Modal forms for quick product updates
- **Responsive Design**: Clean, modern Bootstrap-based interface

### ✅ Story 3 - Bulk Delete from UI
- **Safe Bulk Operations**: Delete all products with confirmation dialog
- **Protection Mechanisms**: "Are you sure?" confirmation with warning messages
- **Visual Feedback**: Success/failure notifications with progress indicators
- **Responsive Processing**: Background deletion to maintain UI responsiveness

### ✅ Story 4 - Webhook Configuration via UI
- **Webhook Management**: Add, edit, test, and delete webhooks through web interface
- **Event Types**: Support for product created/updated/deleted, bulk import/delete completed
- **Testing Functionality**: Built-in webhook testing with response time and status tracking
- **Security**: Optional secret key support for webhook verification
- **Performance Monitoring**: Track webhook response times and success rates

## 🛠 Technical Implementation

### Architecture
- **Backend**: Django 4.2.26 with SQLite database
- **Frontend**: Bootstrap 5.3 with vanilla JavaScript
- **Processing**: Multi-threaded background processing for large files
- **APIs**: RESTful JSON APIs for all CRUD operations

### Database Schema
```sql
-- Products table with optimized indexes
Product:
- id (Primary Key)
- sku (Unique, Case-insensitive, Indexed)
- name (Required)
- price (Decimal, Min 0.00)
- description (Optional)
- active (Boolean, Default True, Indexed)
- created_at, updated_at (Timestamps)

-- Import session tracking
ImportSession:
- session_id (UUID)
- filename, total_rows, processed_rows
- success_count, error_count
- status, error_log
- progress tracking fields

-- Webhook configuration
Webhook:
- name, url, event_type
- is_active, secret_key
- test result tracking
- created_at, updated_at
```

### Performance Optimizations
- **Batch Processing**: 1000 records per batch for optimal memory usage
- **Database Indexes**: Strategic indexing on SKU and active status
- **Background Threading**: Non-blocking file processing
- **Pagination**: Efficient large dataset browsing
- **Connection Pooling**: Optimized database connections

## 📋 Requirements

- Python 3.8+
- Django 4.2.26
- requests 2.31.0
- Modern web browser with JavaScript enabled

## 🚀 Quick Start

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd product-importer
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Database Setup**
   ```bash
   cd productimporter
   python manage.py makemigrations
   python manage.py migrate
   ```

3. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

4. **Access Application**
   - Open http://localhost:8000/product/
   - Upload CSV files, manage products, configure webhooks

## 📁 Project Structure

```
productimporter/
├── product/                    # Main Django app
│   ├── models.py              # Product, ImportSession, Webhook models
│   ├── views.py               # All business logic and API endpoints
│   ├── urls.py                # URL routing
│   ├── templates/product/     # HTML templates
│   │   ├── base.html         # Base template with Bootstrap
│   │   ├── upload.html       # File upload interface
│   │   ├── product_list.html # Product management UI
│   │   └── webhook_list.html # Webhook management UI
│   └── migrations/           # Database migrations
├── productimporter/          # Django project settings
├── manage.py                # Django management script
├── db.sqlite3              # SQLite database
└── requirements.txt        # Python dependencies
```

## 🔧 API Endpoints

### Product Management
- `POST /product/api/products/create/` - Create new product
- `PUT /product/api/products/{id}/update/` - Update existing product
- `DELETE /product/api/products/{id}/delete/` - Delete product
- `DELETE /product/api/products/bulk-delete/` - Delete all products

### File Upload & Progress
- `POST /product/upload/` - Upload CSV file
- `GET /product/progress/{session_id}/` - Get upload progress

### Webhook Management
- `POST /product/api/webhooks/create/` - Create webhook
- `PUT /product/api/webhooks/{id}/update/` - Update webhook
- `DELETE /product/api/webhooks/{id}/delete/` - Delete webhook
- `POST /product/api/webhooks/{id}/test/` - Test webhook

## 📊 CSV Format Requirements

Your CSV file must include these columns (case-insensitive):
- **SKU** (Required): Unique product identifier
- **Name** (Required): Product name
- **Price** (Required): Product price (numeric, >= 0)
- **Description** (Optional): Product description

Example CSV:
```csv
SKU,Name,Price,Description
PROD-001,Widget A,29.99,High-quality widget
PROD-002,Widget B,39.99,Premium widget with extras
```

## 🔗 Webhook Events

The application supports these webhook events:
- `product_created` - New product added
- `product_updated` - Product modified
- `product_deleted` - Product removed
- `bulk_import_completed` - CSV import finished
- `bulk_delete_completed` - Bulk delete finished

Webhook payloads include event type, timestamp, and relevant data.

## 🎨 UI Features

- **Responsive Design**: Works on desktop, tablet, and mobile
- **Real-time Updates**: Live progress tracking and notifications
- **Modern Interface**: Clean Bootstrap 5 design with Font Awesome icons
- **Accessibility**: Proper ARIA labels and keyboard navigation
- **Error Handling**: User-friendly error messages and recovery options

## 🔒 Security Features

- **CSRF Protection**: All forms protected against CSRF attacks
- **Input Validation**: Server-side validation for all inputs
- **File Type Validation**: Only CSV files accepted
- **Size Limits**: 100MB maximum file size
- **Webhook Security**: Optional secret key verification

## 📈 Scalability

- **Large File Handling**: Tested with 500,000+ records
- **Memory Efficient**: Batch processing prevents memory overflow
- **Background Processing**: Non-blocking operations
- **Database Optimization**: Proper indexing and query optimization
- **Webhook Performance**: Asynchronous webhook delivery

## 🐛 Error Handling

- **Graceful Degradation**: Application continues working even with errors
- **Detailed Logging**: Comprehensive error tracking and reporting
- **User Feedback**: Clear error messages and recovery suggestions
- **Retry Mechanisms**: Built-in retry for failed operations

## 🚀 Production Deployment

For production deployment:
1. Use PostgreSQL or MySQL instead of SQLite
2. Configure proper static file serving
3. Set up Redis for background task processing
4. Enable HTTPS and security headers
5. Configure proper logging and monitoring

## 📝 License

This project is built for Acme Inc. as a functional demonstration of scalable CSV import capabilities with modern web technologies.