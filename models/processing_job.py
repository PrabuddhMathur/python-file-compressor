from datetime import datetime, timedelta
from . import db

class ProcessingJob(db.Model):
    """Processing job model for PDF compression tasks."""
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    processed_filename = db.Column(db.String(255), nullable=True)
    original_size = db.Column(db.BigInteger, nullable=False)  # bytes
    processed_size = db.Column(db.BigInteger, nullable=True)  # bytes
    compression_ratio = db.Column(db.Float, nullable=True)
    
    # Processing details
    quality_preset = db.Column(db.String(20), nullable=False)  # high, medium, low
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Status: pending, processing, completed, failed, expired
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)  # 24 hours from creation
    
    # Error handling
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    
    # File paths (relative to storage directory)
    upload_path = db.Column(db.String(500), nullable=False)
    processed_path = db.Column(db.String(500), nullable=True)
    
    def __init__(self, **kwargs):
        super(ProcessingJob, self).__init__(**kwargs)
        # Set expiration to 24 hours from creation if not provided
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=24)
    
    def __repr__(self):
        return f'<ProcessingJob {self.id}: {self.original_filename}>'
    
    @property
    def is_expired(self):
        """Check if the job has expired."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def time_remaining(self):
        """Get time remaining before expiration."""
        if self.is_expired:
            return timedelta(0)
        return self.expires_at - datetime.utcnow()
    
    @property
    def time_remaining_formatted(self):
        """Get formatted time remaining string."""
        if self.is_expired:
            return "Expired"
        
        remaining = self.time_remaining
        hours, remainder = divmod(remaining.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        else:
            return f"{int(minutes):02d}:{int(seconds):02d}"
    
    def start_processing(self):
        """Mark job as started."""
        self.status = 'processing'
        self.started_at = datetime.utcnow()
    
    def complete_processing(self, processed_size, processed_path):
        """Mark job as completed."""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.processed_size = processed_size
        self.processed_path = processed_path
        
        # Calculate compression ratio
        if self.original_size > 0:
            self.compression_ratio = self.processed_size / self.original_size
    
    def fail_processing(self, error_message):
        """Mark job as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = datetime.utcnow()
        self.retry_count += 1
    
    def expire_job(self):
        """Mark job as expired."""
        if not self.is_expired:
            return False
        
        self.status = 'expired'
        return True
    
    def can_retry(self, max_retries=3):
        """Check if job can be retried."""
        return self.status == 'failed' and self.retry_count < max_retries and not self.is_expired
    
    def reset_for_retry(self):
        """Reset job for retry."""
        if not self.can_retry():
            return False
        
        self.status = 'pending'
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        return True
    
    def get_progress_info(self):
        """Get progress information for API responses."""
        progress = 0
        if self.status == 'completed':
            progress = 100
        elif self.status == 'processing':
            # Estimate progress based on time elapsed (rough estimate)
            if self.started_at:
                elapsed = (datetime.utcnow() - self.started_at).total_seconds()
                # Assume 2-3 minutes average processing time
                estimated_total = 150  # 2.5 minutes in seconds
                progress = min(95, int((elapsed / estimated_total) * 100))
            else:
                progress = 5
        elif self.status == 'pending':
            progress = 0
        elif self.status in ['failed', 'expired']:
            progress = 0
        
        return progress
    
    def to_dict(self, include_paths=False):
        """Convert job to dictionary for API responses."""
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'original_filename': self.original_filename,
            'processed_filename': self.processed_filename,
            'original_size': self.original_size,
            'processed_size': self.processed_size,
            'compression_ratio': self.compression_ratio,
            'quality_preset': self.quality_preset,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'expires_at': self.expires_at.isoformat(),
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'is_expired': self.is_expired,
            'time_remaining': self.time_remaining_formatted,
            'progress': self.get_progress_info()
        }
        
        if include_paths:
            data.update({
                'upload_path': self.upload_path,
                'processed_path': self.processed_path
            })
        
        return data
    
    @staticmethod
    def cleanup_expired_jobs():
        """Clean up expired jobs from database."""
        expired_jobs = ProcessingJob.query.filter(
            ProcessingJob.expires_at < datetime.utcnow()
        ).all()
        
        for job in expired_jobs:
            job.expire_job()
        
        db.session.commit()
        return len(expired_jobs)
    
    @staticmethod
    def cleanup_stalled_jobs():
        """Mark old pending jobs as failed (jobs stuck for more than 10 minutes)."""
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        
        stalled_jobs = ProcessingJob.query.filter(
            ProcessingJob.status == 'pending',
            ProcessingJob.created_at < cutoff_time
        ).all()
        
        for job in stalled_jobs:
            job.status = 'failed'
            job.error_message = 'Processing timed out - job was stuck in pending state'
            job.completed_at = datetime.utcnow()
        
        if stalled_jobs:
            db.session.commit()
        
        return len(stalled_jobs)
    
    @staticmethod
    def get_user_active_jobs(user_id):
        """Get all active jobs for a user."""
        return ProcessingJob.query.filter_by(user_id=user_id).filter(
            ProcessingJob.status.in_(['pending', 'processing', 'completed'])
        ).filter(
            ProcessingJob.expires_at > datetime.utcnow()
        ).order_by(ProcessingJob.created_at.desc()).all()
    
    @staticmethod
    def get_user_job_history(user_id, limit=50):
        """Get job history for a user."""
        return ProcessingJob.query.filter_by(user_id=user_id).order_by(
            ProcessingJob.created_at.desc()
        ).limit(limit).all()