import base64
from fileinput import filename
from importlib.resources import files
import os
from urllib import response
from flask import Blueprint, app, render_template, request, redirect, send_from_directory, url_for, flash, session, current_app, jsonify, make_response
from flask_sqlalchemy import query
from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError
from wtforms import ValidationError
from .models import AuditLog, File, RecycleBin, ShareFile, User, Watermark, db
from datetime import datetime, timedelta
import random 
from flask_mail import Mail, Message
import pymupdf
from PIL import Image, ImageDraw, ImageFont
import pathlib
import PyPDF2
import json
import socket
from pikepdf import Pdf, Name, String, Dictionary, Array, Stream

ALLOWED_FILE_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx']
auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

def generate_prng():
    raw_key_string = os.urandom(32) # Generate a 256-bit random key
    key_string = base64.b64encode(raw_key_string).decode('utf-8')  # Encode the key in base64 for storage
    return key_string

def generate_salt():
    return os.urandom(16)  # Generate a 128-bit random salt

def encrypt_file_data(file_data, key=None):
    if key is None:
        key = generate_prng()  # Generate a new key if not provided
    elif isinstance(key, str):
        key = key.encode('utf-8') # Convert string key back to bytes
    
    var = Fernet(key)
    encrypted_data = var.encrypt(file_data)
    return encrypted_data, key

def decrypt_file_data(encrypted_data, key):
    if isinstance(key, str):
        key = key.encode('utf-8') # Convert string key back to bytes
    else:
        key = key

    ciphertext = Fernet(key)
    decrypted_data = ciphertext.decrypt(encrypted_data)
    return decrypted_data

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
        if file.status != 'recycle_bin':
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
    
    key = file.key
    raw_data = decrypt_file_data(file.fileData, key)  # Decrypt file data to ensure key is correct and file is accessible

    
    log = auditlog(
        user_id=session['user_id'],
        action_type='view file',
        details=f'Viewed file ID: {file_id}, filename: {file.original_filename}'
    )
    db.session.add(log)
    db.session.commit()
    
    
    if file.filetype == '.txt':
        decrypted_content = decrypt_file_data(file.fileData, file.key).decode('utf-8') # Assuming the original file is UTF-8 encoded text
        return render_template('view_file.html', file=file, file_id=file_id, content=decrypted_content)

    return render_template('view_file.html', file=file, file_id=file_id, content=raw_data)

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
    
    raw_data = decrypt_file_data(file.fileData, file.key)  # Decrypt file data to ensure key is correct and file is accessible

    file_response = make_response(raw_data)
    try:
        if file.filetype == '.pdf':
            file_response.mimetype = 'application/pdf'
            file_response.headers['Content-Disposition'] = f'inline; filename="{file.original_filename}"'
        else:
            file_response.mimetype = 'application/octet-stream'
            file_response.headers['Content-Disposition'] = f'attachment; filename="{file.original_filename}"'
        
        file_response.headers['Content-Length'] = len(raw_data)
        
        return file_response
        #     return send_from_directory(current_app.config['UPLOAD_FOLDER'], file.filename, as_attachment=False, mimetype='application/pdf')
        # else:
        #     return send_from_directory(current_app.config['UPLOAD_FOLDER'], file.filename, as_attachment=True)
    except Exception as e:
        print(f"Error serving file: {e}")
        flash(f'Error serving file: {str(e)}', 'danger')
        return redirect(url_for('main.view_files'))

@main.route('/edit_file/<int:file_id>', methods=['GET', 'POST'])
def edit_file(file_id):

    file = File.query.get(file_id)
    shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=session['user_id']).first()

    if not file:
        flash('File not found.', 'danger')
        return redirect(url_for('main.view_files'))
    
    if shared_file is None and file.user_id != session['user_id']:
        flash('You do not have permission to edit this file.', 'danger')
        log = auditlog(
            user_id=session['user_id'],
            action_type='edit file',
            details=f'Unauthorized edit attempt for file ID: {file_id}, filename: {file.original_filename}',
            status='failed'
        )
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('main.view_files'))
    
    if file.filetype == '.txt':
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)

        if not os.path.exists(file_path):
            flash('File not found on server.', 'danger')
            return redirect(url_for('main.view_files'))

        if request.method == 'GET': #Handle GET Request = display file content
            # decrypt original file data
            decrypted_file_data = decrypt_file_data(file.fileData, file.key)
            file_content = decrypted_file_data.decode('utf-8')  # Assuming the original file is UTF-8 encoded text
            return render_template('edit_file.html', file=file, file_id=file_id, file_content=file_content)
        
        else:
            new_content = request.form.get('content', '')
            try:
                # Write new content to file
                new_content_bytes = new_content.encode('utf-8')
                encrypted_content, _ = encrypt_file_data(new_content_bytes, file.key)  # Encrypt new content
                file.fileData = encrypted_content  # Update file data with encrypted content

                with open(file_path, 'wb') as f:
                    f.write(new_content_bytes)  # Save new content to file (unencrypted on disk)

                log = auditlog(
                    user_id=session['user_id'],
                    action_type='edit file',
                    details=f'Edited file ID: {file_id}, filename: {file.original_filename}'
                )
                db.session.add(log)
                db.session.commit()
                flash(f'File "{file.original_filename}" updated successfully.', 'success')
                return redirect(url_for('main.view_file', file_id=file_id))
            except Exception as e:
                flash(f'Error saving file: {str(e)}', 'danger')

    if file.filetype == '.pdf':
        pass
    if file.filetype == '.doc' or file.filetype == '.docx':
        pass

    return render_template('edit_file.html', file=file, file_id=file_id)

