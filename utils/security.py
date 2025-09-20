import hashlib
import secrets
import os
from datetime import datetime, timedelta
from flask import request, current_app
from models import db
from models.user import User
from models.audit_log import AuditLog

class SecurityUtils:
    """Security utilities for the application."""
    
    @staticmethod
    def generate_secure_filename(original_filename, user_id):
        """Generate a secure filename to prevent path traversal attacks."""
        # Get file extension
        if '.' in original_filename:
            name, ext = original_filename.rsplit('.', 1)
            ext = ext.lower()
        else:
            name = original_filename
            ext = ''
        
        # Generate secure filename with timestamp and user ID
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        random_part = secrets.token_hex(8)
        
        secure_name = f"{user_id}_{timestamp}_{random_part}"
        if ext:
            secure_name += f".{ext}"
        
        return secure_name
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename to remove dangerous characters."""
        # Remove path separators and dangerous characters
        dangerous_chars = ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*', '\0']
        sanitized = filename
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Limit length
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            max_name_length = 250 - len(ext) - 1 if ext else 250
            sanitized = name[:max_name_length]
            if ext:
                sanitized += f".{ext}"
        
        return sanitized
    
    @staticmethod
    def get_file_hash(file_path):
        """Generate SHA-256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except (IOError, OSError):
            return None
    
    @staticmethod
    def validate_file_path(file_path, allowed_directories):
        """Validate that file path is within allowed directories."""
        # Convert to absolute path and resolve any symlinks
        abs_path = os.path.abspath(file_path)
        
        # Check if path is within any allowed directory
        for allowed_dir in allowed_directories:
            allowed_abs = os.path.abspath(allowed_dir)
            if abs_path.startswith(allowed_abs):
                return True
        
        return False
    
    @staticmethod
    def create_secure_directory(directory_path):
        """Create directory with secure permissions."""
        try:
            os.makedirs(directory_path, mode=0o750, exist_ok=True)
            return True
        except (OSError, PermissionError):
            return False
    
    @staticmethod
    def secure_delete_file(file_path):
        """Securely delete a file."""
        try:
            if os.path.exists(file_path):
                # Overwrite file content before deletion (basic secure deletion)
                file_size = os.path.getsize(file_path)
                with open(file_path, "r+b") as f:
                    f.write(os.urandom(file_size))
                    f.flush()
                    os.fsync(f.fileno())
                
                os.remove(file_path)
                return True
        except (OSError, PermissionError):
            pass
        return False
    
    @staticmethod
    def get_client_info():
        """Get client IP and user agent information."""
        # Handle X-Forwarded-For header for reverse proxies
        if 'X-Forwarded-For' in request.headers:
            ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
        elif 'X-Real-IP' in request.headers:
            ip = request.headers['X-Real-IP']
        else:
            ip = request.remote_addr or 'unknown'
        
        user_agent = request.headers.get('User-Agent', 'unknown')
        
        return ip, user_agent
    
    @staticmethod
    def log_security_event(user_id, event_type, details=None):
        """Log security-related events."""
        ip, user_agent = SecurityUtils.get_client_info()
        
        AuditLog.log_security_event(
            user_id=user_id,
            ip_address=ip,
            event_type=event_type,
            user_agent=user_agent,
            **(details or {})
        )

class RateLimiter:
    """Rate limiting utilities."""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize rate limiter with Flask app."""
        self.app = app
        self.enabled = app.config.get('RATE_LIMITS_ENABLED', True)
        self.daily_file_limit = app.config.get('DAILY_FILE_LIMIT', 50)
        self.daily_storage_limit_mb = app.config.get('DAILY_STORAGE_LIMIT_MB', 200)
        self.session_storage_limit_mb = app.config.get('SESSION_STORAGE_LIMIT_MB', 100)
        self.login_attempts_per_hour = app.config.get('LOGIN_ATTEMPTS_PER_HOUR', 10)
    
    def check_upload_limits(self, user, file_size):
        """Check if user can upload a file."""
        if not self.enabled:
            return True, "Rate limiting disabled"
        
        return user.can_upload_file(
            file_size=file_size,
            daily_file_limit=self.daily_file_limit,
            daily_storage_limit_mb=self.daily_storage_limit_mb,
            session_storage_limit_mb=self.session_storage_limit_mb
        )
    
    def update_upload_counters(self, user, file_size):
        """Update user upload counters."""
        if not self.enabled:
            return
        
        user.update_usage_counters(file_size)
        db.session.commit()
    
    def check_login_attempts(self, ip_address, email=None):
        """Check login attempt rate limiting."""
        if not self.enabled:
            return True, "Rate limiting disabled"
        
        # Count failed login attempts in the last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        # Query for failed login attempts from this IP
        failed_attempts = AuditLog.query.filter(
            AuditLog.action == 'login_failed',
            AuditLog.ip_address == ip_address,
            AuditLog.created_at >= one_hour_ago
        ).count()
        
        if failed_attempts >= self.login_attempts_per_hour:
            return False, f"Too many failed login attempts. Try again later."
        
        return True, "Login attempt allowed"
    
    def get_user_quota_info(self, user):
        """Get user quota information."""
        return user.get_usage_stats(
            daily_file_limit=self.daily_file_limit,
            daily_storage_limit_mb=self.daily_storage_limit_mb,
            session_storage_limit_mb=self.session_storage_limit_mb
        )
    
    def clear_user_session_storage(self, user):
        """Clear user session storage counter."""
        user.clear_session_storage()
        db.session.commit()
    
    @staticmethod
    def is_request_suspicious(request_data=None):
        """Check if request shows suspicious patterns."""
        suspicious_patterns = [
            # Common attack patterns
            '../', '.\\', '/etc/', '/proc/', '/sys/',
            '<script', 'javascript:', 'vbscript:',
            'union select', 'drop table', 'delete from',
            '<?php', '<%', '${', '#{',
        ]
        
        # Check URL path
        if request.path:
            path_lower = request.path.lower()
            for pattern in suspicious_patterns:
                if pattern in path_lower:
                    return True, f"Suspicious path pattern: {pattern}"
        
        # Check query parameters
        if request.args:
            for key, value in request.args.items():
                value_lower = str(value).lower()
                for pattern in suspicious_patterns:
                    if pattern in value_lower:
                        return True, f"Suspicious query parameter: {pattern} in {key}"
        
        # Check form data
        if request_data:
            for key, value in request_data.items():
                if isinstance(value, str):
                    value_lower = value.lower()
                    for pattern in suspicious_patterns:
                        if pattern in value_lower:
                            return True, f"Suspicious form data: {pattern} in {key}"
        
        return False, "Request appears normal"
    
    @staticmethod
    def log_suspicious_request(user_id=None, reason=""):
        """Log suspicious request."""
        ip, user_agent = SecurityUtils.get_client_info()
        
        AuditLog.log_security_event(
            user_id=user_id,
            ip_address=ip,
            event_type='suspicious_request',
            user_agent=user_agent,
            reason=reason,
            path=request.path,
            method=request.method
        )

# Create global rate limiter instance
rate_limiter = RateLimiter()