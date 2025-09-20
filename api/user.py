from flask import request, jsonify, current_app
from . import api
from auth.decorators import handle_exceptions, log_api_access
from models import db
from models.user import User
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog
from services.file_manager import file_manager
from utils.security import rate_limiter

@api.route('/user/stats', methods=['GET'])
@handle_exceptions
@log_api_access('get_system_stats')
def get_system_stats():
    """Get system-wide statistics (no authentication required)."""
    try:
        # Get system-wide job statistics
        total_jobs = ProcessingJob.query.count()
        completed_jobs = ProcessingJob.query.filter_by(status='completed').count()
        failed_jobs = ProcessingJob.query.filter_by(status='failed').count()
        pending_jobs = ProcessingJob.query.filter_by(status='pending').count()
        processing_jobs = ProcessingJob.query.filter_by(status='processing').count()
        
        stats = {
            'total_jobs': total_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs,
            'pending_jobs': pending_jobs,
            'processing_jobs': processing_jobs,
            'success_rate': round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 1)
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get system stats: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving system statistics'
        }), 500


@api.route('/user/jobs', methods=['GET'])
@handle_exceptions
@log_api_access('get_recent_jobs')
def get_recent_jobs():
    """Get recent jobs (no authentication required)."""
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)  # Max 50 per page
        status = request.args.get('status', None)
        
        # Build query
        query = ProcessingJob.query
        
        if status:
            query = query.filter(ProcessingJob.status == status)
        
        # Get paginated results
        jobs = query.order_by(ProcessingJob.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Format job data
        jobs_data = []
        for job in jobs.items:
            jobs_data.append({
                'id': job.id,
                'original_filename': job.original_filename,
                'status': job.status,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'processing_started_at': job.processing_started_at.isoformat() if job.processing_started_at else None,
                'quality_preset': job.quality_preset,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'error_message': job.error_message
            })
        
        return jsonify({
            'success': True,
            'jobs': jobs_data,
            'pagination': {
                'page': jobs.page,
                'pages': jobs.pages,
                'per_page': jobs.per_page,
                'total': jobs.total,
                'has_next': jobs.has_next,
                'has_prev': jobs.has_prev
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to get jobs: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving jobs'
        }), 500


@api.route('/user/cleanup', methods=['POST'])
@handle_exceptions 
@log_api_access('system_cleanup')
def cleanup_old_files():
    """Clean up old files (no authentication required)."""
    try:
        # Get parameters
        days_old = request.json.get('days_old', 7) if request.is_json else 7
        
        # Perform cleanup
        cleanup_result = file_manager.cleanup_old_files(days_old=days_old)
        
        return jsonify({
            'success': True,
            'message': f'Cleanup completed',
            'cleanup_result': cleanup_result
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to perform cleanup: {e}")
        return jsonify({
            'success': False,
            'message': 'Error performing cleanup'
        }), 500