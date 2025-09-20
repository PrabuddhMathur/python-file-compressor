import os
import subprocess
import time
import threading
from datetime import datetime
from flask import current_app
from models import db
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog

class PDFProcessor:
    """PDF compression processor using Ghostscript."""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize PDF processor with Flask app."""
        self.app = app
        self.ghostscript_path = app.config.get('GHOSTSCRIPT_PATH', '/usr/bin/gs')
        self.processing_timeout = app.config.get('PROCESSING_TIMEOUT', 300)  # 5 minutes
        self.quality_presets = app.config.get('QUALITY_PRESETS', {})
    
    def process_pdf(self, job_id, input_path, output_path, quality_preset):
        """Process PDF file with specified quality preset."""
        try:
            # Get job from database
            job = ProcessingJob.query.get(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            
            # Mark job as started
            job.start_processing()
            db.session.commit()
            
            # Log processing start
            AuditLog.log_processing_start(
                user_id=job.user_id,
                job_id=job_id,
                ip_address='system',
                quality_preset=quality_preset
            )
            
            # Get quality preset configuration
            preset_config = self.quality_presets.get(quality_preset)
            if not preset_config:
                raise ValueError(f"Invalid quality preset: {quality_preset}")
            
            # Build Ghostscript command
            gs_command = self._build_ghostscript_command(
                input_path, output_path, preset_config
            )
            
            # Execute Ghostscript with timeout
            start_time = time.time()
            success = self._execute_ghostscript(gs_command, job_id)
            processing_time = time.time() - start_time
            
            if success and os.path.exists(output_path):
                # Get file sizes
                original_size = os.path.getsize(input_path)
                processed_size = os.path.getsize(output_path)
                
                # Store relative path for the processed file
                from services.file_manager import file_manager
                relative_path = os.path.relpath(output_path, file_manager.upload_folder)
                
                # Update job with success
                job.complete_processing(processed_size, relative_path)
                db.session.commit()
                
                # Log successful processing
                compression_ratio = processed_size / original_size if original_size > 0 else 0
                AuditLog.log_processing_complete(
                    user_id=job.user_id,
                    job_id=job_id,
                    ip_address='system',
                    compression_ratio=compression_ratio,
                    processing_time=processing_time
                )
                
                return {
                    'success': True,
                    'message': f"PDF processed successfully. Compression ratio: {compression_ratio:.2f}",
                    'processed_size': processed_size,
                    'compression_ratio': compression_ratio,
                    'relative_path': relative_path
                }
            
            else:
                error_msg = "Ghostscript processing failed"
                job.fail_processing(error_msg)
                db.session.commit()
                
                AuditLog.log_processing_failed(
                    user_id=job.user_id,
                    job_id=job_id,
                    ip_address='system',
                    error_message=error_msg
                )
                
                return {
                    'success': False,
                    'error': error_msg
                }
        
        except Exception as e:
            error_msg = str(e)
            current_app.logger.error(f"PDF processing failed for job {job_id}: {error_msg}")
            
            try:
                job = ProcessingJob.query.get(job_id)
                if job:
                    job.fail_processing(error_msg)
                    db.session.commit()
                    
                    AuditLog.log_processing_failed(
                        user_id=job.user_id,
                        job_id=job_id,
                        ip_address='system',
                        error_message=error_msg
                    )
            except Exception as db_error:
                current_app.logger.error(f"Failed to update job status: {db_error}")
            
            return {
                'success': False,
                'error': error_msg
            }
    
    def process_pdf_async(self, job_id, input_path, output_path, quality_preset):
        """Process PDF asynchronously in background thread."""
        def process_in_background():
            with self.app.app_context():
                self.process_pdf(job_id, input_path, output_path, quality_preset)
        
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()
        return thread
    
    def _build_ghostscript_command(self, input_path, output_path, preset_config):
        """Build Ghostscript command with preset configuration."""
        command = [
            self.ghostscript_path,
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/default',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            '-dSAFER',
            '-dAutoRotatePages=/None',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Bicubic',
        ]
        
        # Add preset-specific arguments
        command.extend(preset_config['ghostscript_args'])
        
        # Add input and output files
        command.extend([
            f'-sOutputFile={output_path}',
            input_path
        ])
        
        return command
    
    def _execute_ghostscript(self, command, job_id):
        """Execute Ghostscript command with timeout and monitoring."""
        try:
            current_app.logger.info(f"Executing Ghostscript for job {job_id}: {' '.join(command)}")
            
            # Start the process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(timeout=self.processing_timeout)
            except subprocess.TimeoutExpired:
                current_app.logger.error(f"Ghostscript timeout for job {job_id}")
                process.kill()
                stdout, stderr = process.communicate()
                return False
            
            # Check return code
            if process.returncode == 0:
                current_app.logger.info(f"Ghostscript completed successfully for job {job_id}")
                return True
            else:
                current_app.logger.error(f"Ghostscript failed for job {job_id}. Return code: {process.returncode}")
                current_app.logger.error(f"Ghostscript stderr: {stderr}")
                return False
        
        except FileNotFoundError:
            current_app.logger.error(f"Ghostscript not found at {self.ghostscript_path}")
            return False
        except Exception as e:
            current_app.logger.error(f"Unexpected error executing Ghostscript for job {job_id}: {e}")
            return False
    
    def validate_pdf_integrity(self, pdf_path):
        """Validate PDF file integrity after processing."""
        try:
            # Use Ghostscript to validate PDF
            command = [
                self.ghostscript_path,
                '-dNODISPLAY',
                '-dNOPAUSE',
                '-dBATCH',
                '-dQUIET',
                '-dSAFER',
                pdf_path
            ]
            
            process = subprocess.run(
                command,
                capture_output=True,
                timeout=30,  # Short timeout for validation
                text=True
            )
            
            return process.returncode == 0
        
        except Exception as e:
            current_app.logger.error(f"PDF validation failed: {e}")
            return False
    
    def get_pdf_info(self, pdf_path):
        """Get PDF file information using Ghostscript."""
        try:
            command = [
                self.ghostscript_path,
                '-dNODISPLAY',
                '-dNOPAUSE',
                '-dBATCH',
                '-dQUIET',
                '-dSAFER',
                '-c',
                f'({pdf_path}) (r) file runpdfbegin pdfpagecount = quit'
            ]
            
            process = subprocess.run(
                command,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            if process.returncode == 0:
                try:
                    page_count = int(process.stdout.strip())
                    return {
                        'page_count': page_count,
                        'valid': True
                    }
                except ValueError:
                    pass
            
            return {
                'page_count': None,
                'valid': False
            }
        
        except Exception as e:
            current_app.logger.error(f"Failed to get PDF info: {e}")
            return {
                'page_count': None,
                'valid': False
            }
    
    def estimate_processing_time(self, file_size, quality_preset):
        """Estimate processing time based on file size and quality preset."""
        # Base processing time per MB (in seconds)
        base_time_per_mb = {
            'high': 10,    # High quality takes longer
            'medium': 6,   # Medium quality
            'low': 3       # Low quality is fastest
        }
        
        file_size_mb = file_size / (1024 * 1024)
        base_time = base_time_per_mb.get(quality_preset, 6)
        
        # Calculate estimated time with minimum and maximum bounds
        estimated_seconds = max(30, min(300, int(file_size_mb * base_time)))
        
        # Convert to human-readable format
        if estimated_seconds < 60:
            return f"{estimated_seconds} seconds"
        else:
            minutes = estimated_seconds // 60
            seconds = estimated_seconds % 60
            if seconds > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{minutes} minutes"
    
    def get_quality_preset_info(self, preset_name):
        """Get information about a quality preset."""
        preset = self.quality_presets.get(preset_name)
        if not preset:
            return None
        
        return {
            'name': preset.get('name', preset_name.title()),
            'description': preset.get('description', ''),
            'expected_compression': preset.get('expected_compression', 0.5),
            'expected_reduction_percent': int((1 - preset.get('expected_compression', 0.5)) * 100)
        }
    
    def get_available_presets(self):
        """Get all available quality presets."""
        presets = {}
        for preset_name, preset_config in self.quality_presets.items():
            presets[preset_name] = self.get_quality_preset_info(preset_name)
        return presets
    
    @staticmethod
    def cleanup_failed_processing(job_id, input_path=None, output_path=None):
        """Clean up files from failed processing."""
        try:
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
                current_app.logger.info(f"Cleaned up failed output file: {output_path}")
        except Exception as e:
            current_app.logger.error(f"Failed to cleanup failed processing files: {e}")

# Create global PDF processor instance
pdf_processor = PDFProcessor()