from fileinput import filename
from importlib.resources import files
import os
from flask import Blueprint, app, render_template, request, redirect, send_from_directory, url_for, flash, session, current_app, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from wtforms import ValidationError
from .models import AuditLog, File, ShareFile, User, db
from datetime import datetime, timedelta
import random 
from flask_mail import Mail, Message
from pypdf import PdfReader

ALLOWED_FILE_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx']
auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

@auth.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    print(f"DEBUG: Received data: {data}")  # Add this line
    email = data.get('email')
    username = data.get('username')

    if not email or not username:
        return jsonify({'success': False, 'message': 'Email and username are required'})
    
    # Checking if the username is already taken
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username is already taken'})
    
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email is already registered'})
    
    otp = random.randint(100000, 999999)
    expire_time = str(datetime.utcnow() + timedelta(minutes=10))
    session['reg_otp'] = {
        'email': email,
        'username': username,
        'otp': otp,
        'expire_time': expire_time
    }
    try:
        mail = current_app.extensions.get('mail')
        # if not mail:
        #     return jsonify({'success': False, 'message': 'Mail service not configured'})
        msg = Message(
            'Your OTP Verification Code',
            sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@yourdomain.com'),
            recipients=[email]
        )
        msg.body = f'Your verification code is: {otp}\nThis code will expire in 10 minutes.'
        mail.send(msg)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@main.route('/dashboard')
def index():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    """Home page - shows after login"""
    user = User.query.get(user_id)
    username = User.query.with_entities(User.username).filter_by(id=user_id).first().username
    logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(20).all()

    # Create response with no-cache headers
    response = make_response(render_template('dashboard.html', user=user, username=username, logs=logs))
    
    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response
    #return render_template('dashboard.html', user=user, username=username, logs=logs)

@main.route('/admin_dashboard')
def admin():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    if user_id and not session.get('is_admin'):
        flash('Access denied: Admins only', 'danger')
        log = auditlog(
            user_id=session['user_id'],
            action_type='login attempt',
            details='Unauthorized admin dashboard access attempt',
            status='failed'
        )
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('auth.login'))
    
    """Admin dashboard - shows after admin login"""
    admin_logs = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(20).all()
    registered_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    return render_template('admin_dashboard.html', registered_users=registered_users, logs=admin_logs)


@main.route('/files', methods=['GET'])
def view_files():
    """View all uploaded files"""
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    current_user = User.query.get(user_id)
    current_user_fullname = current_user.fullname
    files = File.query.filter_by(user_id=user_id).order_by(File.upload_time.desc()).all()
    shared_files_data = ShareFile.query.filter(ShareFile.shared_with_user_id == user_id).order_by(ShareFile.shared_at.desc()).all()
    shared_files = []
    for share in shared_files_data:
        file = File.query.get(share.file_id)
        if file:
            shared_files.append(file)
            
    for file in files:
        file.uploaded_by_username = current_user_fullname
    for file in shared_files:
        file.uploaded_by_username = User.query.get(file.user_id).username

    return render_template('files.html', files=files, shared_files=shared_files)

