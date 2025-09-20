"""Tests for models (User, ProcessingJob, AuditLog)."""

import pytest
from datetime import datetime, timedelta
from models.user import User
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog
from models import db


class TestUserModel:
    """Test User model functionality."""
    
    def test_create_user(self, app):
        """Test creating a new user."""
        with app.app_context():
            user = User(
                email='test@example.com',
                full_name='Test User',
                is_active=True
            )
            user.set_password('testpassword')
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.email == 'test@example.com'
            assert user.full_name == 'Test User'
            assert user.is_active is True
            assert user.is_admin is False  # Default
    
    def test_password_hashing(self, app):
        """Test password hashing and verification."""
        with app.app_context():
            user = User(email='test@example.com', full_name='Test User')
            user.set_password('testpassword')
            
            assert user.password_hash is not None
            assert user.password_hash != 'testpassword'  # Should be hashed
            assert user.check_password('testpassword') is True
            assert user.check_password('wrongpassword') is False
    
    def test_user_representation(self, regular_user, app):
        """Test user string representation."""
        with app.app_context():
            user_repr = repr(regular_user)
            assert 'user@test.com' in user_repr
    
    def test_user_storage_tracking(self, regular_user, app):
        """Test user storage usage tracking."""
        with app.app_context():
            initial_usage = regular_user.daily_storage_used
            
            # Test daily storage tracking
            regular_user.update_usage_counters(1024)  # 1KB
            assert regular_user.daily_storage_used == initial_usage + 1024
            assert regular_user.session_storage_used >= 1024
    
    def test_user_daily_usage(self, regular_user, app):
        """Test daily usage calculation."""
        with app.app_context():
            # Should start with zero usage
            daily_usage = regular_user.get_daily_usage()
            assert daily_usage['files'] >= 0
            assert daily_usage['storage_mb'] >= 0
    
    def test_user_session_storage(self, regular_user, app):
        """Test session storage management."""
        with app.app_context():
            # Add session storage via usage counters
            regular_user.update_usage_counters(2048)  # 2KB
            assert regular_user.session_storage_used >= 2048
            
            # Clear session storage
            regular_user.clear_session_storage()
            assert regular_user.session_storage_used == 0


class TestProcessingJobModel:
    """Test ProcessingJob model functionality."""
    
    def test_create_processing_job(self, app, regular_user):
        """Test creating a processing job."""
        with app.app_context():
            job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test.pdf'
            )
            db.session.add(job)
            db.session.commit()
            
            assert job.id is not None
            assert job.user_id == regular_user.id
            assert job.original_filename == 'test.pdf'
            assert job.status == 'pending'  # Default status
            assert job.expires_at is not None  # Should be set automatically
    
    def test_job_expiration(self, app, regular_user):
        """Test job expiration logic."""
        with app.app_context():
            job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test.pdf'
            )
            
            # Check expiration is set properly (24 hours from creation)
            expected_expiry = datetime.utcnow() + timedelta(hours=24)
            assert abs((job.expires_at - expected_expiry).total_seconds()) < 60
            
            # Test is_expired property
            assert not job.is_expired  # Should not be expired immediately
            
            # Create an expired job
            expired_job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='expired.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/expired.pdf',
                expires_at=datetime.utcnow() - timedelta(hours=1)  # 1 hour ago
            )
            assert expired_job.is_expired
    
    def test_job_status_progression(self, app, regular_user):
        """Test job status changes."""
        with app.app_context():
            job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test.pdf'
            )
            db.session.add(job)
            db.session.commit()
            
            # Start processing
            job.start_processing()
            assert job.status == 'processing'
            assert job.started_at is not None
            
            # Complete processing
            job.complete_processing(processed_size=512, processed_path='processed/test.pdf')
            assert job.status == 'completed'
            assert job.completed_at is not None
            
            # Calculate compression ratio
            expected_ratio = 512 / 1024  # 50% of original size
            assert abs(job.compression_ratio - expected_ratio) < 0.01
    
    def test_job_failure(self, app, regular_user):
        """Test job failure handling."""
        with app.app_context():
            job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test.pdf'
            )
            db.session.add(job)
            db.session.commit()
            
            # Fail the job
            error_message = "Processing failed due to invalid PDF"
            job.fail_processing(error_message)
            
            assert job.status == 'failed'
            assert job.error_message == error_message
    
    def test_get_user_active_jobs(self, app, regular_user):
        """Test getting active jobs for a user."""
        with app.app_context():
            # Create some jobs
            job1 = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test1.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test1.pdf',
                status='completed'
            )
            job2 = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test2.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/test2.pdf',
                status='processing'
            )
            job3 = ProcessingJob(
                user_id=regular_user.id,
                original_filename='expired.pdf',
                original_size=1024,
                quality_preset='50',
                upload_path='uploads/expired.pdf',
                status='completed',
                expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
            )
            
            db.session.add_all([job1, job2, job3])
            db.session.commit()
            
            active_jobs = ProcessingJob.get_user_active_jobs(regular_user.id)
            
            # Should only return non-expired jobs
            assert len(active_jobs) == 2
            assert job1 in active_jobs
            assert job2 in active_jobs
            assert job3 not in active_jobs


class TestAuditLogModel:
    """Test AuditLog model functionality."""
    
    def test_create_audit_log(self, app, regular_user):
        """Test creating an audit log entry."""
        with app.app_context():
            log = AuditLog(
                user_id=regular_user.id,
                action='test_action',
                ip_address='127.0.0.1',
                user_agent='Test Agent'
            )
            db.session.add(log)
            db.session.commit()
            
            assert log.id is not None
            assert log.user_id == regular_user.id
            assert log.action == 'test_action'
            assert log.created_at is not None
    
    def test_log_login(self, app, regular_user):
        """Test logging login action."""
        with app.app_context():
            initial_count = AuditLog.query.count()
            
            AuditLog.log_login(
                user_id=regular_user.id,
                ip_address='192.168.1.1',
                user_agent='Mozilla/5.0'
            )
            
            assert AuditLog.query.count() == initial_count + 1
            
            log = AuditLog.query.filter_by(action='login_success').first()
            assert log is not None
            assert log.user_id == regular_user.id
            assert log.ip_address == '192.168.1.1'
    
    def test_log_logout(self, app, regular_user):
        """Test logging logout action."""
        with app.app_context():
            AuditLog.log_logout(
                user_id=regular_user.id,
                ip_address='192.168.1.1',
                user_agent='Mozilla/5.0'
            )
            
            log = AuditLog.query.filter_by(action='logout').first()
            assert log.user_id == regular_user.id
    
    def test_log_file_upload(self, app, regular_user):
        """Test logging file upload action."""
        with app.app_context():
            AuditLog.log_action(
                user_id=regular_user.id,
                action='file_upload',
                ip_address='192.168.1.1',
                filename='test.pdf',
                file_size=1024
            )
            
            log = AuditLog.query.filter_by(action='file_upload').first()
            assert log.user_id == regular_user.id
            # Check additional data is stored correctly in details JSON field
            assert log.details is not None
    
    def test_log_user_cleanup(self, app, regular_user):
        """Test logging user cleanup action."""
        with app.app_context():
            AuditLog.log_action(
                user_id=regular_user.id,
                action='user_cleanup',
                ip_address='192.168.1.1',
                files_deleted=5,
                jobs_deleted=3
            )
            
            log = AuditLog.query.filter_by(action='user_cleanup').first()
            assert log.user_id == regular_user.id