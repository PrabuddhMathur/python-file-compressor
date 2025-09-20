from flask import request, jsonify, current_app, send_file
from flask_login import current_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from . import api
from auth.decorators import active_user_required, handle_exceptions, log_api_access
from models import db
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog
from services.pdf_processor import pdf_processor
from services.file_manager import file_manager
from utils.validators import FileValidator, InputValidator
from utils.security import rate_limiter

@api.route('/process/upload', methods=['POST'])
@active_user_required
@handle_exceptions
@log_api_access('file_upload')
def upload_file():
    """Upload and process PDF file."""
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No file provided'
            }), 400
        
        file = request.files['file']
        quality_preset = request.form.get('quality', 'medium')
        
        # Validate file
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No file selected'
            }), 400
        
        # Validate quality preset
        is_valid, message = InputValidator.validate_quality_preset(quality_preset)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Initialize file validator
        max_file_size = current_app.config.get('MAX_CONTENT_LENGTH', 25 * 1024 * 1024)
        validator = FileValidator(max_file_size=max_file_size)
        
        # Validate file
        is_valid, message = validator.validate_file(file)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Get file info
        file_info = validator.get_file_info(file)
        file_size = file_info['size']
        
        # Check rate limits
        can_upload, limit_message = rate_limiter.check_upload_limits(current_user, file_size)
        if not can_upload:
            AuditLog.log_rate_limit_exceeded(
                user_id=current_user.id,
                ip_address=request.remote_addr,
                limit_type='upload',
                user_agent=request.headers.get('User-Agent')
            )
            
            return jsonify({
                'success': False,
                'message': limit_message,
                'error_type': 'rate_limit_exceeded'
            }), 429
        
        # First, create a temporary job ID to save the file
        # We need to save the file first to get the upload_path before creating the job
        temp_job_id = int(datetime.utcnow().timestamp() * 1000000) % 1000000  # Use timestamp as temp ID
        
        # Save uploaded file first
        upload_result = file_manager.save_uploaded_file(file, current_user.id, temp_job_id)
        
        if not upload_result['success']:
            return jsonify({
                'success': False,
                'message': f"Failed to save file: {upload_result['error']}"
            }), 500
        
        # Now create processing job with the upload_path
        job = ProcessingJob(
            user_id=current_user.id,
            original_filename=file.filename,
            original_size=file_size,
            quality_preset=quality_preset,
            status='pending',
            upload_path=upload_result['relative_path']
        )
        
        db.session.add(job)
        db.session.flush()  # Get the real job ID
        
        # Update the saved file with the correct job ID if needed
        if temp_job_id != job.id:
            # We might need to rename the file to use the correct job ID
            # But for now, let's keep using the upload_path as is
            pass
        
        # Update user usage counters
        rate_limiter.update_upload_counters(current_user, file_size)
        
        db.session.commit()
        
        # Get processed file path
        input_path = upload_result['file_path']
        output_path = file_manager.get_processed_file_path(
            current_user.id, job.id, file.filename
        )
        
        # Start processing asynchronously
        pdf_processor.process_pdf_async(job.id, input_path, output_path, quality_preset)
        
        # Get estimated processing time
        estimated_time = pdf_processor.estimate_processing_time(file_size, quality_preset)
        
        return jsonify({
            'success': True,
            'job_id': job.id,
            'message': 'File uploaded successfully and processing started',
            'estimated_time': estimated_time,
            'file_info': {
                'filename': file_info['filename'],
                'size': file_info['size'],
                'size_mb': file_info['size_mb'],
                'quality_preset': quality_preset
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Upload failed: {e}")
        
        # Check if it's a 413 error and re-raise it
        from werkzeug.exceptions import RequestEntityTooLarge
        if isinstance(e, RequestEntityTooLarge):
            raise e
            
        return jsonify({
            'success': False,
            'message': 'Upload failed. Please try again.'
        }), 500

@api.route('/process/status/<int:job_id>', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('job_status_check')
def get_job_status(job_id):
    """Get processing job status."""
    try:
        # Find job
        job = ProcessingJob.query.get(job_id)
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Check if user owns this job
        if job.user_id != current_user.id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if job is expired
        if job.is_expired:
            job.expire_job()
            db.session.commit()
        
        # Get job status data
        job_data = job.to_dict()
        
        # Add download URL if completed
        if job.status == 'completed' and job.processed_path:
            job_data['download_url'] = f"/api/process/download/{job.id}"
        
        # Add quality preset info
        preset_info = pdf_processor.get_quality_preset_info(job.quality_preset)
        if preset_info:
            job_data['quality_info'] = preset_info
        
        return jsonify({
            'success': True,
            'job': job_data
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get job status for {job_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve job status'
        }), 500

@api.route('/process/download/<int:job_id>', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('file_download')
def download_file(job_id):
    """Download processed file."""
    try:
        # Find job
        job = ProcessingJob.query.get(job_id)
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Check if user owns this job
        if job.user_id != current_user.id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if job is completed
        if job.status != 'completed':
            return jsonify({
                'success': False,
                'message': 'File is not ready for download'
            }), 400
        
        # Check if job is expired
        if job.is_expired:
            return jsonify({
                'success': False,
                'message': 'Download link has expired'
            }), 410
        
        # Get file path
        file_path = file_manager.get_file_download_path(job)
        if not file_path:
            return jsonify({
                'success': False,
                'message': 'File not found or access denied'
            }), 404
        
        # Log download
        AuditLog.log_file_download(
            user_id=current_user.id,
            job_id=job_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        # Generate download filename
        original_name, ext = os.path.splitext(job.original_filename)
        download_filename = f"{original_name}_compressed_{job.quality_preset}.{ext.lstrip('.')}"
        
        # Send file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/pdf'
        )
    
    except Exception as e:
        current_app.logger.error(f"Download failed for job {job_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Download failed'
        }), 500

@api.route('/process/clear-session', methods=['POST'])
@active_user_required
@handle_exceptions
@log_api_access('clear_session')
def clear_session():
    """Clear all session files for the current user."""
    try:
        # Clear session files
        result = file_manager.clear_user_session_files(current_user.id)
        
        if result['success']:
            # Update rate limiter
            rate_limiter.clear_user_session_storage(current_user)
            
            return jsonify({
                'success': True,
                'message': 'Session files cleared successfully',
                'files_cleared': result['files_cleared'],
                'jobs_affected': result['jobs_affected']
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f"Failed to clear session: {result['error']}"
            }), 500
    
    except Exception as e:
        current_app.logger.error(f"Failed to clear session for user {current_user.id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to clear session'
        }), 500

@api.route('/process/jobs', methods=['GET'])
@active_user_required
@handle_exceptions
@log_api_access('list_user_jobs')
def get_user_jobs():
    """Get user's processing jobs."""
    try:
        status_filter = request.args.get('status', 'all')  # all, active, completed, failed
        limit = min(request.args.get('limit', 50, type=int), 100)
        
        # Build query
        query = ProcessingJob.query.filter_by(user_id=current_user.id)
        
        if status_filter == 'active':
            query = query.filter(ProcessingJob.status.in_(['pending', 'processing']))
        elif status_filter == 'completed':
            query = query.filter_by(status='completed')
        elif status_filter == 'failed':
            query = query.filter_by(status='failed')
        
        # Get jobs
        jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()
        
        jobs_data = []
        for job in jobs:
            job_data = job.to_dict()
            
            # Add download URL if completed and not expired
            if job.status == 'completed' and job.processed_path and not job.is_expired:
                job_data['download_url'] = f"/api/process/download/{job.id}"
            
            # Add quality preset info
            preset_info = pdf_processor.get_quality_preset_info(job.quality_preset)
            if preset_info:
                job_data['quality_info'] = preset_info
            
            jobs_data.append(job_data)
        
        return jsonify({
            'success': True,
            'jobs': jobs_data,
            'total': len(jobs_data)
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get user jobs: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve jobs'
        }), 500

@api.route('/process/retry/<int:job_id>', methods=['POST'])
@active_user_required
@handle_exceptions
@log_api_access('retry_job')
def retry_job(job_id):
    """Retry a failed processing job."""
    try:
        # Find job
        job = ProcessingJob.query.get(job_id)
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Check if user owns this job
        if job.user_id != current_user.id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if job can be retried
        if not job.can_retry():
            return jsonify({
                'success': False,
                'message': 'Job cannot be retried (expired or too many attempts)'
            }), 400
        
        # Reset job for retry
        if not job.reset_for_retry():
            return jsonify({
                'success': False,
                'message': 'Failed to reset job for retry'
            }), 500
        
        db.session.commit()
        
        # Get file paths
        input_path = os.path.join(file_manager.upload_folder, job.upload_path)
        output_path = file_manager.get_processed_file_path(
            current_user.id, job.id, job.original_filename
        )
        
        # Start processing asynchronously
        pdf_processor.process_pdf_async(job.id, input_path, output_path, job.quality_preset)
        
        return jsonify({
            'success': True,
            'message': 'Job retry started',
            'job_id': job.id
        }), 200
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to retry job {job_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retry job'
        }), 500

@api.route('/process/presets', methods=['GET'])
@active_user_required
@handle_exceptions
def get_quality_presets():
    """Get available quality presets."""
    try:
        presets = pdf_processor.get_available_presets()
        
        return jsonify({
            'success': True,
            'presets': presets
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get quality presets: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve quality presets'
        }), 500

@api.route('/process/estimate', methods=['POST'])
@active_user_required
@handle_exceptions
def estimate_processing_time():
    """Estimate processing time for given file size and quality."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Request data required'
            }), 400
        
        file_size = data.get('file_size')
        quality_preset = data.get('quality_preset', 'medium')
        
        if not file_size:
            return jsonify({
                'success': False,
                'message': 'File size is required'
            }), 400
        
        # Validate quality preset
        is_valid, message = InputValidator.validate_quality_preset(quality_preset)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Get estimate
        estimated_time = pdf_processor.estimate_processing_time(file_size, quality_preset)
        preset_info = pdf_processor.get_quality_preset_info(quality_preset)
        
        return jsonify({
            'success': True,
            'estimated_time': estimated_time,
            'quality_info': preset_info,
            'file_size_mb': round(file_size / (1024 * 1024), 2)
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to estimate processing time: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to estimate processing time'
        }), 500