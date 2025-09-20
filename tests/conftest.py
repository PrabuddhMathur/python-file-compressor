# Test configuration and utilities

import os
import tempfile
import pytest
from app import create_app
from models import db
from models.user import User
from models.processing_job import ProcessingJob
from models.audit_log import AuditLog


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app('testing')
    
    # Override specific test configurations
    app.config.update({
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'UPLOAD_FOLDER': tempfile.mkdtemp(),
    })

    with app.app_context():
        db.create_all()
        
        # Create a test admin user
        admin_user = User(
            email='admin@test.com',
            full_name='Test Admin',
            is_active=True,
            is_admin=True
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        
        # Create a test regular user
        regular_user = User(
            email='user@test.com',
            full_name='Test User',
            is_active=True,
            is_admin=False
        )
        regular_user.set_password('user123')
        db.session.add(regular_user)
        
        # Create a pending user
        pending_user = User(
            email='pending@test.com',
            full_name='Pending User',
            is_active=False,
            is_admin=False
        )
        pending_user.set_password('pending123')
        db.session.add(pending_user)
        
        db.session.commit()

    yield app

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """A test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the Flask application's CLI commands."""
    return app.test_cli_runner()


@pytest.fixture
def admin_user(app):
    """Get the test admin user."""
    with app.app_context():
        return User.query.filter_by(email='admin@test.com').first()


@pytest.fixture
def regular_user(app):
    """Get the test regular user."""
    with app.app_context():
        return User.query.filter_by(email='user@test.com').first()


@pytest.fixture
def pending_user(app):
    """Get the test pending user."""
    with app.app_context():
        return User.query.filter_by(email='pending@test.com').first()


@pytest.fixture
def admin_headers(client, admin_user):
    """Login as admin and return headers with session."""
    response = client.post('/auth/login', data={
        'email': 'admin@test.com',
        'password': 'admin123'
    })
    assert response.status_code == 302  # Redirect after successful login
    return {}


@pytest.fixture
def user_headers(client, regular_user):
    """Login as regular user and return headers with session."""
    response = client.post('/auth/login', data={
        'email': 'user@test.com',
        'password': 'user123'
    })
    assert response.status_code == 302  # Redirect after successful login
    return {}


@pytest.fixture
def sample_pdf():
    """Create a sample PDF file for testing."""
    # This would create a minimal PDF file
    # For now, we'll return a mock file-like object
    import io
    
    # Simple PDF header - this is a minimal valid PDF
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Hello World) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000204 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
297
%%EOF"""
    
    return io.BytesIO(pdf_content)


def create_test_file(filename, content=b"test content", size=None):
    """Create a temporary test file."""
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, filename)
    
    if size:
        content = b"x" * size
    
    with open(file_path, 'wb') as f:
        f.write(content)
    
    return file_path


def cleanup_test_files(*paths):
    """Clean up test files and directories."""
    for path in paths:
        if os.path.exists(path):
            if os.path.isfile(path):
                os.unlink(path)
            else:
                import shutil
                shutil.rmtree(path, ignore_errors=True)