@main.route('/view_file/<int:file_id>', methods=['GET'])
def view_file(file_id):
    """View a specific file's details"""
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    file = File.query.get(file_id)
    
    if not file:
        flash('File not found.', 'danger')
        return redirect(url_for('main.view_files'))
    
    if file.user_id != user_id:
        shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()
        if not shared_file:
            flash('Access denied.', 'danger')
            return redirect(url_for('main.view_files'))
    
    if file.filetype not in ALLOWED_FILE_EXTENSIONS:
        flash('Cannot display this file type.', 'warning')
        return redirect(url_for('main.view_files'))
    
    log = auditlog(
        user_id=session['user_id'],
        action_type='view file',
        details=f'Viewed file ID: {file_id}, filename: {file.original_filename}'
    )
    db.session.add(log)
    db.session.commit()
    
    
    if file.filetype == '.txt':
        if hasattr(file, 'filepath') and os.path.exists(file.filepath):
            with open(file.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
        return render_template('view_file.html', file=file, file_id=file_id, content=file_content)

    return render_template('view_file.html', file=file, file_id=file_id)

@main.route('/serve_file/<int:file_id>', methods=['GET'])
def serve_file(file_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    file = File.query.get(file_id)
    if not file:
        flash('File not found.', 'danger')
        return redirect(url_for('main.view_files'))
    if file.user_id != user_id:
        shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()
        if not shared_file:
            flash('Access denied.', 'danger')
            return redirect(url_for('main.view_files'))
    
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)

    if not os.path.exists(file_path):
        # flash('File not found.', 'danger')
        # return redirect(url_for('main.view_files'))
        print(f"File not found at path: {file_path}")  # Debug logging
        flash('File not found on server.', 'danger')
        return redirect(url_for('main.view_files'))
    try:
        if file.filetype == '.pdf':
            return send_from_directory(current_app.config['UPLOAD_FOLDER'], file.filename, as_attachment=False, mimetype='application/pdf')
        else:
            return send_from_directory(current_app.config['UPLOAD_FOLDER'], file.filename, as_attachment=True)
    except Exception as e:
        print(f"Error serving file: {e}")
        flash(f'Error serving file: {str(e)}', 'danger')
        return redirect(url_for('main.view_files'))

@main.route('/edit_file/<int:file_id>', methods=['GET', 'POST'])
def edit_file(file_id):

    file = File.query.get(file_id)

    log = auditlog(
        user_id=session['user_id'],
        action_type='edit file',
        details=f'Edited file ID: {file_id}, filename: {file.original_filename}'
    )
    db.session.add(log)
    db.session.commit()

    return render_template('edit_file.html', file_id=file_id)

@main.route('/delete_file/<int:file_id>', methods=['GET', 'POST'])
def delete_file(file_id):
    file = File.query.get(file_id)
    if file:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        if os.path.exists(filepath):
            os.remove(filepath)

            db.session.delete(file)
            log = auditlog(
                user_id=session['user_id'],
                action_type='delete file',
                details=f'Deleted file ID: {file_id}, filename: {file.original_filename}'
            )
            db.session.add(log)
            db.session.commit()

            flash(f'File "{file.filename}" deleted successfully.', 'success')
    return redirect(url_for('main.view_files'))
    

@main.route('/share', methods=['POST'])
def share_file():
    file_id = request.form.get('file_id')
    file = File.query.get(file_id)
    
    if file:
        try:
            shared_with = request.form.get('shared_with')
            shared_with_user = User.query.filter_by(username=shared_with).first() if shared_with else None
            shared_with_user_id = shared_with_user.id if shared_with_user else None
            description = request.form.get('description')
            if not shared_with_user_id:
                flash('User to share with not found.', 'danger')
                return redirect(url_for('main.view_files'))
            else:
                file.shared_with_user_id = shared_with_user_id
                file.shared_by_user_id = session['user_id']
                description = description or ''
                
                share_file = ShareFile( #Add entry to ShareFile table
                    file_id=file_id,
                    shared_with_user_id=shared_with_user_id,
                    shared_by_user_id=session['user_id'],
                    description=description,
                    shared_at=datetime.utcnow()
                )
                db.session.add(share_file)
                print(f"✓ ShareFile entry added to session")

                log = auditlog( #Log the sharing action
                    user_id=session['user_id'],
                    action_type='share file',
                    details=f'Shared file ID: {file_id}, filename: {file.original_filename} with users: {shared_with}'
                )
                db.session.add(log)
                print(f"✓ AuditLog entry added to session")

                print(f"Attempting to commit...")
                db.session.commit()
                print(f"✓ Session committed successfully.")

                flash(f'File "{file.original_filename}" shared successfully with {shared_with}.', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            flash(f'Error sharing file: {str(e)}', 'danger')
            return redirect(url_for('main.index'))
        
    
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
            shared_with_user = User.query.filter_by(username=shared_with).first() if shared_with else None
            shared_with_user_id = shared_with_user.id if shared_with_user else None

            original_filename = file.filename

            def get_file_extension(filename):
                """Extract file extension including the dot"""
                if '.' in filename:
                    return '.' + filename.rsplit('.', 1)[1].lower()
                return ''
            
            filetype = get_file_extension(original_filename)

            if filetype not in ALLOWED_FILE_EXTENSIONS:
                flash('File type not allowed. Please upload a valid file.', 'danger')
                return render_template('uploadfile.html', shared_with=shared_with, description=description)
            
            if not shared_with:
                flash('Please specify at least one user to share the file with.', 'danger')
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                return render_template('uploadfile.html', shared_with=shared_with, 
                                       description=description)
            # Create unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            user_id = session.get('user_id')
            unique_filename = f"{user_id}_{timestamp}_{original_filename}"

            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))

            #Read file data
            file_size = os.path.getsize(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))

            if file_size > 16 * 1024 * 1024:  # 16 MB limit
                flash('File size exceeds the 16 MB limit. Please upload a smaller file.', 'danger')
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='upload',
                    details='Failed file upload - file too large: ' + original_filename,
                    status='failed'
                )
                db.session.add(log)
                db.session.commit()
                return render_template('uploadfile.html', shared_with=shared_with, 
                                       description=description)
            
              
            else:
                new_file = File(
                    user_id=user_id,
                    filename=unique_filename,
                    original_filename=original_filename,
                    filepath= os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename),
                    filetype=filetype,
                    file_size=file_size,  # Placeholder for file size
                    description=description,
                    shared_with=shared_with,
                    status='pending',
                    sensitivity=5,
                    action='no action'
                )
                db.session.add(new_file)
                db.session.flush()  # Get new_file.file_id before commit

                share_file = ShareFile( #Add entry to ShareFile table
                    file_id=new_file.file_id,
                    shared_with_user_id=shared_with_user_id,
                    shared_by_user_id=session['user_id'],
                    description=description,
                    shared_at=datetime.utcnow()
                )
                db.session.add(share_file)

                # Logging the upload event
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='upload',
                    details='Successful file upload: ' + original_filename
                )
                db.session.add(log)

                log2 = auditlog( #Log the sharing action
                    user_id=session['user_id'],
                    action_type='share file',
                    details=f'Shared file ID: {new_file.file_id}, filename: {original_filename} with users: {shared_with}'
                )
                db.session.add(log2)
                db.session.commit()
        
                flash(f'File "{original_filename}" uploaded successfully!', 'success')
                return redirect(url_for('main.index'))
        
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
        
        elif user and user.check_password(password) == False:
            log = auditlog(
                user_id=user.id,
                action_type='login attempt',
                details='Failed login attempt for username: ' + username,
                status='failed'
            )
            db.session.add(log)
            db.session.commit()
            flash('Invalid username or password', 'danger')
            return render_template('login.html', username=username)
        
        else:
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login successful!', 'success')

            if user.is_admin:
                # Logging the login event for admin
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='admin login',
                    details='Successful login attempt'
                )
                db.session.add(log)
                db.session.commit()

                return redirect('/admin_dashboard')  # Or your admin route

            else:
                # Logging the login event for regular user
                log = auditlog(
                    user_id=session['user_id'],
                    action_type='login',
                    details='Successful login attempt'
                )
                db.session.add(log)
                db.session.commit()
                return redirect(url_for('main.index'))  # Regular user dashboard
        
    
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
                        
            # Checking and confirm password match
            if password != confirm_password:
                raise ValidationError('Passwords do not match.')
            
            # Checking if full name is filled in 
            if fullname is None or fullname.strip() == '':
                raise ValidationError('Please fill in your full name.')
            
            # Checking if position is filled in correctly
            if position is None or position.strip() == '':
                raise ValidationError('Please fill in your position.')
            
            if position not in ['Employee', 'Manager']:
                raise ValidationError('Invalid position. Please choose a valid position.')
            
            # Checking if the username is already taken
            if User.query.filter_by(username=username).first():
                raise ValidationError('Username is already taken. Please choose a different one.')
                #return render_template('register.html', username=username, email=email)
            
            # Checking if the email is already registered
            if User.query.filter_by(email=email).first():
                raise ValidationError('Email is already registered. Please choose a different one.')
                #return render_template('register.html', username=username, email=email)
            
            # OTP verification

            reg_otp = session.get('reg_otp', {})
            stored_otp = reg_otp.get('otp')
            stored_expire_time = reg_otp.get('expire_time')
            stored_username = reg_otp.get('username')
            stored_email = reg_otp.get('email')

            if not stored_otp or not stored_expire_time or email != stored_email or username != stored_username:
                raise ValidationError('Invalid OTP or mismatched email/username. Please request a new OTP.')
            
            if datetime.utcnow() > datetime.fromisoformat(stored_expire_time):
                raise ValidationError('The OTP you filled in has expired. Please request for a new OTP.')
            
            if str(stored_otp) != str(request.form.get('otp')):
                raise ValidationError('Incorrect OTP. Please try again.')
                
            # Creating a new user
            new_user = User(
                fullname=fullname, 
                username=username, 
                email=email, 
                position=position,
                otp =str(stored_otp),
                otp_expiry=datetime.fromisoformat(stored_expire_time),
                is_admin=False
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
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit_logs.html', logs=logs)