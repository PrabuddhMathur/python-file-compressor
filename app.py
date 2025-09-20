import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import configuration
from config import config

# Import models and database
from models import db
from models.user import User
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog

# Import blueprints
from auth import auth as auth_blueprint
from api import api as api_blueprint
from main import main as main_blueprint

# Import services
from services.pdf_processor import pdf_processor
from services.file_manager import file_manager
from utils.security import rate_limiter

def create_app(config_name=None):
    """Create Flask application."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    init_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Initialize services
    init_services(app)
    
    # Set up logging
    setup_logging(app)
    
    # Set up error handlers
    setup_error_handlers(app)
    
    # Create database tables
    with app.app_context():
        create_database_tables()
        create_default_admin()
    
    # Add health check endpoints
    setup_health_checks(app)
    
    return app

def init_extensions(app):
    """Initialize Flask extensions."""
    # Initialize database
    db.init_app(app)
    
    # Initialize CSRF protection (disabled for now)
    # csrf = CSRFProtect()
    # csrf.init_app(app)
    
    # Add CSRF token to template context (disabled for now)
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=lambda: "disabled")
    
    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401
        return jsonify({
            'success': False,
            'message': 'Please log in to access this page'
        }), 401

def register_blueprints(app):
    """Register application blueprints."""
    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(api_blueprint)

def init_services(app):
    """Initialize application services."""
    pdf_processor.init_app(app)
    file_manager.init_app(app)
    rate_limiter.init_app(app)

def setup_logging(app):
    """Set up application logging."""
    if not app.debug and not app.testing:
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        # Set up file handler
        file_handler = RotatingFileHandler(
            'logs/app.log',
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('PDF Compressor application startup')

def setup_error_handlers(app):
    """Set up error handlers."""
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'success': False,
            'message': 'Bad request',
            'error_code': 400
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'success': False,
            'message': 'Unauthorized access',
            'error_code': 401
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'success': False,
            'message': 'Access forbidden',
            'error_code': 403
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'message': 'Resource not found',
            'error_code': 404
        }), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            'success': False,
            'message': 'File too large. Maximum size is 25MB.',
            'error_code': 413
        }), 413
    
    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            'success': False,
            'message': 'Rate limit exceeded. Please try again later.',
            'error_code': 429
        }), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f'Server Error: {error}')
        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error_code': 500
        }), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.error(f'Unhandled Exception: {error}')
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An unexpected error occurred',
            'error_code': 500
        }), 500

def create_database_tables():
    """Create database tables if they don't exist."""
    try:
        db.create_all()
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")

def create_default_admin():
    """Create default admin user if no admin exists."""
    try:
        # Check if any admin user exists
        admin_exists = User.query.filter_by(is_admin=True).first()
        
        if not admin_exists:
            # Create default admin user
            admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
            
            admin_user = User(
                email=admin_email,
                full_name='System Administrator',
                is_active=True,
                is_admin=True
            )
            admin_user.set_password(admin_password)
            admin_user.approved_at = datetime.utcnow()
            
            db.session.add(admin_user)
            db.session.commit()
            
            print(f"Default admin user created: {admin_email}")
            print(f"Default admin password: {admin_password}")
            print("Please change the admin password after first login!")
        
    except Exception as e:
        print(f"Error creating default admin user: {e}")
        db.session.rollback()

def setup_health_checks(app):
    """Set up health check endpoints."""
    
    @app.route('/health/live')
    def health_live():
        """Liveness probe - basic application health."""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'pdf-compressor'
        }), 200
    
    @app.route('/health/ready')
    def health_ready():
        """Readiness probe - check dependencies."""
        checks = {
            'database': False,
            'storage': False,
            'ghostscript': False
        }
        
        try:
            # Check database connection
            db.session.execute('SELECT 1')
            checks['database'] = True
        except Exception as e:
            app.logger.error(f"Database health check failed: {e}")
        
        try:
            # Check storage directory
            storage_path = app.config.get('UPLOAD_FOLDER', 'storage')
            checks['storage'] = os.path.exists(storage_path) and os.access(storage_path, os.W_OK)
        except Exception as e:
            app.logger.error(f"Storage health check failed: {e}")
        
        try:
            # Check Ghostscript availability
            import subprocess
            gs_path = app.config.get('GHOSTSCRIPT_PATH', '/usr/bin/gs')
            result = subprocess.run([gs_path, '--version'], 
                                  capture_output=True, timeout=5)
            checks['ghostscript'] = result.returncode == 0
        except Exception as e:
            app.logger.error(f"Ghostscript health check failed: {e}")
        
        all_healthy = all(checks.values())
        status_code = 200 if all_healthy else 503
        
        return jsonify({
            'status': 'healthy' if all_healthy else 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': checks
        }), status_code
    
    @app.route('/metrics')
    def metrics():
        """Basic metrics endpoint."""
        try:
            total_users = User.query.count()
            active_users = User.query.filter_by(is_active=True).count()
            total_jobs = ProcessingJob.query.count()
            completed_jobs = ProcessingJob.query.filter_by(status='completed').count()
            
            return jsonify({
                'metrics': {
                    'users_total': total_users,
                    'users_active': active_users,
                    'jobs_total': total_jobs,
                    'jobs_completed': completed_jobs,
                    'uptime': datetime.utcnow().isoformat()
                }
            }), 200
        
        except Exception as e:
            app.logger.error(f"Metrics endpoint failed: {e}")
            return jsonify({
                'error': 'Failed to retrieve metrics'
            }), 500

# Create the application instance
app = create_app()

# CLI commands for database management
@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    print('Database tables created.')

@app.cli.command()
def create_admin():
    """Create an admin user."""
    email = input('Admin email: ')
    password = input('Admin password: ')
    name = input('Full name: ')
    
    admin_user = User(
        email=email,
        full_name=name,
        is_active=True,
        is_admin=True
    )
    admin_user.set_password(password)
    admin_user.approved_at = datetime.utcnow()
    
    db.session.add(admin_user)
    db.session.commit()
    
    print(f'Admin user {email} created successfully.')

@app.cli.command()
def cleanup_files():
    """Clean up expired files."""
    result = file_manager.cleanup_expired_files()
    if result:
        print(f"Cleanup completed: {result['files_deleted']} files deleted, "
              f"{result['jobs_cleaned']} jobs expired")
    else:
        print("Cleanup failed")

@app.cli.command()
def list_users():
    """List all users."""
    users = User.query.all()
    print(f"{'ID':<5} {'Email':<30} {'Name':<25} {'Active':<8} {'Admin':<8}")
    print("-" * 80)
    for user in users:
        print(f"{user.id:<5} {user.email:<30} {user.full_name:<25} "
              f"{'Yes' if user.is_active else 'No':<8} "
              f"{'Yes' if user.is_admin else 'No':<8}")

# Global request handlers
@app.before_request
def before_request():
    """Execute before each request."""
    # Log API requests (excluding health checks)
    if (request.path.startswith('/api/') and 
        not request.path.startswith('/health/') and 
        not request.path.startswith('/metrics')):
        
        app.logger.info(f"{request.method} {request.path} from {request.remote_addr}")

@app.after_request
def after_request(response):
    """Execute after each request."""
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

if __name__ == '__main__':
    # Development server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)