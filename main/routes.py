from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc
from . import main
from models import db
from models.processing_job import ProcessingJob
from models.user import User
from models.audit_log import AuditLog
from utils.validators import InputValidator
from services.file_manager import file_manager
import logging

logger = logging.getLogger(__name__)


@main.route('/')
def index():
    """Home page - redirect logged-in users to dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main.route('/dashboard')
@login_required
def dashboard():
    """User dashboard."""
    try:
        # Define default limits (these could be moved to config)
        daily_file_limit = 20
        daily_storage_limit_mb = 100
        session_storage_limit_mb = 50
        
        # Get user's quota information
        quota_info = {
            'daily_usage': current_user.get_daily_usage(),
            'daily_limits': {
                'files': daily_file_limit,
                'storage_mb': daily_storage_limit_mb
            },
            'session_usage': current_user.get_session_usage(),
            'session_limits': {
                'files': 20,  # Default session limit
                'storage_mb': session_storage_limit_mb
            }
        }
        
        # Get recent processing jobs (last 10)
        recent_jobs = ProcessingJob.query.filter_by(user_id=current_user.id)\
                                        .order_by(desc(ProcessingJob.created_at))\
                                        .limit(10)\
                                        .all()
        
        return render_template('main/dashboard.html', 
                             quota_info=quota_info, 
                             recent_jobs=recent_jobs)
                             
    except Exception as e:
        logger.error(f"Dashboard error for user {current_user.id}: {e}")
        flash('Error loading dashboard. Please try again.', 'error')
        return render_template('main/dashboard.html', 
                             quota_info={'daily_usage': {'files': 0, 'storage_mb': 0}, 
                                       'daily_limits': {'files': 50, 'storage_mb': 200},
                                       'session_usage': {'files': 0, 'storage_mb': 0},
                                       'session_limits': {'files': 20, 'storage_mb': 100}}, 
                             recent_jobs=[])


@main.route('/history')
@login_required
def history():
    """Processing history page."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        jobs = ProcessingJob.query.filter_by(user_id=current_user.id)\
                                 .order_by(desc(ProcessingJob.created_at))\
                                 .paginate(
                                     page=page, 
                                     per_page=per_page, 
                                     error_out=False
                                 )
        
        return render_template('main/history.html', jobs=jobs)
        
    except Exception as e:
        logger.error(f"History error for user {current_user.id}: {e}")
        flash('Error loading processing history.', 'error')
        return redirect(url_for('main.dashboard'))


