import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 26214400))  # 25MB default
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'storage')
    
    # Security Configuration
    WTF_CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'true').lower() == 'true'
    SESSION_COOKIE_SECURE = os.environ.get('SECURE_COOKIES', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Rate Limiting Configuration
    RATE_LIMITS_ENABLED = os.environ.get('RATE_LIMITS_ENABLED', 'true').lower() == 'true'
    DAILY_FILE_LIMIT = int(os.environ.get('DAILY_FILE_LIMIT', 50))
    DAILY_STORAGE_LIMIT_MB = int(os.environ.get('DAILY_STORAGE_LIMIT_MB', 200))
    SESSION_STORAGE_LIMIT_MB = int(os.environ.get('SESSION_STORAGE_LIMIT_MB', 100))
    CONCURRENT_UPLOADS = int(os.environ.get('CONCURRENT_UPLOADS', 3))
    LOGIN_ATTEMPTS_PER_HOUR = int(os.environ.get('LOGIN_ATTEMPTS_PER_HOUR', 10))
    
    # Processing Configuration
    GHOSTSCRIPT_PATH = os.environ.get('GHOSTSCRIPT_PATH', '/usr/bin/gs')
    PROCESSING_TIMEOUT = int(os.environ.get('PROCESSING_TIMEOUT', 300))  # 5 minutes
    
    # Cleanup Configuration
    CLEANUP_ENABLED = os.environ.get('CLEANUP_ENABLED', 'true').lower() == 'true'
    FILE_RETENTION_HOURS = int(os.environ.get('FILE_RETENTION_HOURS', 24))
    
    # Quality Presets
    QUALITY_PRESETS = {
        # Legacy presets (still supported)
        'high': {
            'name': 'High Quality',
            'description': 'Minimal compression, best quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/printer',
                '-dColorImageResolution=300',
                '-dGrayImageResolution=300',
                '-dMonoImageResolution=1200',
            ],
            'expected_compression': 0.7  # 30% reduction
        },
        'medium': {
            'name': 'Medium Quality',
            'description': 'Balanced compression and quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/ebook',
                '-dColorImageResolution=150',
                '-dGrayImageResolution=150',
                '-dMonoImageResolution=600',
            ],
            'expected_compression': 0.4  # 60% reduction
        },
        'low': {
            'name': 'Low Quality',
            'description': 'Maximum compression, smallest size',
            'ghostscript_args': [
                '-dPDFSETTINGS=/screen',
                '-dColorImageResolution=72',
                '-dGrayImageResolution=72',
                '-dMonoImageResolution=300',
            ],
            'expected_compression': 0.2  # 80% reduction
        },
        
        # New percentage-based presets
        '20': {  # 20% reduction (80% of original size)
            'name': '20% Reduction (Minimal)',
            'description': 'Minimal compression, excellent quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/printer',
                '-dColorImageResolution=300',
                '-dGrayImageResolution=300',
                '-dMonoImageResolution=1200',
                '-dColorImageDownsampleType=/Bicubic',
                '-dGrayImageDownsampleType=/Bicubic',
            ],
            'expected_compression': 0.8  # 20% reduction
        },
        '30': {  # 30% reduction (70% of original size)
            'name': '30% Reduction',
            'description': 'Light compression, very good quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/printer',
                '-dColorImageResolution=250',
                '-dGrayImageResolution=250',
                '-dMonoImageResolution=1000',
            ],
            'expected_compression': 0.7  # 30% reduction
        },
        '40': {  # 40% reduction (60% of original size)
            'name': '40% Reduction',
            'description': 'Moderate compression, good quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/ebook',
                '-dColorImageResolution=200',
                '-dGrayImageResolution=200',
                '-dMonoImageResolution=800',
            ],
            'expected_compression': 0.6  # 40% reduction
        },
        '50': {  # 50% reduction (50% of original size)
            'name': '50% Reduction (Balanced)',
            'description': 'Balanced compression and quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/ebook',
                '-dColorImageResolution=150',
                '-dGrayImageResolution=150',
                '-dMonoImageResolution=600',
            ],
            'expected_compression': 0.5  # 50% reduction
        },
        '60': {  # 60% reduction (40% of original size)
            'name': '60% Reduction',
            'description': 'Strong compression, fair quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/screen',
                '-dColorImageResolution=120',
                '-dGrayImageResolution=120',
                '-dMonoImageResolution=400',
            ],
            'expected_compression': 0.4  # 60% reduction
        },
        '70': {  # 70% reduction (30% of original size)
            'name': '70% Reduction (Maximum)',
            'description': 'Maximum compression, basic quality',
            'ghostscript_args': [
                '-dPDFSETTINGS=/screen',
                '-dColorImageResolution=96',
                '-dGrayImageResolution=96',
                '-dMonoImageResolution=300',
            ],
            'expected_compression': 0.3  # 70% reduction
        }
    }

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///app_dev.db'

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}