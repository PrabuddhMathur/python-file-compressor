from flask import request, jsonify, current_app
from datetime import datetime
from . import api
from auth.decorators import handle_exceptions, log_api_access
from models import db
from models.user import User
from models.audit_log import AuditLog
from models.processing_job import ProcessingJob
from utils.validators import InputValidator
from services.file_manager import file_manager

@api.route('/admin/system-stats', methods=['GET'])
@handle_exceptions
@log_api_access('admin_system_stats')
def get_admin_system_stats():
    """Get system statistics (no authentication required)."""
    try:
        # Get job statistics
        total_jobs = ProcessingJob.query.count()
        completed_jobs = ProcessingJob.query.filter_by(status='completed').count()
        failed_jobs = ProcessingJob.query.filter_by(status='failed').count()
        pending_jobs = ProcessingJob.query.filter_by(status='pending').count()
        processing_jobs = ProcessingJob.query.filter_by(status='processing').count()
        
        # Get recent activity
        recent_jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).limit(10).all()
        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
        
        # Format recent jobs
        recent_jobs_data = []
        for job in recent_jobs:
            recent_jobs_data.append({
                'id': job.id,
                'original_filename': job.original_filename,
                'status': job.status,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio
            })
        
        # Format recent logs
        recent_logs_data = []
        for log in recent_logs:
            recent_logs_data.append({
                'id': log.id,
                'action': log.action,
                'timestamp': log.timestamp.isoformat(),
                'ip_address': log.ip_address,
                'details': log.details
            })
        
        stats = {
            'job_stats': {
                'total_jobs': total_jobs,
                'completed_jobs': completed_jobs,
                'failed_jobs': failed_jobs,
                'pending_jobs': pending_jobs,
                'processing_jobs': processing_jobs,
                'success_rate': round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 1)
            },
            'recent_activity': {
                'recent_jobs': recent_jobs_data,
                'recent_logs': recent_logs_data
            }
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get system stats: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve system statistics'
        }), 500


@api.route('/admin/cleanup', methods=['POST'])
@handle_exceptions
@log_api_access('admin_cleanup')
def perform_cleanup():
    """Perform system cleanup (no authentication required)."""
    try:
        # Get cleanup parameters
        days_old = request.json.get('days_old', 7) if request.is_json else 7
        
        # Perform file cleanup
        cleanup_result = file_manager.cleanup_old_files(days_old=days_old)
        
        # Log cleanup action
        AuditLog.log_system_action(
            user_id=None,  # No user authentication
            action='system_cleanup',
            details=f'Cleaned up files older than {days_old} days',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': f'System cleanup completed for files older than {days_old} days',
            'cleanup_result': cleanup_result
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to perform cleanup: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to perform system cleanup'
        }), 500