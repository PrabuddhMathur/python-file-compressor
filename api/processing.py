from flask import request, jsonify, current_app, send_file, session
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from . import api
from auth.decorators import handle_exceptions, log_api_access
from models import db
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog
from services.pdf_processor import pdf_processor
from services.file_manager import file_manager
from utils.validators import FileValidator, InputValidator
from utils.security import rate_limiter

@api.route('/process/upload', methods=['POST'])
@handle_exceptions
@log_api_access('file_upload')
def upload_file():
    """Upload and process PDF file using session-based file management."""
    try:
        # Generate or get session ID
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
            session.permanent = True  # Make session permanent
        session_id = session['session_id']
        
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
        
        # Session-based rate limiting could be implemented here
        # For now, we'll skip rate limiting for anonymous users
        
        # Create a temporary job ID to save the file
        temp_job_id = int(datetime.utcnow().timestamp() * 1000000) % 1000000
        
        # Save uploaded file using session ID
        upload_result = file_manager.save_uploaded_file(file, None, temp_job_id, session_id)
        
        if not upload_result['success']:
            return jsonify({
                'success': False,
                'message': f"Failed to save file: {upload_result['error']}"
            }), 500
        
        # Now create processing job with session_id
        job = ProcessingJob(
            user_id=None,  # No user authentication
            session_id=session_id,  # Track with session
            original_filename=file.filename,
            original_size=file_size,
            quality_preset=quality_preset,
            status='pending',
            upload_path=upload_result['relative_path']
        )
        
        try:
            db.session.add(job)
            db.session.commit()
            
            # File paths are already set correctly in upload_result
            
        except Exception as e:
            db.session.rollback()
            # Clean up uploaded file if database operation fails
            try:
                file_manager.delete_uploaded_file(upload_result['relative_path'])
            except:
                pass
            return jsonify({
                'success': False,
                'message': 'Error creating processing job'
            }), 500
        
        # Log file upload
        AuditLog.log_file_upload(
            user_id=None,  # No user authentication
            filename=file.filename,
            file_size=file_size,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        # Process file immediately
        try:
            # Update processing status
            job.status = 'processing'
            job.start_processing()
            db.session.commit()
            
            # Generate output path for processed file
            output_path = file_manager.get_processed_file_path(
                user_id=None, 
                job_id=job.id, 
                original_filename=file.filename,
                session_id=session_id
            )
            
            # Process the PDF
            processing_result = pdf_processor.process_pdf(
                job_id=job.id,
                input_path=upload_result['file_path'],
                output_path=output_path,  # Now properly set
                quality_preset=quality_preset
            )
            
            if processing_result['success']:
                # Update job with results
                job.status = 'completed'
                job.completed_at = datetime.utcnow()
                job.processed_size = processing_result.get('processed_size', 0)
                job.compression_ratio = processing_result.get('compression_ratio', 0.0)
                job.processed_path = processing_result.get('relative_path', '')
                
                # Log processing completion
                AuditLog.log_processing_complete(
                    user_id=None,  # No user authentication
                    job_id=job.id,
                    processing_time=(job.completed_at - job.started_at).total_seconds(),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
            else:
                job.status = 'failed'
                job.error_message = processing_result.get('error', 'Unknown processing error')
                job.completed_at = datetime.utcnow()
                
                # Log processing failure
                AuditLog.log_processing_failed(
                    user_id=None,  # No user authentication
                    job_id=job.id,
                    error_message=job.error_message,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
            
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Processing error for job {job.id}: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.session.commit()
        
        # Return job status and details
        response_data = {
            'success': True,
            'job': {
                'id': job.id,
                'status': job.status,
                'original_filename': job.original_filename,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'quality_preset': job.quality_preset,
                'created_at': job.created_at.isoformat(),
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message
            }
        }
        
        return jsonify(response_data), 200 if job.status == 'completed' else 202
        
    except Exception as e:
        current_app.logger.error(f"Upload API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Internal server error during file upload'
        }), 500


@api.route('/process/session/info', methods=['GET'])
@handle_exceptions
@log_api_access('session_info')
def get_session_info():
    """Get current session information for debugging."""
    try:
        session_id = session.get('session_id')
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'session_permanent': session.permanent,
            'session_keys': list(session.keys())
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Session info API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving session info'
        }), 500
        
        # Return job status and details
        response_data = {
            'success': True,
            'job': {
                'id': job.id,
                'status': job.status,
                'original_filename': job.original_filename,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'quality_preset': job.quality_preset,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message
            }
        }
        
        return jsonify(response_data), 200 if job.status == 'completed' else 202
        
    except Exception as e:
        current_app.logger.error(f"Upload API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Internal server error during file upload'
        }), 500


