import os
import re
from werkzeug.utils import secure_filename

# Optional imports
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class FileValidator:
    """File validation utilities."""
    
    # Allowed file extensions and MIME types for PDF files
    ALLOWED_EXTENSIONS = {'pdf'}
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'application/x-pdf',
    }
    
    # PDF magic bytes (file signatures)
    PDF_SIGNATURES = [
        b'%PDF-',  # Standard PDF signature
    ]
    
    def __init__(self, max_file_size=None):
        """Initialize file validator with optional max file size."""
        self.max_file_size = max_file_size or (25 * 1024 * 1024)  # 25MB default
    
    def validate_file(self, file, filename=None):
        """Comprehensive file validation."""
        if not file:
            return False, "No file provided"
        
        # Use provided filename or get from file object
        filename = filename or getattr(file, 'filename', None)
        if not filename:
            return False, "No filename provided"
        
        # Check filename
        is_valid, message = self.validate_filename(filename)
        if not is_valid:
            return False, message
        
        # Check file size
        is_valid, message = self.validate_file_size(file)
        if not is_valid:
            return False, message
        
        # Check file content
        is_valid, message = self.validate_file_content(file)
        if not is_valid:
            return False, message
        
        return True, "File validation passed"
    
    def validate_filename(self, filename):
        """Validate filename."""
        if not filename:
            return False, "Filename is empty"
        
        # Check for dangerous characters
        dangerous_chars = ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*', '\0']
        for char in dangerous_chars:
            if char in filename:
                return False, f"Filename contains invalid character: {char}"
        
        # Check extension
        if '.' not in filename:
            return False, "File must have an extension"
        
        extension = filename.rsplit('.', 1)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            return False, f"File type .{extension} not allowed. Only PDF files are accepted."
        
        # Check filename length
        if len(filename) > 255:
            return False, "Filename too long (max 255 characters)"
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'\.\.', r'/', r'\\', r'<', r'>', r'\|', r'\?', r'\*',
            r'CON', r'PRN', r'AUX', r'NUL',  # Windows reserved names
            r'COM[1-9]', r'LPT[1-9]'
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                return False, f"Filename contains suspicious pattern"
        
        return True, "Filename is valid"
    
    def validate_file_size(self, file):
        """Validate file size."""
        # Seek to end to get file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        if file_size == 0:
            return False, "File is empty"
        
        if file_size > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            current_mb = file_size / (1024 * 1024)
            return False, f"File size ({current_mb:.1f}MB) exceeds maximum allowed size ({max_mb:.0f}MB)"
        
        return True, f"File size is valid ({file_size} bytes)"
    
    def validate_file_content(self, file):
        """Validate file content to ensure it's actually a PDF."""
        # Read first few bytes to check file signature
        file.seek(0)
        header = file.read(1024)  # Read first 1KB
        file.seek(0)  # Reset file pointer
        
        if not header:
            return False, "File appears to be empty"
        
        # Check PDF signature
        is_pdf = False
        for signature in self.PDF_SIGNATURES:
            if header.startswith(signature):
                is_pdf = True
                break
        
        if not is_pdf:
            return False, "File does not appear to be a valid PDF (invalid file signature)"
        
        # Try to use python-magic if available for MIME type detection
        if MAGIC_AVAILABLE:
            try:
                file.seek(0)
                mime_type = magic.from_buffer(file.read(1024), mime=True)
                file.seek(0)
                
                if mime_type not in self.ALLOWED_MIME_TYPES:
                    return False, f"File MIME type '{mime_type}' not allowed"
            except Exception as e:
                # Error in magic detection, but don't fail validation
                pass
        
        # Additional PDF structure validation
        file.seek(0)
        content = file.read(8192)  # Read first 8KB
        file.seek(0)
        
        # Check for essential PDF elements
        if b'%PDF-' not in content:
            return False, "File does not contain PDF header"
        
        # Look for PDF version
        pdf_version_match = re.search(br'%PDF-(\d+\.\d+)', content)
        if pdf_version_match:
            version = pdf_version_match.group(1).decode('ascii')
            # Accept PDF versions 1.0 to 2.0
            if not re.match(r'^[12]\.\d$', version):
                return False, f"Unsupported PDF version: {version}"
        
        return True, "PDF file content validation passed"
    
    def get_file_info(self, file, filename=None):
        """Get information about the file."""
        filename = filename or getattr(file, 'filename', 'unknown')
        
        # Get file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        # Get file extension
        extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # Read header for PDF version
        header = file.read(1024)
        file.seek(0)
        
        pdf_version = "Unknown"
        pdf_version_match = re.search(br'%PDF-(\d+\.\d+)', header)
        if pdf_version_match:
            pdf_version = pdf_version_match.group(1).decode('ascii')
        
        return {
            'filename': filename,
            'size': file_size,
            'size_mb': round(file_size / (1024 * 1024), 2),
            'extension': extension,
            'pdf_version': pdf_version
        }

