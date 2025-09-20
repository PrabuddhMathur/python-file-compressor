from flask import request, jsonify, current_app
from flask_login import current_user
from . import api
from auth.decorators import active_user_required, handle_exceptions, log_api_access
from models import db
from models.user import User
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog
from services.file_manager import file_manager
from utils.security import rate_limiter

@api.route('/user/profile', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('get_user_profile')
def get_user_profile():
    """Get current user's profile information."""
    try:
        # Get user data
        user_data = current_user.to_dict()
        
        # Add usage statistics
        quota_info = rate_limiter.get_user_quota_info(current_user)
        user_data['quota'] = quota_info
        
        # Add job statistics
        total_jobs = current_user.processing_jobs.count()
        completed_jobs = current_user.processing_jobs.filter_by(status='completed').count()
        failed_jobs = current_user.processing_jobs.filter_by(status='failed').count()
        
        user_data['job_stats'] = {
            'total_jobs': total_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs,
            'success_rate': round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 1)
        }
        
        # Add storage statistics
        storage_stats = file_manager.get_storage_stats(current_user.id)
        user_data['storage_stats'] = storage_stats
        
        return jsonify({
            'success': True,
            'user': user_data
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user profile: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve profile information'
        }), 500

@api.route('/user/jobs', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('get_user_job_history')
def get_user_job_history():
    """Get user's job history with filtering options."""
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        status_filter = request.args.get('status', 'all')
        quality_filter = request.args.get('quality')
        
        # Build query
        query = ProcessingJob.query.filter_by(user_id=current_user.id)
        
        # Apply filters
        if status_filter != 'all':
            if status_filter == 'active':
                query = query.filter(ProcessingJob.status.in_(['pending', 'processing']))
            elif status_filter in ['completed', 'failed', 'expired']:
                query = query.filter_by(status=status_filter)
        
        if quality_filter:
            query = query.filter_by(quality_preset=quality_filter)
        
        # Paginate results
        jobs_pagination = query.order_by(ProcessingJob.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        jobs_data = []
        for job in jobs_pagination.items:
            job_data = job.to_dict()
            
            # Add download URL if available
            if (job.status == 'completed' and job.processed_path and 
                not job.is_expired):
                job_data['download_url'] = f"/api/process/download/{job.id}"
            
            # Add compression info
            if job.compression_ratio:
                original_mb = round(job.original_size / (1024 * 1024), 2)
                processed_mb = round(job.processed_size / (1024 * 1024), 2)
                savings_mb = round((job.original_size - job.processed_size) / (1024 * 1024), 2)
                savings_percent = round((1 - job.compression_ratio) * 100, 1)
                
                job_data['compression_info'] = {
                    'original_size_mb': original_mb,
                    'processed_size_mb': processed_mb,
                    'savings_mb': savings_mb,
                    'savings_percent': savings_percent
                }
            
            jobs_data.append(job_data)
        
        return jsonify({
            'success': True,
            'jobs': jobs_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': jobs_pagination.total,
                'pages': jobs_pagination.pages,
                'has_next': jobs_pagination.has_next,
                'has_prev': jobs_pagination.has_prev
            }
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user job history: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve job history'
        }), 500

@api.route('/user/quota', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('get_user_quota')
def get_user_quota():
    """Get user's current quota and usage information."""
    try:
        # Get quota information
        quota_info = rate_limiter.get_user_quota_info(current_user)
        
        # Add time until reset
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time_until_reset = tomorrow - now
        
        quota_info['time_until_reset'] = {
            'hours': time_until_reset.seconds // 3600,
            'minutes': (time_until_reset.seconds % 3600) // 60,
            'total_seconds': time_until_reset.total_seconds()
        }
        
        # Add percentage usage
        daily_file_usage_percent = (quota_info['daily_usage']['files'] / 
                                  quota_info['daily_limits']['files'] * 100)
        daily_storage_usage_percent = (quota_info['daily_usage']['storage_mb'] / 
                                     quota_info['daily_limits']['storage_mb'] * 100)
        session_storage_usage_percent = (quota_info['session_usage']['storage_mb'] / 
                                       quota_info['session_limit_mb'] * 100)
        
        quota_info['usage_percentages'] = {
            'daily_files': round(daily_file_usage_percent, 1),
            'daily_storage': round(daily_storage_usage_percent, 1),
            'session_storage': round(session_storage_usage_percent, 1)
        }
        
        # Add warnings
        warnings = []
        if daily_file_usage_percent > 80:
            warnings.append("Daily file limit nearly reached")
        if daily_storage_usage_percent > 80:
            warnings.append("Daily storage limit nearly reached")
        if session_storage_usage_percent > 80:
            warnings.append("Session storage limit nearly reached")
        
        quota_info['warnings'] = warnings
        
        return jsonify({
            'success': True,
            'quota': quota_info
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user quota: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve quota information'
        }), 500

@api.route('/user/activity', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('get_user_activity')
def get_user_activity():
    """Get user's recent activity log."""
    try:
        limit = min(request.args.get('limit', 50, type=int), 100)
        action_filter = request.args.get('action')
        
        # Build query
        query = AuditLog.query.filter_by(user_id=current_user.id)
        
        if action_filter:
            query = query.filter_by(action=action_filter)
        
        # Get recent logs
        logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
        
        logs_data = []
        for log in logs:
            log_data = log.to_dict()
            
            # Add human-readable descriptions
            log_data['description'] = _get_activity_description(log)
            
            logs_data.append(log_data)
        
        return jsonify({
            'success': True,
            'activity': logs_data,
            'total': len(logs_data)
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user activity: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve activity log'
        }), 500

@api.route('/user/statistics', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('get_user_statistics')
def get_user_statistics():
    """Get comprehensive user statistics."""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        # Time periods for statistics
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Job statistics by time period
        stats = {
            'all_time': {
                'total_jobs': current_user.processing_jobs.count(),
                'completed_jobs': current_user.processing_jobs.filter_by(status='completed').count(),
                'failed_jobs': current_user.processing_jobs.filter_by(status='failed').count(),
            },
            'this_month': {
                'total_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= month_ago
                ).count(),
                'completed_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= month_ago,
                    ProcessingJob.status == 'completed'
                ).count(),
            },
            'this_week': {
                'total_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= week_ago
                ).count(),
                'completed_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= week_ago,
                    ProcessingJob.status == 'completed'
                ).count(),
            },
            'today': {
                'total_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= today
                ).count(),
                'completed_jobs': current_user.processing_jobs.filter(
                    ProcessingJob.created_at >= today,
                    ProcessingJob.status == 'completed'
                ).count(),
            }
        }
        
        # Calculate success rates
        for period in stats:
            total = stats[period]['total_jobs']
            completed = stats[period]['completed_jobs']
            stats[period]['success_rate'] = round(
                (completed / total * 100) if total > 0 else 0, 1
            )
        
        # Compression statistics
        completed_jobs = current_user.processing_jobs.filter_by(status='completed').all()
        
        if completed_jobs:
            total_original_size = sum(job.original_size for job in completed_jobs)
            total_processed_size = sum(job.processed_size for job in completed_jobs)
            total_savings = total_original_size - total_processed_size
            average_compression = total_processed_size / total_original_size if total_original_size > 0 else 0
            
            compression_stats = {
                'total_files_processed': len(completed_jobs),
                'total_original_size_mb': round(total_original_size / (1024 * 1024), 2),
                'total_processed_size_mb': round(total_processed_size / (1024 * 1024), 2),
                'total_savings_mb': round(total_savings / (1024 * 1024), 2),
                'average_compression_ratio': round(average_compression, 3),
                'average_savings_percent': round((1 - average_compression) * 100, 1),
            }
        else:
            compression_stats = {
                'total_files_processed': 0,
                'total_original_size_mb': 0,
                'total_processed_size_mb': 0,
                'total_savings_mb': 0,
                'average_compression_ratio': 0,
                'average_savings_percent': 0,
            }
        
        # Quality preset usage
        preset_usage = db.session.query(
            ProcessingJob.quality_preset,
            func.count(ProcessingJob.id).label('count')
        ).filter_by(
            user_id=current_user.id
        ).group_by(ProcessingJob.quality_preset).all()
        
        preset_stats = {preset: count for preset, count in preset_usage}
        
        return jsonify({
            'success': True,
            'statistics': {
                'job_stats': stats,
                'compression_stats': compression_stats,
                'preset_usage': preset_stats,
                'account_info': {
                    'member_since': current_user.created_at.isoformat(),
                    'days_active': (now - current_user.created_at).days,
                    'last_login': current_user.last_login.isoformat() if current_user.last_login else None
                }
            }
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user statistics: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve statistics'
        }), 500