@main.route('/delete_file/<int:file_id>', methods=['GET', 'POST'])
def delete_file(file_id):
    file = File.query.get(file_id)
    recycle_entry = RecycleBin.query.filter_by(file_id=file_id).first()
    if file:
        filepath = os.path.join(current_app.config['RECYCLE_BIN_FOLDER'], file.filename)

        if os.path.exists(filepath):
            os.remove(filepath)

            db.session.delete(file)
            db.session.delete(recycle_entry)

            log = auditlog(
                user_id=session['user_id'],
                action_type='delete file',
                details=f'Deleted file ID: {file_id}, filename: {file.original_filename}'
            )
            db.session.add(log)
            db.session.commit()

            flash(f'File "{file.filename}" deleted successfully.', 'success')
    return redirect(url_for('main.view_files'))
    
@main.route('/recycle', methods=['POST'])
def recycle():
    file_id = request.args.get('file_id')
    file = File.query.get(file_id)
    if file:
        file.status = 'recycle_bin'
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        new_path = os.path.join(current_app.config['RECYCLE_BIN_FOLDER'], file.filename)
        os.rename(old_path, new_path)


        log = auditlog(
            user_id=session['user_id'],
            action_type='recycle file',
            details=f'Moved file ID: {file_id}, filename: {file.original_filename} to recycle bin'
        )
        db.session.add(log)

        new_recycle_entry = RecycleBin(
            file_id=file.file_id,
            filename=file.filename,
            deleted_by_user_id=session['user_id'],
            deleted_at=datetime.utcnow()
        )
        db.session.add(new_recycle_entry)
        db.session.commit()

        flash(f'File "{file.filename}" moved to recycle bin.', 'success')
    return redirect(url_for('main.view_files'))

@main.route('/restore/<int:file_id>', methods=['GET'])
def restore_file(file_id):
    file = File.query.get(file_id)
    if file:
        file.status = 'safe'
        old_path = os.path.join(current_app.config['RECYCLE_BIN_FOLDER'], file.filename)
        new_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        os.rename(old_path, new_path)

        log = auditlog(
            user_id=session['user_id'],
            action_type='restore file',
            details=f'Restored file ID: {file_id}, filename: {file.original_filename}'
        )
        db.session.add(log)

        RecycleBin.query.filter_by(file_id=file_id).delete()
        db.session.commit()

        flash(f'File "{file.filename}" restored successfully.', 'success')
    return redirect(url_for('main.view_files'))

@main.route('/view_recycle_bin', methods=['GET'])
def view_recycle_bin():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    recycle_bin_files = RecycleBin.query.filter_by(deleted_by_user_id=user_id).order_by(RecycleBin.deleted_at.desc()).all()
    return render_template('recycle_bin.html', recycle_bin=recycle_bin_files)

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

            #Read file data and encrypt
            key_string = generate_prng()  # Generate encryption key
            raw_file_data = file.read()
            file_size = len(raw_file_data)  # Get file size in bytes
            encrypted_file_data, returned_key = encrypt_file_data(raw_file_data, key_string)  # Encrypt file data

            if file_size > 50 * 1024 * 1024:  # 16 MB limit
                flash('File size exceeds the 50 MB limit. Please upload a smaller file.', 'danger')
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
            
            file.seek(0)  # Reset file pointer to the beginning after reading

            new_file = File(
                user_id=user_id,
                filename=unique_filename,
                original_filename=original_filename,
                filetype=filetype,
                file_size=file_size,  # Placeholder for file size
                fileData=encrypted_file_data,  # Store encrypted data
                key=returned_key,  # Generate and store encryption key
                description=description,
                shared_with=shared_with,
                status='pending',
                sensitivity=5,
                action='no action'
            )
            db.session.add(new_file)
            db.session.flush()  # Get new_file.file_id before commit
            
            filepath = file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
            
            # Add watermark if file is a pdf
            if filetype == '.pdf':
                username = session.get('username')
                ip_address = get_system_info()
                view_time = datetime.utcnow().isoformat()
                add_invisible_watermark(filepath, unique_filename)

                watermark_entry = Watermark(
                    file_id = new_file.file_id,
                    watermark_text= f"User: {username}, IP: {ip_address}, Time: {view_time}",
                    created_at=datetime.utcnow()
                )
                db.session.add(watermark_entry)

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
    if not session.get('is_admin'):
        flash('You do not have permission to view audit logs.', 'danger')

        log = auditlog(
            user_id=session.get('user_id'),
            action_type='view admin audit logs',
            details='Unauthorized attempt to view audit logs',
            status='failed'
        )
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    #logs_per_page = 30
    userid = request.args.get('userid')
    action_type = request.args.get('action_type')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sort = request.args.get('sort', 'timestamp')

    query = db.session.query(AuditLog)
    if userid:
        query = query.filter(AuditLog.user_id == userid)
    if action_type:
        query = query.filter(AuditLog.action_type == action_type)
    if status:
        query = query.filter(AuditLog.status == status)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)

    filter_params = {}
    if userid:
        filter_params['userid'] = userid
    if action_type:
        filter_params['action_type'] = action_type
    if date_from:
        filter_params['date_from'] = date_from
    if date_to:
        filter_params['date_to'] = date_to
    if status:
        filter_params['status'] = status

    pagination = query.paginate(page=page, error_out=False)
    logs = pagination.items
    total_pages = pagination.pages

    return render_template(
        'audit_logs.html', 
        logs=logs,
        page=page,
        total_pages=total_pages,
        filter_params=filter_params)

