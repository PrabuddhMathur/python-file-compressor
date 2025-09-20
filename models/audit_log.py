from datetime import datetime, timedelta
from . import db

class AuditLog(db.Model):
    """Audit log model for tracking user actions and system events."""
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Action details
    action = db.Column(db.String(50), nullable=False)
    # Actions: login, logout, upload, process, download, admin_approve, etc.
    resource_type = db.Column(db.String(50), nullable=True)  # file, user, job
    resource_id = db.Column(db.String(100), nullable=True)
    
    # Request details
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6 support
    user_agent = db.Column(db.String(500), nullable=True)
    
    # Additional context
    details = db.Column(db.JSON, nullable=True)  # Flexible JSON for extra data
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<AuditLog {self.id}: {self.action} by user {self.user_id}>'
    
    @staticmethod
    def log_action(user_id, action, ip_address, resource_type=None, 
                   resource_id=None, user_agent=None, **details):
        """Log an action with optional additional details."""
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details if details else None
        )
        db.session.add(log)
        try:
            db.session.commit()
            return log
        except Exception as e:
            db.session.rollback()
            # In production, you might want to log this error
            print(f"Failed to create audit log: {e}")
            return None
    
    @staticmethod
    def log_login(user_id, ip_address, user_agent=None, success=True):
        """Log a login attempt."""
        action = 'login_success' if success else 'login_failed'
        return AuditLog.log_action(
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_logout(user_id, ip_address, user_agent=None):
        """Log a logout action."""
        return AuditLog.log_action(
            user_id=user_id,
            action='logout',
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_registration(user_id, ip_address, user_agent=None, email=None):
        """Log a user registration."""
        return AuditLog.log_action(
            user_id=user_id,
            action='registration',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='user',
            resource_id=str(user_id),
            email=email
        )
    
    @staticmethod
    def log_user_approval(admin_user_id, approved_user_id, ip_address, user_agent=None):
        """Log user approval by admin."""
        return AuditLog.log_action(
            user_id=admin_user_id,
            action='user_approval',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='user',
            resource_id=str(approved_user_id)
        )
    
    @staticmethod
    def log_file_upload(user_id, ip_address, filename, file_size, user_agent=None):
        """Log a file upload."""
        return AuditLog.log_action(
            user_id=user_id,
            action='file_upload',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='file',
            filename=filename,
            file_size=file_size
        )
    
    @staticmethod
    def log_processing_start(user_id, job_id, ip_address, user_agent=None, quality_preset=None):
        """Log start of PDF processing."""
        return AuditLog.log_action(
            user_id=user_id,
            action='processing_start',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='job',
            resource_id=str(job_id),
            quality_preset=quality_preset
        )
    
    @staticmethod
    def log_processing_complete(user_id, job_id, ip_address, user_agent=None, 
                               compression_ratio=None, processing_time=None):
        """Log completion of PDF processing."""
        return AuditLog.log_action(
            user_id=user_id,
            action='processing_complete',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='job',
            resource_id=str(job_id),
            compression_ratio=compression_ratio,
            processing_time=processing_time
        )
    
    @staticmethod
    def log_processing_failed(user_id, job_id, ip_address, error_message=None, user_agent=None):
        """Log failed PDF processing."""
        return AuditLog.log_action(
            user_id=user_id,
            action='processing_failed',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='job',
            resource_id=str(job_id),
            error_message=error_message
        )
    
    @staticmethod
    def log_file_download(user_id, job_id, ip_address, user_agent=None):
        """Log a file download."""
        return AuditLog.log_action(
            user_id=user_id,
            action='file_download',
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type='job',
            resource_id=str(job_id)
        )
    
    @staticmethod
    def log_session_clear(user_id, ip_address, user_agent=None, files_cleared=None):
        """Log session file clearing."""
        return AuditLog.log_action(
            user_id=user_id,
            action='session_clear',
            ip_address=ip_address,
            user_agent=user_agent,
            files_cleared=files_cleared
        )
    
    @staticmethod
    def log_rate_limit_exceeded(user_id, ip_address, limit_type, user_agent=None):
        """Log rate limit exceeded."""
        return AuditLog.log_action(
            user_id=user_id,
            action='rate_limit_exceeded',
            ip_address=ip_address,
            user_agent=user_agent,
            limit_type=limit_type
        )
    
    @staticmethod
    def log_security_event(user_id, ip_address, event_type, user_agent=None, **details):
        """Log security-related events."""
        return AuditLog.log_action(
            user_id=user_id,
            action='security_event',
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=event_type,
            **details
        )
    
    def to_dict(self):
        """Convert audit log to dictionary for API responses."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'details': self.details,
            'created_at': self.created_at.isoformat()
        }
    
    @staticmethod
    def get_user_logs(user_id, limit=100, offset=0):
        """Get audit logs for a specific user."""
        return AuditLog.query.filter_by(user_id=user_id).order_by(
            AuditLog.created_at.desc()
        ).offset(offset).limit(limit).all()
    
    @staticmethod
    def get_recent_logs(limit=100, offset=0):
        """Get recent audit logs (admin view)."""
        return AuditLog.query.order_by(
            AuditLog.created_at.desc()
        ).offset(offset).limit(limit).all()
    
    @staticmethod
    def get_logs_by_action(action, limit=100, offset=0):
        """Get audit logs by action type."""
        return AuditLog.query.filter_by(action=action).order_by(
            AuditLog.created_at.desc()
        ).offset(offset).limit(limit).all()
    
    @staticmethod
    def cleanup_old_logs(days_to_keep=90):
        """Clean up old audit logs (optional maintenance)."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        old_logs = AuditLog.query.filter(AuditLog.created_at < cutoff_date).all()
        
        for log in old_logs:
            db.session.delete(log)
        
        db.session.commit()
        return len(old_logs)