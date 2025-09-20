from functools import wraps
from flask import jsonify, request, current_app
from flask_login import current_user
from models.audit_log import AuditLog

def login_required_api(f):
    """Decorator for API endpoints that require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    """Decorator that requires user to be active (approved)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401
        
        if not current_user.is_active:
            return jsonify({
                'success': False,
                'message': 'Account pending approval. Please contact administrator.'
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator that requires admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401
        
        if not current_user.is_active:
            return jsonify({
                'success': False,
                'message': 'Account pending approval'
            }), 403
        
        if not current_user.is_admin:
            # Log unauthorized admin access attempt
            AuditLog.log_security_event(
                user_id=current_user.id,
                ip_address=request.remote_addr,
                event_type='unauthorized_admin_access',
                user_agent=request.headers.get('User-Agent'),
                endpoint=request.endpoint
            )
            return jsonify({
                'success': False,
                'message': 'Admin privileges required'
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function

def rate_limit_check(limit_type='general'):
    """Decorator to check rate limits."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_app.config.get('RATE_LIMITS_ENABLED', True):
                return f(*args, **kwargs)
            
            if not current_user.is_authenticated:
                return f(*args, **kwargs)  # Let other decorators handle auth
            
            # Check rate limits based on type
            if limit_type == 'upload':
                # This will be handled in the upload endpoint itself
                # as it needs file size information
                pass
            elif limit_type == 'login':
                # Login rate limiting would be implemented here
                # For now, we'll skip this as it requires more complex tracking
                pass
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_api_access(action_name):
    """Decorator to log API access."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Execute the function first
            result = f(*args, **kwargs)
            
            # Log the action if user is authenticated
            if current_user.is_authenticated:
                try:
                    # Determine if the action was successful based on response
                    success = True
                    if hasattr(result, 'status_code'):
                        success = result.status_code < 400
                    elif isinstance(result, tuple) and len(result) > 1:
                        success = result[1] < 400
                    
                    # Only log successful actions to avoid spam
                    if success:
                        AuditLog.log_action(
                            user_id=current_user.id,
                            action=action_name,
                            ip_address=request.remote_addr,
                            user_agent=request.headers.get('User-Agent'),
                            endpoint=request.endpoint
                        )
                except Exception as e:
                    # Don't let logging errors break the request
                    current_app.logger.warning(f"Failed to log API access: {e}")
            
            return result
        return decorated_function
    return decorator

def validate_json_request(required_fields=None):
    """Decorator to validate JSON request data."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON'
                }), 400
            
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON data'
                }), 400
            
            # Check required fields
            if required_fields:
                missing_fields = []
                for field in required_fields:
                    if field not in data or not data[field]:
                        missing_fields.append(field)
                
                if missing_fields:
                    return jsonify({
                        'success': False,
                        'message': f'Missing required fields: {", ".join(missing_fields)}'
                    }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def handle_exceptions(f):
    """Decorator to handle exceptions in API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            current_app.logger.warning(f"Validation error in {f.__name__}: {e}")
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        except PermissionError as e:
            current_app.logger.warning(f"Permission error in {f.__name__}: {e}")
            return jsonify({
                'success': False,
                'message': 'Permission denied'
            }), 403
        except FileNotFoundError as e:
            current_app.logger.warning(f"File not found in {f.__name__}: {e}")
            return jsonify({
                'success': False,
                'message': 'Resource not found'
            }), 404
        except Exception as e:
            current_app.logger.error(f"Unexpected error in {f.__name__}: {e}")
            return jsonify({
                'success': False,
                'message': 'Internal server error'
            }), 500
    return decorated_function