@main.route('/manage_users')
def manage_users():
    if request.method == 'GET':
        if not session.get('is_admin'):
            flash('You do not have permission to manage users.', 'danger')

            log = auditlog(
                user_id=session.get('user_id'),
                action_type='view manage users',
                details='Unauthorized attempt to access manage users page',
                status='failed'
            )
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('main.index'))
        
        users = User.query.order_by(User.created_at.desc()).all()

    return render_template('manage_users.html', users=users)

@main.route('/creating_watermark', methods=['POST'])
def creating_watermark(input_file, output_file, watermark_text):
    try:
        # Open the original PDF
        doc = pymupdf.open(input_file)
        
        # Create a watermark image
        watermark = Image.new('RGBA', (400, 100), (255, 255, 255, 0))
        draw = ImageDraw.Draw(watermark)
        font = ImageFont.load_default()
        draw.text((10, 10), watermark_text, font=font, fill=(255, 0, 0, 128))
        
        # Save the watermark as a temporary PNG
        temp_watermark_path = f'watermark/{filename}.jpg'
        watermark.save(temp_watermark_path)

        # Apply the watermark to each page of the PDF
        for page in doc:
            page.insert_image(page.rect, filename=temp_watermark_path, overlay=True)

        # Save the watermarked PDF
        doc.save(output_file)
        
        # Clean up temporary watermark image
        os.remove(temp_watermark_path)
    except Exception as e:
        print(f"Error creating watermark: {e}")

def get_system_info():
    """Get client's IP address for logging purposes"""
    ip_address = request.remote_addr
    return ip_address

@main.route('/addInvisibleWatermark', methods=['POST'])
def add_invisible_watermark(input_path, filename):
    input_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

    ip_address = get_system_info()
    print(ip_address)
    viewing_time = datetime.now().isoformat()
    username = session.get('username')
    watermark = {
        'username': username,
        'ip': ip_address,
        'time': viewing_time
    }
    watermark_json = json.dumps(watermark)
    watermark_b64 = base64.b64encode(watermark_json.encode()).decode()  # Encode watermark text to base64 to ensure it can be safely embedded

    with Pdf.open(input_path, allow_overwriting_input=True) as file:
        if file.Root is None:
            file.Root = Dictionary()
        if file.docinfo is None:
            file.docinfo = Dictionary()
        file.docinfo['/Watermark'] = watermark_b64  # Store the watermark in PDF metadata (invisible to users but can be extracted later)
        file.docinfo['/WatermarkJSON'] = watermark_json
        file.save()  # Save changes to the original file or a new file as needed

    print(f"✓ Invisible watermark embedded successfully")
    print(f"  Username: {username}")
    print(f"  IP: {ip_address}")
    print(f"  Time: {viewing_time}")
    return watermark 
    

def add_watermark(file_id, watermark_text):
    file = File.query.get(file_id)
    if file and file.filetype == '.pdf':
        try:
            file = open(os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename), 'rb')
            reader = PyPDF2.PdfReader(file)
            page = reader.getPage(0)

        except Exception as e:
            print(f"Error adding watermark: {e}")

@main.route('/change_settings', methods=['POST'])
def change_settings():
    if request.method == 'POST':
        setting_to_change = request.form.get('setting_to_change')

        user_id = session.get('user_id')
        if not user_id:
            flash('You must be logged in to change settings.', 'danger')
            return redirect(url_for('auth.login'))
        
        if setting_to_change == 'password':
            old_password = request.form.get('old_value')
            new_password = request.form.get('new_value')

            user = User.query.get(user_id)
            if not user.check_password(old_password):
                flash('Old password is incorrect.', 'danger')
                return redirect(url_for('main.manage_users'))
            user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully.', 'success')
