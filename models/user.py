from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class User(UserMixin, db.Model):
    """User model with approval system and rate limiting."""
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Rate limiting fields
    daily_file_count = db.Column(db.Integer, default=0, nullable=False)
    daily_storage_used = db.Column(db.BigInteger, default=0, nullable=False)  # bytes
    session_storage_used = db.Column(db.BigInteger, default=0, nullable=False)  # bytes
    last_reset_date = db.Column(db.Date, default=date.today, nullable=False)
    
    # Relationships
    processing_jobs = db.relationship('ProcessingJob', backref='user', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    
    # Self-referencing relationship for approver
    approved_users = db.relationship('User', backref=db.backref('approver', remote_side=[id]))
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    def set_password(self, password):
        """Set password hash."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash."""
        return check_password_hash(self.password_hash, password)
    
    def reset_daily_counters_if_needed(self):
        """Reset daily counters if it's a new day."""
        today = date.today()
        if self.last_reset_date < today:
            self.daily_file_count = 0
            self.daily_storage_used = 0
            self.last_reset_date = today
            db.session.commit()
    
    def can_upload_file(self, file_size, daily_file_limit, daily_storage_limit_mb, session_storage_limit_mb):
        """Check if user can upload a file based on rate limits."""
        self.reset_daily_counters_if_needed()
        
        daily_storage_limit_bytes = daily_storage_limit_mb * 1024 * 1024
        session_storage_limit_bytes = session_storage_limit_mb * 1024 * 1024
        
        # Check daily limits
        if self.daily_file_count >= daily_file_limit:
            return False, f"Daily file limit of {daily_file_limit} files exceeded"
        
        if self.daily_storage_used + file_size > daily_storage_limit_bytes:
            return False, f"Daily storage limit of {daily_storage_limit_mb}MB exceeded"
        
        # Check session limits
        if self.session_storage_used + file_size > session_storage_limit_bytes:
            return False, f"Session storage limit of {session_storage_limit_mb}MB exceeded"
        
        return True, "Upload allowed"
    
    def update_usage_counters(self, file_size):
        """Update usage counters after successful upload."""
        self.daily_file_count += 1
        self.daily_storage_used += file_size
        self.session_storage_used += file_size
    
    def clear_session_storage(self):
        """Clear session storage counter."""
        self.session_storage_used = 0
    
    def get_usage_stats(self, daily_file_limit, daily_storage_limit_mb, session_storage_limit_mb):
        """Get current usage statistics."""
        self.reset_daily_counters_if_needed()
        
        return {
            'daily_limits': {
                'files': daily_file_limit,
                'storage_mb': daily_storage_limit_mb
            },
            'daily_usage': {
                'files': self.daily_file_count,
                'storage_mb': round(self.daily_storage_used / (1024 * 1024), 2)
            },
            'session_usage': {
                'files': self.processing_jobs.filter_by(
                    created_at=datetime.utcnow().date()
                ).count(),
                'storage_mb': round(self.session_storage_used / (1024 * 1024), 2)
            },
            'session_limit_mb': session_storage_limit_mb
        }
    
    def to_dict(self):
        """Convert user to dictionary for API responses."""
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def get_daily_usage(self):
        """Get current daily usage statistics."""
        self.reset_daily_counters_if_needed()
        return {
            'files': self.daily_file_count,
            'storage_mb': round(self.daily_storage_used / (1024 * 1024), 2)
        }
    
    def get_session_usage(self):
        """Get current session usage statistics."""
        return {
            'files': 0,  # Session file count not tracked separately
            'storage_mb': round(self.session_storage_used / (1024 * 1024), 2)
        }