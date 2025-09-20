from functools import wraps
from flask import jsonify, request, current_app
from models.audit_log import AuditLog

def login_required_api(f):
    """Decorator for API endpoints - DISABLED (no authentication required)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # No authentication required - just call the function
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    """Decorator that required user to be active - DISABLED (no authentication)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # No authentication required - just call the function
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator that required admin privileges - DISABLED (no authentication)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # No authentication required - just call the function
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """Decorator that checks user role - DISABLED (no authentication)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # No authentication required - just call the function
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_api_access(action_name):
    """Decorator to log API access (simplified without user authentication)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Execute the function first
            result = f(*args, **kwargs)
            
            # Log the action without user context
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
                        user_id=None,  # No user authentication
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
            if request.content_type and 'application/json' in request.content_type:
                if not request.is_json:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid JSON format'
                    }), 400
                
                data = request.get_json()
                if data is None:
                    return jsonify({
                        'success': False,
                        'message': 'No JSON data provided'
                    }), 400
                
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
            # Handle HTTP exceptions by re-raising them
            from werkzeug.exceptions import HTTPException
            if isinstance(e, HTTPException):
                raise e
                
            current_app.logger.error(f"Unexpected error in {f.__name__}: {e}")
            return jsonify({
                'success': False,
                'message': 'Internal server error'
            }), 500
    return decorated_function