@api.route('/user/preferences', methods=['GET', 'POST'])
@active_user_required
@handle_exceptions
def user_preferences():
    """Get or update user preferences."""
    if request.method == 'GET':
        try:
            # For now, return basic preferences
            # In a more complete implementation, you might have a UserPreferences model
            preferences = {
                'default_quality': 'medium',
                'email_notifications': False,
                'auto_delete_files': True,
                'preferred_download_format': 'original_name'
            }
            
            return jsonify({
                'success': True,
                'preferences': preferences
            }), 200
        
        except Exception as e:
            current_app.logger.error(f"Failed to get user preferences: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve preferences'
            }), 500
    
    else:  # POST
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'No preference data provided'
                }), 400
            
            # In a complete implementation, you would save these to a UserPreferences model
            # For now, just validate and return success
            
            return jsonify({
                'success': True,
                'message': 'Preferences updated successfully',
                'preferences': data
            }), 200
        
        except Exception as e:
            current_app.logger.error(f"Failed to update user preferences: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to update preferences'
            }), 500

def _get_activity_description(log):
    """Generate human-readable description for activity log entries."""
    descriptions = {
        'login_success': 'Logged in successfully',
        'logout': 'Logged out',
        'file_upload': 'Uploaded a file for processing',
        'file_download': 'Downloaded a processed file',
        'processing_start': 'Started PDF processing',
        'processing_complete': 'PDF processing completed',
        'processing_failed': 'PDF processing failed',
        'session_clear': 'Cleared session files',
        'rate_limit_exceeded': 'Rate limit exceeded',
    }
    
    description = descriptions.get(log.action, f'Action: {log.action}')
    
    # Add additional context from details
    if log.details:
        if log.action == 'file_upload' and 'filename' in log.details:
            description += f" ({log.details['filename']})"
        elif log.action in ['processing_complete', 'processing_failed'] and 'compression_ratio' in log.details:
            ratio = log.details['compression_ratio']
            savings = round((1 - ratio) * 100, 1)
            description += f" (saved {savings}%)"
    
    return description