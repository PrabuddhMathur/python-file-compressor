from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, session
from sqlalchemy import desc
from . import main
from models import db
from models.processing_job import ProcessingJob
from models.user import User
from models.audit_log import AuditLog
from utils.validators import InputValidator
from services.file_manager import file_manager
import logging
import os
import io
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename
import unicodedata
import re

logger = logging.getLogger(__name__)


@main.route('/')
def dashboard():
    """Main dashboard page - now available to all users."""
    try:
        # Define default limits (these could be moved to config)
        daily_file_limit = 20
        daily_storage_limit_mb = 100
        session_storage_limit_mb = 50
        
        # Get quota information (simplified without user context)
        quota_info = {
            'daily_usage': {'files': 0, 'storage_mb': 0},
            'daily_limits': {
                'files': daily_file_limit,
                'storage_mb': daily_storage_limit_mb
            },
            'session_usage': {'files': 0, 'storage_mb': 0},
            'session_limits': {
                'files': 20,  # Default session limit
                'storage_mb': session_storage_limit_mb
            }
        }
        
        # Get recent processing jobs for current session (last 10)
        session_id = session.get('session_id')
        
        if session_id:
            recent_jobs = ProcessingJob.query.filter_by(session_id=session_id)\
                                            .order_by(desc(ProcessingJob.created_at))\
                                            .limit(10)\
                                            .all()
        else:
            recent_jobs = []
        
        return render_template('main/dashboard.html', 
                             quota_info=quota_info, 
                             recent_jobs=recent_jobs)
                             
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash('Error loading dashboard. Please try again.', 'error')
        return render_template('main/dashboard.html', 
                             quota_info={'daily_usage': {'files': 0, 'storage_mb': 0}, 
                                       'daily_limits': {'files': 50, 'storage_mb': 200},
                                       'session_usage': {'files': 0, 'storage_mb': 0},
                                       'session_limits': {'files': 20, 'storage_mb': 100}}, 
                             recent_jobs=[])


@main.route('/history')
def history():
    """Processing history page - session-based."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        if session_id:
            # Show jobs for current session
            jobs = ProcessingJob.query.filter_by(session_id=session_id)\
                                     .order_by(desc(ProcessingJob.created_at))\
                                     .paginate(
                                         page=page, 
                                         per_page=per_page, 
                                         error_out=False
                                     )
        else:
            # No session - show empty results
            jobs = ProcessingJob.query.filter_by(id=-1)\
                                     .paginate(
                                         page=page, 
                                         per_page=per_page, 
                                         error_out=False
                                     )
        
        return render_template('main/history.html', jobs=jobs)
        
    except Exception as e:
        logger.error(f"History error: {e}")
        flash('Error loading processing history.', 'error')
        return redirect(url_for('main.dashboard'))


@main.route('/download/<int:job_id>')
def download_file(job_id):
    """Download processed file with session verification."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            flash('Session expired. Please upload a new file.', 'error')
            return redirect(url_for('main.dashboard'))
        
        job = ProcessingJob.query.get_or_404(job_id)
        
        # Verify job belongs to this session
        if job.session_id != session_id:
            flash('Access denied - file does not belong to your session.', 'error')
            return redirect(url_for('main.dashboard'))
        
        # Check if file is ready for download
        if job.status != 'completed':
            flash('File processing not completed yet. Please wait.', 'warning')
            return redirect(url_for('main.history'))
        
        # Check if processed file exists
        processed_path = job.get_processed_file_path()
        if not processed_path or not os.path.exists(processed_path):
            flash('Processed file not found. It may have been deleted.', 'error')
            return redirect(url_for('main.history'))
        
        def make_safe_filename(filename):
            # Remove non-ASCII characters and normalize
            filename = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
            # Replace spaces and special characters with underscores
            filename = re.sub(r'[^\w\s.\-]', '_', filename)
            # Replace multiple spaces/underscores with single underscore
            filename = re.sub(r'[\-\s_]+', '_', filename)
            return filename.strip('_')
        
        # Create download filename
        original_name = job.original_filename or 'compressed_file.pdf'
        name_parts = os.path.splitext(original_name)
        safe_name = make_safe_filename(name_parts[0])
        download_filename = f"{safe_name}_compressed{name_parts[1]}"
        
        # Log file download (simplified without user context)
        AuditLog.log_file_download(
            user_id=None,  # No user authentication
            job_id=job.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return send_file(
            processed_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Download error for job {job_id}: {e}")
        flash('Error downloading file. Please try again.', 'error')
        return redirect(url_for('main.history'))


@main.route('/batch-download', methods=['POST'])
@main.route('/download-batch', methods=['POST'])  # Alias for frontend compatibility
def batch_download():
    """Download multiple files as a ZIP archive."""
    try:
        # Get session ID for verification
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'success': False, 'message': 'Session expired. Please refresh the page.'}), 403
        
        # Get job IDs from request
        job_ids = request.json.get('job_ids', []) if request.is_json else request.form.getlist('job_ids')
        
        if not job_ids:
            return jsonify({'success': False, 'message': 'No files selected for download.'}), 400
        
        # Convert to integers
        try:
            job_ids = [int(job_id) for job_id in job_ids]
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid job IDs provided.'}), 400
        
        # Get jobs with session verification
        jobs = ProcessingJob.query.filter(
            ProcessingJob.id.in_(job_ids),
            ProcessingJob.session_id == session_id  # Verify session ownership
        ).all()
        
        if not jobs:
            return jsonify({'success': False, 'message': 'No valid files found for download.'}), 404
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for job in jobs:
                try:
                    processed_path = job.get_processed_file_path()
                    if processed_path and os.path.exists(processed_path):
                        # Create safe filename for ZIP entry
                        original_name = job.original_filename or f'compressed_file_{job.id}.pdf'
                        name_parts = os.path.splitext(original_name)
                        zip_filename = f"{name_parts[0]}_compressed{name_parts[1]}"
                        
                        zip_file.write(processed_path, zip_filename)
                except Exception as e:
                    logger.warning(f"Error adding job {job.id} to ZIP: {e}")
                    continue
        
        zip_buffer.seek(0)
        
        # Log batch download (simplified without user context)
        for job in jobs:
            AuditLog.log_file_download(
                user_id=None,  # No user authentication
                job_id=job.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        # Generate download filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"compressed_files_{timestamp}.zip"
        
        return send_file(
            io.BytesIO(zip_buffer.read()),
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"Batch download error: {e}")
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


@main.route('/api/recent-jobs')
def api_recent_jobs():
    """API endpoint to get recent jobs (no authentication required)."""
    try:
        recent_jobs = ProcessingJob.query.order_by(
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
        logger.error(f"Error fetching recent jobs: {e}")
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