@main.route('/download/<int:job_id>')
@login_required
def download_file(job_id):
    """Download processed file."""
    try:
        job = ProcessingJob.query.get_or_404(job_id)
        
        # Check if user owns this job
        if job.user_id != current_user.id:
            flash('You do not have permission to download this file.', 'error')
            return redirect(url_for('main.dashboard'))
        
        # Check if job is completed and not expired
        if job.status != 'completed':
            flash('File is not ready for download.', 'error')
            return redirect(url_for('main.dashboard'))
            
        if job.is_expired:
            flash('File has expired and is no longer available.', 'error')
            return redirect(url_for('main.dashboard'))
        
        # Get file path using file manager
        file_path = file_manager.get_file_download_path(job)
        if not file_path:
            flash('File not found or access denied.', 'error')
            return redirect(url_for('main.dashboard'))
        
        # Log download
        AuditLog.log_file_download(
            user_id=current_user.id,
            job_id=job_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        # Generate download filename
        import os
        original_name, ext = os.path.splitext(job.original_filename)
        download_filename = f"{original_name}_compressed_{job.quality_preset}{ext}"
        
        # Send file
        from flask import send_file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Download error for job {job_id}, user {current_user.id}: {e}")
        flash('Error downloading file.', 'error')
        return redirect(url_for('main.dashboard'))


@main.route('/download-batch', methods=['POST'])
@login_required
def download_batch():
    """Download multiple files as a ZIP archive."""
    import io
    import zipfile
    import os
    from flask import send_file
    
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        
        if not job_ids:
            return jsonify({'success': False, 'message': 'No files selected for download.'}), 400
        
        if len(job_ids) > 50:  # Reasonable limit
            return jsonify({'success': False, 'message': 'Too many files selected. Maximum 50 files allowed per batch.'}), 400
        
        # Validate all jobs belong to current user and are downloadable
        jobs = ProcessingJob.query.filter(
            ProcessingJob.id.in_(job_ids),
            ProcessingJob.user_id == current_user.id,
            ProcessingJob.status == 'completed'
        ).all()
        
        if len(jobs) != len(job_ids):
            return jsonify({'success': False, 'message': 'Some files are not available for download or do not belong to you.'}), 403
        
        # Check for expired files
        expired_jobs = [job for job in jobs if job.is_expired]
        if expired_jobs:
            expired_names = [job.original_filename for job in expired_jobs]
            return jsonify({
                'success': False, 
                'message': f'Some files have expired: {", ".join(expired_names[:3])}{"..." if len(expired_names) > 3 else ""}'
            }), 410
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for job in jobs:
                # Get file path
                file_path = file_manager.get_file_download_path(job)
                if not file_path or not os.path.exists(file_path):
                    logger.warning(f"File not found for job {job.id}: {file_path}")
                    continue
                
                # Generate filename for ZIP
                original_name, ext = os.path.splitext(job.original_filename)
                zip_filename = f"{original_name}_compressed_{job.quality_preset}{ext}"
                
                # Handle duplicate filenames by adding a number
                counter = 1
                base_zip_filename = zip_filename
                while zip_filename in [info.filename for info in zip_file.infolist()]:
                    name, ext = os.path.splitext(base_zip_filename)
                    zip_filename = f"{name}_{counter}{ext}"
                    counter += 1
                
                # Add file to ZIP
                zip_file.write(file_path, zip_filename)
        
        zip_buffer.seek(0)
        
        # Log batch download
        for job in jobs:
            AuditLog.log_file_download(
                user_id=current_user.id,
                job_id=job.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        # Generate download filename with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"compressed_files_{timestamp}.zip"
        
        return send_file(
            io.BytesIO(zip_buffer.read()),
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"Batch download error for user {current_user.id}: {e}")
        return jsonify({'success': False, 'message': 'Error creating download archive. Please try again.'}), 500


@main.route('/about')
def about():
    """About page."""
    return render_template('main/about.html')


@main.route('/help')
def help():
    """Help page."""
    return render_template('main/help.html')


@main.route('/privacy')
def privacy():
    """Privacy policy page."""
    return render_template('main/privacy.html')


@main.route('/terms')
def terms():
    """Terms of service page."""
    return render_template('main/terms.html')


# Admin routes
@main.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard."""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get system statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        pending_users = User.query.filter_by(is_active=False).count()
        admin_users = User.query.filter_by(is_admin=True).count()
        
        # Get recent activity
        recent_jobs = ProcessingJob.query.order_by(desc(ProcessingJob.created_at)).limit(10).all()
        
        stats = {
            'total_users': total_users,
            'active_users': active_users,
            'pending_users': pending_users,
            'admin_users': admin_users,
            'recent_jobs': recent_jobs
        }
        
        return render_template('main/admin_dashboard.html', stats=stats)
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        flash('Error loading admin dashboard.', 'error')
        return redirect(url_for('main.dashboard'))


@main.route('/api/recent-jobs')
@login_required
def api_recent_jobs():
    """API endpoint to get recent jobs for the current user."""
    try:
        recent_jobs = ProcessingJob.query.filter_by(user_id=current_user.id).order_by(
            desc(ProcessingJob.created_at)
        ).limit(10).all()
        
        jobs_data = []
        for job in recent_jobs:
            jobs_data.append({
                'id': job.id,
                'original_filename': job.original_filename,
                'status': job.status,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'quality_preset': job.quality_preset,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'error_message': job.error_message
            })
        
        return jsonify({
            'success': True,
            'jobs': jobs_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching recent jobs for user {current_user.id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Error fetching recent jobs'
        }), 500


@main.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return render_template('errors/404.html'), 404


@main.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return render_template('errors/500.html'), 500
