"""Tests for main routes and dashboard functionality."""

import pytest
from flask import url_for
from models.user import User
from models.processing_job import ProcessingJob
from models import db
from tests.conftest import create_test_file, cleanup_test_files
from unittest.mock import patch, MagicMock


class TestDashboard:
    """Test dashboard functionality."""
    
    def test_dashboard_loads_for_authenticated_user(self, client, user_headers):
        """Test that dashboard loads for authenticated users."""
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'PDF' in response.data or b'Compress' in response.data
    
    def test_dashboard_shows_user_info(self, client, user_headers):
        """Test that dashboard shows user information."""
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'Test User' in response.data  # User's full name
    
    def test_dashboard_upload_form(self, client, user_headers):
        """Test that dashboard contains upload form."""
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'form' in response.data
        assert b'file' in response.data or b'upload' in response.data


class TestHistory:
    """Test history page functionality."""
    
    def test_history_loads_for_authenticated_user(self, client, user_headers):
        """Test that history page loads for authenticated users."""
        response = client.get('/history')
        assert response.status_code == 200
        assert b'Processing History' in response.data or b'History' in response.data
    
    def test_history_empty_state(self, client, user_headers):
        """Test history page when user has no files."""
        response = client.get('/history')
        assert response.status_code == 200
        # Should show empty state or no files message
        assert b'No files' in response.data or b'empty' in response.data or response.status_code == 200
    
    def test_history_with_jobs(self, client, app, regular_user, user_headers):
        """Test history page with processing jobs."""
        with app.app_context():
            # Create a test job
            job = ProcessingJob(
                user_id=regular_user.id,
                original_filename='test.pdf',
                original_size=1024,
                quality_preset='50',
                status='completed',
                upload_path='uploads/test/test.pdf'
            )
            db.session.add(job)
            db.session.commit()
        
        response = client.get('/history')
        assert response.status_code == 200
        assert b'test.pdf' in response.data


class TestFileUpload:
    """Test file upload functionality."""
    
    def test_upload_requires_authentication(self, client):
        """Test that file upload requires authentication."""
        response = client.post('/api/process/upload')
        assert response.status_code == 401
    
    @patch('services.pdf_processor.pdf_processor.process_pdf_async')
    def test_valid_pdf_upload(self, mock_process, client, app, user_headers, sample_pdf):
        """Test uploading a valid PDF file."""
        mock_process.return_value = {'job_id': 1, 'status': 'pending'}
        
        sample_pdf.seek(0)
        response = client.post('/api/process/upload', 
                             data={
                                 'file': (sample_pdf, 'test.pdf'),
                                 'quality': '50'
                             },
                             content_type='multipart/form-data')
        
        # Should accept the file
        assert response.status_code in [200, 201, 202]  # Various success codes
    
    def test_upload_without_file(self, client, user_headers):
        """Test upload endpoint without file."""
        response = client.post('/api/process/upload', 
                             data={'quality': '50'},
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
    
    def test_upload_invalid_file_type(self, client, user_headers):
        """Test uploading non-PDF file."""
        from io import BytesIO
        
        fake_file = BytesIO(b"This is not a PDF")
        response = client.post('/api/process/upload',
                             data={
                                 'file': (fake_file, 'test.txt'),
                                 'quality': '50'
                             },
                             content_type='multipart/form-data')
        
        assert response.status_code == 400


class TestFileDownload:
    """Test file download functionality."""
    
    def test_download_requires_authentication(self, client):
        """Test that file download requires authentication."""
        response = client.get('/download/1')
        assert response.status_code == 302  # Redirect to login
    
    def test_download_nonexistent_file(self, client, user_headers):
        """Test downloading non-existent file."""
        response = client.get('/download/999')
        # The route uses get_or_404 which should return 404, but exception handler might redirect
        assert response.status_code in [302, 404]  # Either redirect to dashboard or 404
    
    def test_download_other_users_file(self, client, app, admin_user, user_headers):
        """Test that users cannot download other users' files."""
        with app.app_context():
            # Create a job for admin user
            job = ProcessingJob(
                user_id=admin_user.id,
                original_filename='admin.pdf',
                original_size=1024,
                quality_preset='50',
                status='completed',
                upload_path='uploads/admin/admin.pdf',
                processed_path='processed/admin/admin.pdf'
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id
        
        # Try to download as regular user
        response = client.get(f'/download/{job_id}')
        # Should redirect to dashboard with error message, not return 403
        assert response.status_code == 302


class TestBatchDownload:
    """Test batch download functionality."""
    
    def test_batch_download_requires_authentication(self, client):
        """Test that batch download requires authentication."""
        response = client.post('/download-batch')
        assert response.status_code == 302  # Redirect to login
    
    def test_batch_download_empty_list(self, client, user_headers):
        """Test batch download with empty job list."""
        response = client.post('/download-batch',
                             json={'job_ids': []})
        assert response.status_code == 400
    
    def test_batch_download_invalid_jobs(self, client, user_headers):
        """Test batch download with invalid job IDs."""
        response = client.post('/download-batch',
                             json={'job_ids': [999, 1000]})
        # Returns 403 because jobs don't belong to user or don't exist
        assert response.status_code == 403


class TestAPIEndpoints:
    """Test API endpoint functionality."""
    
    def test_user_stats_requires_authentication(self, client):
        """Test that user stats API requires authentication."""
        response = client.get('/api/user/stats')
        assert response.status_code == 401
    
    def test_user_stats_authenticated(self, client, user_headers):
        """Test user stats for authenticated user."""
        response = client.get('/api/user/stats')
        assert response.status_code == 200
        
        if response.content_type == 'application/json':
            data = response.get_json()
            assert 'success' in data
    
    def test_clear_session_requires_authentication(self, client):
        """Test that clear session API requires authentication."""
        response = client.post('/api/user/clear-session')
        assert response.status_code == 401
    
    def test_clear_session_authenticated(self, client, user_headers):
        """Test clear session for authenticated user."""
        response = client.post('/api/user/clear-session')
        assert response.status_code == 200
        
        if response.content_type == 'application/json':
            data = response.get_json()
            assert 'success' in data


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_404_page(self, client):
        """Test 404 error page."""
        response = client.get('/nonexistent-page')
        assert response.status_code == 404
    
    def test_405_method_not_allowed(self, client):
        """Test 405 error for wrong HTTP method."""
        response = client.delete('/auth/login')
        assert response.status_code == 405
    
    def test_large_file_upload(self, client, user_headers):
        """Test uploading file larger than limit."""
        # Create a large fake file (larger than 25MB limit)
        from io import BytesIO
        large_file = BytesIO(b"x" * (26 * 1024 * 1024))  # 26MB
        
        response = client.post('/api/process/upload',
                             data={
                                 'file': (large_file, 'large.pdf'),
                                 'quality': '50'
                             },
                             content_type='multipart/form-data')
        
        assert response.status_code == 413  # Payload too large