@api.route('/process/status/<int:job_id>', methods=['GET'])
@handle_exceptions
@log_api_access('status_check')
def get_job_status(job_id):
    """Get processing job status using session verification."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({
                'success': False,
                'message': 'Session not found'
            }), 401
        
        job = ProcessingJob.query.get(job_id)
        
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Verify job belongs to this session
        if job.session_id != session_id:
            return jsonify({
                'success': False,
                'message': 'Access denied - job does not belong to your session'
            }), 403
        
        response_data = {
            'success': True,
            'job': {
                'id': job.id,
                'status': job.status,
                'original_filename': job.original_filename,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'quality_preset': job.quality_preset,
                'created_at': job.created_at.isoformat(),
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message
            }
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        current_app.logger.error(f"Status API error for job {job_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving job status'
        }), 500


@api.route('/process/download/<int:job_id>', methods=['GET'])
@handle_exceptions
@log_api_access('download')
def download_processed_file(job_id):
    """Download processed file using session verification."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({
                'success': False,
                'message': 'Session not found'
            }), 401
        
        job = ProcessingJob.query.get(job_id)
        
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Verify job belongs to this session
        if job.session_id != session_id:
            return jsonify({
                'success': False,
                'message': 'Access denied - job does not belong to your session'
            }), 403
        
        if job.status != 'completed':
            return jsonify({
                'success': False,
                'message': 'File processing not completed yet'
            }), 400
        
        # Get processed file path
        processed_path = job.get_processed_file_path()
        
        if not processed_path or not os.path.exists(processed_path):
            return jsonify({
                'success': False,
                'message': 'Processed file not found'
            }), 404
        
        # Generate safe filename
        original_name = job.original_filename or 'compressed_file.pdf'
        name_parts = os.path.splitext(original_name)
        download_filename = f"{name_parts[0]}_compressed{name_parts[1]}"
        
        # Log download
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
        current_app.logger.error(f"Download API error for job {job_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Error downloading file'
        }), 500


@api.route('/process/session/clear', methods=['POST'])
@handle_exceptions
@log_api_access('session_clear')
def clear_session():
    """Clear all files and jobs for current session."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({
                'success': False,
                'message': 'No session to clear'
            }), 400
        
        # Clear session files
        result = file_manager.clear_session_files(session_id)
        
        # Clear session
        session.clear()
        
        return jsonify({
            'success': True,
            'message': 'Session cleared successfully',
            'files_cleared': result.get('files_cleared', 0),
            'jobs_affected': result.get('jobs_affected', 0)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Session clear API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Error clearing session'
        }), 500


@api.route('/process/session/jobs', methods=['GET'])
@handle_exceptions
@log_api_access('session_jobs')
def get_session_jobs():
    """Get all jobs for current session."""
    try:
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({
                'success': True,
                'jobs': []
            }), 200
        
        # Get session jobs
        jobs = ProcessingJob.get_session_active_jobs(session_id)
        
        jobs_data = []
        for job in jobs:
            jobs_data.append({
                'id': job.id,
                'status': job.status,
                'original_filename': job.original_filename,
                'original_size': job.original_size,
                'processed_size': job.processed_size,
                'compression_ratio': job.compression_ratio,
                'quality_preset': job.quality_preset,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message
            })
        
        return jsonify({
            'success': True,
            'jobs': jobs_data
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Session jobs API error: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving session jobs'
        }), 500
@api.route('/process/delete/<int:job_id>', methods=['DELETE'])
@handle_exceptions
@log_api_access('delete')
def delete_job(job_id):
    """Delete processing job and associated files (no authentication required)."""
    try:
        job = ProcessingJob.query.get(job_id)
        
        if not job:
            return jsonify({
                'success': False,
                'message': 'Job not found'
            }), 404
        
        # Since no authentication, anyone can delete any job
        # Note: This removes security - in production you might want to add some other protection
        
        # Delete associated files
        delete_result = file_manager.delete_job_files(job.id, None)  # No user_id
        
        # Delete job from database
        db.session.delete(job)
        db.session.commit()
        
        # Log deletion
        AuditLog.log_action(
            user_id=None,  # No user authentication
            action='file_deletion',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            resource_type='job',
            resource_id=str(job_id),
            filename=job.original_filename
        )
        
        return jsonify({
            'success': True,
            'message': 'Job deleted successfully',
            'file_deletion': delete_result
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Delete API error for job {job_id}: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Error deleting job'
        }), 500