class InputValidator:
    """Input validation utilities."""
    
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    PASSWORD_MIN_LENGTH = 8
    NAME_MIN_LENGTH = 2
    NAME_MAX_LENGTH = 100
    
    @staticmethod
    def validate_email(email):
        """Validate email address format."""
        if not email:
            return False, "Email is required"
        
        if len(email) > 254:  # RFC 5321 limit
            return False, "Email address too long"
        
        if not InputValidator.EMAIL_PATTERN.match(email):
            return False, "Invalid email format"
        
        # Check for consecutive periods
        if '..' in email:
            return False, "Email cannot contain consecutive periods"
        
        # Check local part length
        local_part = email.split('@')[0]
        if len(local_part) > 64:  # RFC 5321 limit
            return False, "Email local part too long"
        
        return True, "Email is valid"
    
    @staticmethod
    def validate_password(password):
        """Validate password strength."""
        if not password:
            return False, "Password is required"
        
        if len(password) < InputValidator.PASSWORD_MIN_LENGTH:
            return False, f"Password must be at least {InputValidator.PASSWORD_MIN_LENGTH} characters long"
        
        if len(password) > 128:
            return False, "Password too long (max 128 characters)"
        
        # Check for at least one letter
        if not re.search(r'[A-Za-z]', password):
            return False, "Password must contain at least one letter"
        
        # Check for at least one digit
        if not re.search(r'\d', password):
            return False, "Password must contain at least one number"
        
        # Check for at least one special character (optional but recommended)
        # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        #     return False, "Password should contain at least one special character"
        
        # Check for common weak passwords
        weak_passwords = [
            'password', '12345678', 'qwerty123', 'abc12345',
            'password123', '12345abc', 'letmein123'
        ]
        
        if password.lower() in weak_passwords:
            return False, "Password is too common, please choose a stronger password"
        
        return True, "Password is strong"
    
    @staticmethod
    def validate_name(name, field_name="Name"):
        """Validate name fields."""
        if not name:
            return False, f"{field_name} is required"
        
        name = name.strip()
        
        if len(name) < InputValidator.NAME_MIN_LENGTH:
            return False, f"{field_name} must be at least {InputValidator.NAME_MIN_LENGTH} characters long"
        
        if len(name) > InputValidator.NAME_MAX_LENGTH:
            return False, f"{field_name} must be less than {InputValidator.NAME_MAX_LENGTH} characters"
        
        # Check for valid characters (letters, spaces, hyphens, apostrophes)
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", name):
            return False, f"{field_name} can only contain letters, spaces, hyphens, apostrophes, and periods"
        
        # Check for suspicious patterns
        if re.search(r'[<>{}()[\]|\\]', name):
            return False, f"{field_name} contains invalid characters"
        
        return True, f"{field_name} is valid"
    
    @staticmethod
    def validate_quality_preset(quality):
        """Validate quality preset selection."""
        # Support both old presets and new percentage values
        valid_presets = ['high', 'medium', 'low']
        valid_percentages = [20, 30, 40, 50, 60, 70]
        
        if not quality:
            return False, "Quality preset is required"
        
        # Try to convert to integer (percentage)
        try:
            quality_int = int(quality)
            if quality_int in valid_percentages:
                return True, "Quality preset is valid"
            else:
                return False, f"Invalid quality percentage. Must be one of: {', '.join(map(str, valid_percentages))}%"
        except (ValueError, TypeError):
            # If not a number, check if it's a valid preset name
            if quality in valid_presets:
                return True, "Quality preset is valid"
            else:
                return False, f"Invalid quality preset. Must be percentage (20-70%) or one of: {', '.join(valid_presets)}"
    
    @staticmethod
    def validate_integer(value, field_name, min_val=None, max_val=None):
        """Validate integer fields."""
        if value is None:
            return False, f"{field_name} is required"
        
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            return False, f"{field_name} must be a valid integer"
        
        if min_val is not None and int_value < min_val:
            return False, f"{field_name} must be at least {min_val}"
        
        if max_val is not None and int_value > max_val:
            return False, f"{field_name} must be at most {max_val}"
        
        return True, f"{field_name} is valid"
    
    @staticmethod
    def sanitize_string(input_string, max_length=None):
        """Sanitize string input."""
        if not input_string:
            return ""
        
        # Strip whitespace
        sanitized = input_string.strip()
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Remove control characters except newlines and tabs
        sanitized = ''.join(char for char in sanitized 
                          if ord(char) >= 32 or char in '\n\t')
        
        # Truncate if max_length specified
        if max_length and len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized
    
    @staticmethod
    def validate_json_data(data, required_fields=None, optional_fields=None):
        """Validate JSON data structure."""
        if not isinstance(data, dict):
            return False, "Data must be a JSON object"
        
        # Check required fields
        if required_fields:
            missing_fields = []
            for field in required_fields:
                if field not in data or data[field] is None or data[field] == '':
                    missing_fields.append(field)
            
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"
        
        # Check for unexpected fields
        if required_fields or optional_fields:
            allowed_fields = set(required_fields or []) | set(optional_fields or [])
            unexpected_fields = set(data.keys()) - allowed_fields
            
            if unexpected_fields:
                return False, f"Unexpected fields: {', '.join(unexpected_fields)}"
        
        return True, "JSON data is valid"
    
    @staticmethod
    def validate_file_path(file_path):
        """Validate file path for security."""
        if not file_path:
            return False, "File path is required"
        
        # Check for path traversal attempts
        dangerous_patterns = ['../', '..\\', '/.', '\\.', '//', '\\\\']
        
        for pattern in dangerous_patterns:
            if pattern in file_path:
                return False, f"File path contains dangerous pattern: {pattern}"
        
        # Check for absolute paths (should be relative)
        if os.path.isabs(file_path):
            return False, "File path must be relative"
        
        # Check length
        if len(file_path) > 500:
            return False, "File path too long"
        
        return True, "File path is valid"