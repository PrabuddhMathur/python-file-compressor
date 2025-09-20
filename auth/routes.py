from flask import request, jsonify, current_app, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash
from datetime import datetime
from . import auth
from .decorators import validate_json_request, handle_exceptions, log_api_access
from models import db
from models.user import User
from models.audit_log import AuditLog
import re

def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, "Password is valid"

# Template routes (GET)
@auth.route('/login', methods=['GET'])
def login_page():
    """Serve login form."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/login.html')

@auth.route('/register', methods=['GET'])
def register_page():
    """Serve registration form."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/register.html')

@auth.route('/register', methods=['POST'])
@handle_exceptions
def register():
    """User registration endpoint - handles both API and form requests."""
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data or 'full_name' not in data:
            return jsonify({
                'success': False,
                'message': 'Email, password, and full name are required'
            }), 400
        email = data['email'].lower().strip()
        password = data['password']
        full_name = data['full_name'].strip()
        is_api_request = True
    else:
        # Form submission
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        is_api_request = False
        
        if not email or not password or not full_name:
            flash('All fields are required.', 'error')
            return render_template('auth/register.html'), 400
    
    # Validate input
    if not validate_email(email):
        error_message = 'Invalid email format'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        else:
            flash(error_message, 'error')
            return render_template('auth/register.html'), 400
    
    is_valid, message = validate_password(password)
    if not is_valid:
        if is_api_request:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        else:
            flash(message, 'error')
            return render_template('auth/register.html'), 400
    
    if len(full_name) < 2:
        error_message = 'Full name must be at least 2 characters long'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        else:
            flash(error_message, 'error')
            return render_template('auth/register.html'), 400
    
    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        error_message = 'Email address already registered'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 409
        else:
            flash(error_message, 'error')
            return render_template('auth/register.html'), 409
    
    # Create new user (inactive by default)
    user = User(
        email=email,
        full_name=full_name,
        is_active=False,
        is_admin=False
    )
    user.set_password(password)
    
    try:
        db.session.add(user)
        db.session.commit()
        
        # Log registration
        AuditLog.log_registration(
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            email=email
        )
        
        success_message = 'Registration successful. Please wait for admin approval.'
        if is_api_request:
            return jsonify({
                'success': True,
                'message': success_message,
                'user_id': user.id
            }), 201
        else:
            flash(success_message, 'success')
            return render_template('auth/pending.html')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration failed: {e}")
        
        error_message = 'Registration failed. Please try again.'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 500
        else:
            flash(error_message, 'error')
            return render_template('auth/register.html'), 500

@auth.route('/login', methods=['POST'])
@handle_exceptions
def login():
    """User login endpoint - handles both API and form requests."""
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({
                'success': False,
                'message': 'Email and password are required'
            }), 400
        email = data['email'].lower().strip()
        password = data['password']
        is_api_request = True
    else:
        # Form submission
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        is_api_request = False
        
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('auth/login.html'), 400
    
    if not validate_email(email):
        if is_api_request:
            return jsonify({
                'success': False,
                'message': 'Invalid email format'
            }), 400
        else:
            flash('Invalid email format.', 'error')
            return render_template('auth/login.html'), 400
    
    # Find user
    user = User.query.filter_by(email=email).first()
    
    # Check credentials
    if not user or not user.check_password(password):
        # Log failed login attempt
        user_id = user.id if user else None
        AuditLog.log_login(
            user_id=user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            success=False
        )
        
        error_message = 'Invalid email or password'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 401
        else:
            flash(error_message, 'error')
            return render_template('auth/login.html'), 401
    
    # Check if user is active
    if not user.is_active:
        AuditLog.log_action(
            user_id=user.id,
            action='login_inactive_account',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        error_message = 'Account pending approval. Please contact administrator.'
        if is_api_request:
            return jsonify({
                'success': False,
                'message': error_message
            }), 403
        else:
            flash(error_message, 'warning')
            return render_template('auth/pending.html')
    
    # Login successful
    remember = request.form.get('remember-me') == 'on' if not is_api_request else data.get('remember', False)
    login_user(user, remember=remember)
    
    # Log successful login
    AuditLog.log_login(
        user_id=user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        success=True
    )
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    if is_api_request:
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'is_admin': user.is_admin
            }
        }), 200
    else:
        flash('Login successful!', 'success')
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('main.dashboard'))

@auth.route('/logout', methods=['GET', 'POST'])
@handle_exceptions
def logout():
    """User logout endpoint."""
    if current_user.is_authenticated:
        user_id = current_user.id
        
        # Log logout
        AuditLog.log_logout(
            user_id=user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        logout_user()
        
        # Handle both API and web requests
        if request.method == 'GET' or 'text/html' in request.headers.get('Accept', ''):
            flash('You have been logged out successfully.', 'success')
            return redirect(url_for('main.index'))
        else:
            return jsonify({
                'success': True,
                'message': 'Logout successful'
            }), 200
    else:
        if request.method == 'GET' or 'text/html' in request.headers.get('Accept', ''):
            return redirect(url_for('main.index'))
        else:
            return jsonify({
                'success': False,
                'message': 'No active session'
            }), 400

@auth.route('/status', methods=['GET'])
@handle_exceptions
def status():
    """Check authentication status."""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': current_user.id,
                'email': current_user.email,
                'full_name': current_user.full_name,
                'is_active': current_user.is_active,
                'is_admin': current_user.is_admin
            }
        }), 200
    else:
        return jsonify({
            'authenticated': False
        }), 200

@auth.route('/check-email', methods=['POST'])
@handle_exceptions
@validate_json_request(['email'])
def check_email():
    """Check if email is available for registration."""
    data = request.get_json()
    email = data['email'].lower().strip()
    
    if not validate_email(email):
        return jsonify({
            'available': False,
            'message': 'Invalid email format'
        }), 400
    
    existing_user = User.query.filter_by(email=email).first()
    
    if existing_user:
        return jsonify({
            'available': False,
            'message': 'Email address already registered'
        }), 200
    else:
        return jsonify({
            'available': True,
            'message': 'Email address available'
        }), 200

@auth.route('/validate-password', methods=['POST'])
@handle_exceptions
@validate_json_request(['password'])
def validate_password_endpoint():
    """Validate password strength."""
    data = request.get_json()
    password = data['password']
    
    is_valid, message = validate_password(password)
    
    return jsonify({
        'valid': is_valid,
        'message': message
    }), 200

# Error handlers for auth blueprint
@auth.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'message': 'Bad request'
    }), 400

@auth.errorhandler(401)
def unauthorized(error):
    return jsonify({
        'success': False,
        'message': 'Unauthorized access'
    }), 401

@auth.errorhandler(403)
def forbidden(error):
    return jsonify({
        'success': False,
        'message': 'Access forbidden'
    }), 403

@auth.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': 'Endpoint not found'
    }), 404

@auth.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify({
        'success': False,
        'message': 'Rate limit exceeded. Please try again later.'
    }), 429