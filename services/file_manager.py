import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from flask import current_app
from werkzeug.utils import secure_filename
from models import db
from models.processing_job import ProcessingJob
from models.user import User
from models.audit_log import AuditLog
from utils.security import SecurityUtils

class FileManager:
    """File management service for uploads, processing, and cleanup."""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize file manager with Flask app."""
        self.app = app
        self.upload_folder = app.config.get('UPLOAD_FOLDER', 'storage')
        self.file_retention_hours = app.config.get('FILE_RETENTION_HOURS', 24)
        self.cleanup_enabled = app.config.get('CLEANUP_ENABLED', True)
        
        # Create directory structure
        self._create_directory_structure()
        
        # Start cleanup thread if enabled
        if self.cleanup_enabled:
            self._start_cleanup_thread()
    
    def _create_directory_structure(self):
        """Create required directory structure."""
        directories = [
            self.upload_folder,
            os.path.join(self.upload_folder, 'uploads'),
            os.path.join(self.upload_folder, 'processed'),
            os.path.join(self.upload_folder, 'temp')
        ]
        
        for directory in directories:
            SecurityUtils.create_secure_directory(directory)
    
    def save_uploaded_file(self, file, user_id, job_id):
        """Save uploaded file to storage."""
        try:
            # Generate secure filename
            original_filename = file.filename
            secure_name = SecurityUtils.generate_secure_filename(original_filename, user_id)
            
            # Create user-specific directory
            upload_dir = self._get_user_upload_dir(user_id)
            SecurityUtils.create_secure_directory(upload_dir)
            
            # Full file path
            file_path = os.path.join(upload_dir, secure_name)
            
            # Save file
            file.save(file_path)
            
            # Verify file was saved correctly
            if not os.path.exists(file_path):
                raise IOError("File was not saved correctly")
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Log file upload
            AuditLog.log_file_upload(
                user_id=user_id,
                ip_address='system',
                filename=original_filename,
                file_size=file_size
            )
            
            return {
                'success': True,
                'file_path': file_path,
                'relative_path': os.path.relpath(file_path, self.upload_folder),
                'secure_filename': secure_name,
                'file_size': file_size
            }
        
        except Exception as e:
            current_app.logger.error(f"Failed to save uploaded file: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_processed_file_path(self, user_id, job_id, original_filename):
        """Generate path for processed file."""
        # Get file extension
        if '.' in original_filename:
            name, ext = original_filename.rsplit('.', 1)
        else:
            ext = 'pdf'
        
        # Generate processed filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        processed_filename = f"{user_id}_{job_id}_{timestamp}_processed.{ext}"
        
        # Create processed directory
        processed_dir = self._get_user_processed_dir(user_id)
        SecurityUtils.create_secure_directory(processed_dir)
        
        return os.path.join(processed_dir, processed_filename)
    
    def create_temp_directory(self, job_id):
        """Create temporary directory for processing."""
        temp_dir = os.path.join(self.upload_folder, 'temp', str(job_id))
        SecurityUtils.create_secure_directory(temp_dir)
        return temp_dir
    
    def cleanup_temp_directory(self, job_id):
        """Clean up temporary processing directory."""
        temp_dir = os.path.join(self.upload_folder, 'temp', str(job_id))
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                current_app.logger.info(f"Cleaned up temp directory: {temp_dir}")
                return True
        except Exception as e:
            current_app.logger.error(f"Failed to cleanup temp directory {temp_dir}: {e}")
        return False
    
    def delete_job_files(self, job):
        """Delete all files associated with a job."""
        files_deleted = 0
        
        try:
            # Delete upload file
            if job.upload_path:
                upload_path = os.path.join(self.upload_folder, job.upload_path)
                if os.path.exists(upload_path):
                    SecurityUtils.secure_delete_file(upload_path)
                    files_deleted += 1
            
            # Delete processed file
            if job.processed_path:
                processed_path = os.path.join(self.upload_folder, job.processed_path)
                if os.path.exists(processed_path):
                    SecurityUtils.secure_delete_file(processed_path)
                    files_deleted += 1
            
            # Clean up temp directory
            self.cleanup_temp_directory(job.id)
            
            current_app.logger.info(f"Deleted {files_deleted} files for job {job.id}")
            return files_deleted
        
        except Exception as e:
            current_app.logger.error(f"Failed to delete files for job {job.id}: {e}")
            return 0
    
    def clear_user_session_files(self, user_id):
        """Clear all session files for a user."""
        try:
            # Get all active jobs for user
            active_jobs = ProcessingJob.get_user_active_jobs(user_id)
            
            files_cleared = 0
            for job in active_jobs:
                files_cleared += self.delete_job_files(job)
            
            # Update user session storage counter
            user = User.query.get(user_id)
            if user:
                user.clear_session_storage()
                db.session.commit()
            
            # Log session clear
            AuditLog.log_session_clear(
                user_id=user_id,
                ip_address='system',
                files_cleared=files_cleared
            )
            
            return {
                'success': True,
                'files_cleared': files_cleared,
                'jobs_affected': len(active_jobs)
            }
        
        except Exception as e:
            current_app.logger.error(f"Failed to clear session files for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_file_download_path(self, job):
        """Get download path for processed file."""
        if not job.processed_path:
            return None
        
        # Check if the processed_path already includes the storage folder
        if job.processed_path.startswith(self.upload_folder):
            # Path is already absolute from the upload folder
            file_path = job.processed_path
        else:
            # Path is relative to upload folder
            file_path = os.path.join(self.upload_folder, job.processed_path)
        
        # Verify file exists
        if not os.path.exists(file_path):
            return None
        
        # Verify path is secure
        allowed_dirs = [
            os.path.join(self.upload_folder, 'processed'),
            os.path.join(self.upload_folder, 'uploads')
        ]
        
        if not SecurityUtils.validate_file_path(file_path, allowed_dirs):
            current_app.logger.warning(f"Insecure file path access attempt: {file_path}")
            return None
        
        return file_path
    
    def get_storage_stats(self, user_id=None):
        """Get storage statistics."""
        try:
            stats = {
                'total_files': 0,
                'total_size': 0,
                'upload_files': 0,
                'upload_size': 0,
                'processed_files': 0,
                'processed_size': 0
            }
            
            if user_id:
                # User-specific stats
                upload_dir = self._get_user_upload_dir(user_id)
                processed_dir = self._get_user_processed_dir(user_id)
                
                # Count upload files
                if os.path.exists(upload_dir):
                    for filename in os.listdir(upload_dir):
                        file_path = os.path.join(upload_dir, filename)
                        if os.path.isfile(file_path):
                            stats['upload_files'] += 1
                            stats['upload_size'] += os.path.getsize(file_path)
                
                # Count processed files
                if os.path.exists(processed_dir):
                    for filename in os.listdir(processed_dir):
                        file_path = os.path.join(processed_dir, filename)
                        if os.path.isfile(file_path):
                            stats['processed_files'] += 1
                            stats['processed_size'] += os.path.getsize(file_path)
            
            else:
                # Global stats
                for root, dirs, files in os.walk(self.upload_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        stats['total_files'] += 1
                        stats['total_size'] += file_size
                        
                        if 'uploads' in root:
                            stats['upload_files'] += 1
                            stats['upload_size'] += file_size
                        elif 'processed' in root:
                            stats['processed_files'] += 1
                            stats['processed_size'] += file_size
            
            # Calculate totals for user stats
            if user_id:
                stats['total_files'] = stats['upload_files'] + stats['processed_files']
                stats['total_size'] = stats['upload_size'] + stats['processed_size']
            
            # Convert sizes to MB
            for key in ['total_size', 'upload_size', 'processed_size']:
                stats[f"{key}_mb"] = round(stats[key] / (1024 * 1024), 2)
            
            return stats
        
        except Exception as e:
            current_app.logger.error(f"Failed to get storage stats: {e}")
            return None
    
    def cleanup_expired_files(self):
        """Clean up expired files and jobs."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.file_retention_hours)
            
            # Find expired jobs
            expired_jobs = ProcessingJob.query.filter(
                ProcessingJob.expires_at < datetime.utcnow()
            ).all()
            
            files_deleted = 0
            jobs_cleaned = 0
            
            for job in expired_jobs:
                # Delete associated files
                files_deleted += self.delete_job_files(job)
                
                # Mark job as expired
                if job.expire_job():
                    jobs_cleaned += 1
            
            # Commit database changes
            db.session.commit()
            
            # Clean up empty directories
            self._cleanup_empty_directories()
            
            current_app.logger.info(
                f"Cleanup completed: {files_deleted} files deleted, {jobs_cleaned} jobs expired"
            )
            
            return {
                'files_deleted': files_deleted,
                'jobs_cleaned': jobs_cleaned
            }
        
        except Exception as e:
            current_app.logger.error(f"Cleanup failed: {e}")
            return None
    
    def _cleanup_empty_directories(self):
        """Remove empty directories in storage."""
        try:
            for root, dirs, files in os.walk(self.upload_folder, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        if not os.listdir(dir_path):  # Directory is empty
                            os.rmdir(dir_path)
                    except OSError:
                        pass  # Directory not empty or other error
        except Exception as e:
            current_app.logger.error(f"Failed to cleanup empty directories: {e}")
    
    def _get_user_upload_dir(self, user_id):
        """Get user-specific upload directory."""
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        return os.path.join(self.upload_folder, 'uploads', str(user_id), date_str)
    
    def _get_user_processed_dir(self, user_id):
        """Get user-specific processed files directory."""
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        return os.path.join(self.upload_folder, 'processed', str(user_id), date_str)
    
    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(3600)  # Sleep for 1 hour
                    with self.app.app_context():
                        self.cleanup_expired_files()
                except Exception as e:
                    current_app.logger.error(f"Cleanup thread error: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        self.app.logger.info("File cleanup thread started")
    
    def validate_storage_path(self, file_path):
        """Validate that file path is within allowed storage areas."""
        allowed_dirs = [
            os.path.join(self.upload_folder, 'uploads'),
            os.path.join(self.upload_folder, 'processed'),
            os.path.join(self.upload_folder, 'temp')
        ]
        
        return SecurityUtils.validate_file_path(file_path, allowed_dirs)
    
    def get_file_info(self, file_path):
        """Get information about a file."""
        try:
            if not os.path.exists(file_path):
                return None
            
            stat = os.stat(file_path)
            
            return {
                'path': file_path,
                'size': stat.st_size,
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'exists': True
            }
        
        except Exception as e:
            current_app.logger.error(f"Failed to get file info for {file_path}: {e}")
            return None

# Create global file manager instance
file_manager = FileManager()