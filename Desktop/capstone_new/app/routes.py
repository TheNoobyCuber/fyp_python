import email
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy.exc import SQLAlchemyError
from wtforms import ValidationError
# from app import AuditLog
from .models import AuditLog, File, User, db
from datetime import datetime
import time
import random

ALLOWED_FILE_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx']
auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

@main.route('/dashboard')
def index():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    """Home page - shows after login"""
    user = User.query.get(user_id)
    username = User.query.with_entities(User.username).filter_by(id=user_id).first().username
    logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(20).all()
    return render_template('dashboard.html', user=user, username=username, logs=logs)

@main.route('/admin_dashboard')
def admin():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    if user_id and not session.get('is_admin'):
        flash('Access denied: Admins only', 'danger')
        return redirect(url_for('auth.login'))
    
    """Admin dashboard - shows after admin login"""
    logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(20).all()
    return render_template('admin_dashboard.html')

@main.route('/files')
def view_files():
    """View all uploaded files"""
    return render_template('files.html')

@main.route('/upload', methods=['GET', 'POST'])
def upload():
    try:   
        if request.method == 'POST':
            file = request.files['file']
            if file.filename == '':
                flash('No selected file. Please choose a file to upload.', 'danger')
                return render_template('uploadfile.html')
            description = request.form.get('description')
            shared_with = request.form.get('shared_with')  # Comma-separated user IDs

            original_filename = file.filename

            def get_file_extension(filename):
                """Extract file extension including the dot"""
                if '.' in original_filename:
                    return '.' + filename.rsplit('.', 1)[1].lower()
                return ''
            
            filetype = get_file_extension(original_filename)

            if filetype not in ALLOWED_FILE_EXTENSIONS:
                flash('File type not allowed. Please upload a valid file.', 'danger')
                return render_template('uploadfile.html', shared_with=shared_with, description=description)
            
            # Create unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            user_id = session.get('user_id')
            unique_filename = f"{user_id}_{timestamp}_{original_filename}"

            new_file = File(
                user_id=user_id,
                filename=unique_filename,
                original_filename=original_filename,
                filetype=filetype,
                file_size=0,  # Placeholder for file size
                description=description,
                shared_with=shared_with,
                status='pending',
                sensitivity=5,
                action='no action'
            )
            db.session.add(new_file)
            db.session.commit()

            # Logging the registration event
            log = auditlog(
                user_id=session['user_id'],
                action_type='upload',
                details='Successful file upload: ' + original_filename
            )
            db.session.add(log)
            db.session.commit()
    
            print(f"File {original_filename} uploaded by user {user_id}")
            flash(f'File "{original_filename}" uploaded successfully!', 'success')
            return redirect(url_for('main.view_files'))
    
    except Exception as e:
            print(f"\n=== DEBUG: ERROR ===")
            print(f"Error: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            
            db.session.rollback()
            flash(f'Error uploading file: {str(e)}', 'danger')
            return redirect(request.url)

    """Upload file page"""
    return render_template('uploadfile.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        #remember = request.form.get('remember')
        
        if not username:
            flash('Please enter your username', 'danger')
            return render_template('login.html', username=username)
        if not password:
            flash('Please enter your password', 'danger')
            return render_template('login.html', username=username)
        
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Invalid username or password', 'danger')
            return render_template('login.html', username=username)
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login successful!', 'success')

            if user.is_admin:

                # Logging the registration event
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='admin login',
                    details='Successful login attempt'
                )
                db.session.add(log)
                db.session.commit()

                return redirect('/admin_dashboard')  # Or your admin route

            else:
                # Logging the registration event
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='login',
                    details='Successful login attempt'
                )
                db.session.add(log)
                db.session.commit()
                return redirect(url_for('main.index'))  # Regular user dashboard
        else:
            flash('Invalid username or password', 'danger')
            return render_template('login.html', username=username)
        
    
    return render_template('login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            fullname = request.form.get('fullname')
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            position = request.form.get('position')
            #otp = request.form.get('otp')
                        
            # Checking and confirm password match
            if password != confirm_password:
                raise ValidationError('Passwords do not match.')
            
            # Checking if full name is filled in 
            if fullname is None or fullname.strip() == '':
                raise ValidationError('Please fill in your full name.')
            
            # Checking if position is filled in correctly
            if position is None or position.strip() == '':
                raise ValidationError('Please fill in your position.')
            
            if position not in ['Employee', 'Manager', 'Admin']:
                raise ValidationError('Invalid position. Please choose a valid position.')
            
            # Checking if the username is already taken
            if User.query.filter_by(username=username).first():
                raise ValidationError('Username is already taken. Please choose a different one.')
                #return render_template('register.html', username=username, email=email)
            
            # Checking if the email is already registered
            if User.query.filter_by(email=email).first():
                raise ValidationError('Email is already registered. Please choose a different one.')
                #return render_template('register.html', username=username, email=email)
            
            # Creating a new user
            new_user = User(
                fullname=fullname, 
                username=username, 
                email=email, 
                position=position,
                is_admin=True if position == 'Admin' else False
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.flush()  # Get new_user.id before commit

            user_id = new_user.id

            # Logging the registration event
            log = auditlog(
                user_id=user_id,
                action_type='register',
                details='New user registration with email verification'
            )
            db.session.add(log)
            db.session.commit()
            
            # Clearing the OTP session data
            # session.pop('registration_otp', None)
            
            flash('Account created successfully! You can now login.', 'success')
            return redirect(url_for('auth.login'))
        
        return render_template('login.html')

    except Exception as e:
        print(f"ERROR in register: {type(e).__name__}: {e}")
        flash(f'Registration failed: {str(e)}', 'danger')
        return render_template('register.html', 
                            username=username or '', 
                            email=email or '')
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error: {e}")
        flash(f'Database error: {str(e)[:100]}', 'danger')
        return render_template('register.html')
    
@auth.route('/logout')
def logout():
    # Logging the logout event
    log = auditlog(
        user_id=session['user_id'],
        action_type='logout',
        details='Successful logout attempt'
    )
    db.session.add(log)
    db.session.commit()
    
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

def auditlog(user_id, action_type, details='', status='success'):
    """Helper function to log audit events"""
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action_type=action_type,
            details=details,
            status=status,
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)
        return log_entry
    except Exception as e:
        print(f"Failed to log audit event: {e}")
        db.session.rollback()

@main.route('/view_audit_logs')
def view_audit_logs():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit_logs.html', user=user, logs=logs)