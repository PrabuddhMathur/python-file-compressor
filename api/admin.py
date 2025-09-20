from flask import request, jsonify, current_app
from flask_login import current_user
from datetime import datetime
from . import api
from auth.decorators import admin_required, handle_exceptions, validate_json_request, log_api_access
from models import db
from models.user import User
from models.audit_log import AuditLog
from utils.validators import InputValidator

@api.route('/admin/pending-users', methods=['GET'])
@admin_required
@handle_exceptions
@log_api_access('admin_list_pending_users')
def get_pending_users():
    """Get list of users pending approval."""
    try:
        # Get all inactive users (pending approval)
        pending_users = User.query.filter_by(is_active=False).order_by(User.created_at.desc()).all()
        
        users_data = []
        for user in pending_users:
            users_data.append({
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'created_at': user.created_at.isoformat(),
                'days_waiting': (datetime.utcnow() - user.created_at).days
            })
        
        return jsonify({
            'success': True,
            'users': users_data,
            'total_pending': len(users_data)
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get pending users: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve pending users'
        }), 500

@api.route('/admin/approve-user/<int:user_id>', methods=['POST'])
@admin_required
@handle_exceptions
@log_api_access('admin_approve_user')
def approve_user(user_id):
    """Approve a user account."""
    try:
        # Find the user
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Check if user is already active
        if user.is_active:
            return jsonify({
                'success': False,
                'message': 'User is already approved'
            }), 400
        
        # Approve the user
        user.is_active = True
        user.approved_at = datetime.utcnow()
        user.approved_by = current_user.id
        
        db.session.commit()
        
        # Log the approval
        AuditLog.log_user_approval(
            admin_user_id=current_user.id,
            approved_user_id=user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': f'User {user.email} approved successfully',
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'approved_at': user.approved_at.isoformat()
            }
        }), 200
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to approve user {user_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to approve user'
        }), 500

@api.route('/admin/approve-user', methods=['POST'])
@admin_required
@handle_exceptions
@validate_json_request(['email'])
@log_api_access('admin_approve_user_by_email')
def approve_user_by_email():
    """Approve a user account by email address."""
    try:
        data = request.get_json()
        email = data['email'].lower().strip()
        
        # Validate email format
        is_valid, message = InputValidator.validate_email(email)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Find the user
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Check if user is already active
        if user.is_active:
            return jsonify({
                'success': False,
                'message': 'User is already approved'
            }), 400
        
        # Approve the user
        user.is_active = True
        user.approved_at = datetime.utcnow()
        user.approved_by = current_user.id
        
        db.session.commit()
        
        # Log the approval
        AuditLog.log_user_approval(
            admin_user_id=current_user.id,
            approved_user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': True,
            'message': f'User {user.email} approved successfully',
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'approved_at': user.approved_at.isoformat()
            }
        }), 200
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to approve user by email: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to approve user'
        }), 500

@api.route('/admin/users', methods=['GET'])
@admin_required
@handle_exceptions
@log_api_access('admin_list_all_users')
def get_all_users():
    """Get list of all users."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status', 'all')  # all, active, inactive
        
        # Build query
        query = User.query
        
        if status_filter == 'active':
            query = query.filter_by(is_active=True)
        elif status_filter == 'inactive':
            query = query.filter_by(is_active=False)
        
        # Paginate results
        users_pagination = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        users_data = []
        for user in users_pagination.items:
            user_data = user.to_dict()
            # Add additional admin info
            user_data['job_count'] = user.processing_jobs.count()
            user_data['last_activity'] = user.last_login.isoformat() if user.last_login else None
            
            users_data.append(user_data)
        
        return jsonify({
            'success': True,
            'users': users_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': users_pagination.total,
                'pages': users_pagination.pages,
                'has_next': users_pagination.has_next,
                'has_prev': users_pagination.has_prev
            }
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get all users: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve users'
        }), 500

@api.route('/admin/user/<int:user_id>/deactivate', methods=['POST'])
@admin_required
@handle_exceptions
@log_api_access('admin_deactivate_user')
def deactivate_user(user_id):
    """Deactivate a user account."""
    try:
        # Find the user
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Cannot deactivate admin users
        if user.is_admin:
            return jsonify({
                'success': False,
                'message': 'Cannot deactivate admin users'
            }), 403
        
        # Cannot deactivate self
        if user.id == current_user.id:
            return jsonify({
                'success': False,
                'message': 'Cannot deactivate your own account'
            }), 403
        
        # Check if user is already inactive
        if not user.is_active:
            return jsonify({
                'success': False,
                'message': 'User is already deactivated'
            }), 400
        
        # Deactivate the user
        user.is_active = False
        db.session.commit()
        
        # Log the deactivation
        AuditLog.log_action(
            user_id=current_user.id,
            action='admin_deactivate_user',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            resource_type='user',
            resource_id=str(user_id)
        )
        
        return jsonify({
            'success': True,
            'message': f'User {user.email} deactivated successfully'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to deactivate user {user_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to deactivate user'
        }), 500

@api.route('/admin/stats', methods=['GET'])
@admin_required
@handle_exceptions
@log_api_access('admin_get_stats')
def get_admin_stats():
    """Get system statistics for admin dashboard."""
    try:
        from models.processing_job import ProcessingJob
        from services.file_manager import file_manager
        
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        pending_users = User.query.filter_by(is_active=False).count()
        
        # Job statistics
        total_jobs = ProcessingJob.query.count()
        completed_jobs = ProcessingJob.query.filter_by(status='completed').count()
        failed_jobs = ProcessingJob.query.filter_by(status='failed').count()
        processing_jobs = ProcessingJob.query.filter_by(status='processing').count()
        
        # Storage statistics
        storage_stats = file_manager.get_storage_stats()
        
        # Recent activity
        recent_registrations = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).limit(10).all()
        
        return jsonify({
            'success': True,
            'stats': {
                'users': {
                    'total': total_users,
                    'active': active_users,
                    'pending': pending_users
                },
                'jobs': {
                    'total': total_jobs,
                    'completed': completed_jobs,
                    'failed': failed_jobs,
                    'processing': processing_jobs
                },
                'storage': storage_stats
            },
            'recent_activity': {
                'registrations': [user.to_dict() for user in recent_registrations],
                'jobs': [job.to_dict() for job in recent_jobs]
            }
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get admin stats: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve statistics'
        }), 500

@api.route('/admin/audit-logs', methods=['GET'])
@admin_required
@handle_exceptions
@log_api_access('admin_get_audit_logs')
def get_audit_logs():
    """Get audit logs for admin review."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        action_filter = request.args.get('action')
        user_id_filter = request.args.get('user_id', type=int)
        
        # Build query
        query = AuditLog.query
        
        if action_filter:
            query = query.filter_by(action=action_filter)
        
        if user_id_filter:
            query = query.filter_by(user_id=user_id_filter)
        
        # Paginate results
        logs_pagination = query.order_by(AuditLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        logs_data = []
        for log in logs_pagination.items:
            log_data = log.to_dict()
            # Add user information if available
            if log.user:
                log_data['user_email'] = log.user.email
                log_data['user_name'] = log.user.full_name
            
            logs_data.append(log_data)
        
        return jsonify({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': logs_pagination.total,
                'pages': logs_pagination.pages,
                'has_next': logs_pagination.has_next,
                'has_prev': logs_pagination.has_prev
            }
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get audit logs: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve audit logs'
        }), 500