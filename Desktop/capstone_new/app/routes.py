import base64
from fileinput import filename
from importlib.resources import files
import hashlib, hmac
import os
from urllib import response
from flask import Blueprint, app, render_template, request, redirect, send_from_directory, url_for, flash, session, current_app, jsonify, make_response
from flask_sqlalchemy import query
from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError
from wtforms import ValidationError
from .models import AuditLog, File, RecycleBin, ShareFile, User, FileHash, Edit, db
from datetime import datetime, timedelta
import random 
from flask_mail import Message
import pymupdf
import requests
import uuid # Universally Unique Identifiers
import jwt # Used in Docker
import secrets # Used for jwt
import json
from pikepdf import Pdf, Dictionary

ALLOWED_FILE_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx']
ONLYOFFICE_URL = 'http://localhost:8080' # OnlyOffice API configuration
JWT_SECRET = '22077237D_capstone_project_jwt_secret_key' # OnlyOffice API configuration

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

def generate_prng():
    raw_key_string = os.urandom(32) # Generate a 256-bit random key
    key_string = base64.b64encode(raw_key_string).decode('utf-8')  # Encode the key in base64 for storage
    return key_string

def generate_salt():
    return os.urandom(16)  # Generate a 128-bit random salt

def generate_hmac_hash(file_content, key=None):
    if key is None:
        key = generate_prng()
    raw_key = base64.b64decode(key)
    hash_value = hmac.new(raw_key, file_content, hashlib.sha256)
    hex_hash = hash_value.hexdigest()
    print(f"HMAC-SHA256 (Hex): {hex_hash}")
    return hex_hash

def encrypt_file_data(file_data, encryption_key=None):
    if encryption_key is None:
        encryption_key = generate_prng()  # Generate a new key if not provided
    elif isinstance(encryption_key, str):
        encryption_key = encryption_key.encode('utf-8') # Convert string key back to bytes
    
    var = Fernet(encryption_key)
    encrypted_data = var.encrypt(file_data)
    return encrypted_data, encryption_key

def decrypt_file_data(encrypted_data, encryption_key):
    if isinstance(encryption_key, str):
        encryption_key = encryption_key.encode('utf-8') # Convert string key back to bytes
    else:
        encryption_key = encryption_key

    ciphertext = Fernet(encryption_key)
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
    
def get_user_folders(type='uploads', user_id=None):
    try:
        if user_id is None:
            user_id = session.get('user_id')
            if not user_id:
                flash('You need to login before proceeding.')
                return None
        
        config_folders = {
            'uploads': 'UPLOAD_FOLDER',
            'recycle': 'RECYCLE_BIN_FOLDER',
            'temp': 'TEMP_FOLDER'
        }

        config_folder = config_folders.get(type, type.upper() + 'FOLDER')
        base_folder = current_app.config.get(config_folder)

        user_folder = os.path.join(base_folder, str(user_id))
        os.makedirs(user_folder, exist_ok=True)

        return user_folder

    except Exception as e:
        print(f"Error in get_user_folders: {str(e)}")
        return None


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
    current_user_username = current_user.username
    files = File.query.filter_by(user_id=user_id).order_by(File.upload_time.desc()).all() #Get user's OWN files
    for file in files:
        file.uploaded_by_username = current_user_username

    shared_files_data = ShareFile.query.filter(ShareFile.shared_with_user_id == user_id).order_by(ShareFile.shared_at.desc()).all() #Get files SHARED to the user
    shared_files = []
    for share in shared_files_data:
        file = File.query.get(share.file_id)
        
        if file and file.status != 'recycle_bin':
            uploader = User.query.get(file.user_id)

            shared_files.append({
                'file': file,
                'shared_by_username': share.shared_by_username,  # From ShareFile
                'shared_at': share.shared_at,  # From ShareFile
                'description': share.description,  # From ShareFile
                'uploaded_by_username': uploader.username if uploader else 'Unknown'
            })

            print(f'Shared files: {shared_files}')

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
        user_folder = get_user_folders('uploads', file.user_id)
        shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()
        if not shared_file:
            flash('Access denied.', 'danger')
            return redirect(url_for('main.view_files'))
    else:
        user_folder = get_user_folders('uploads', user_id)

    file_path = os.path.join(user_folder, file.filename)
    if not os.path.exists(file_path):
        flash('File not found on server.', 'danger')
        return redirect(url_for('main.view_files'))
    
    if file.file_type not in ALLOWED_FILE_EXTENSIONS:
        flash('Cannot display this file type.', 'warning')
        return redirect(url_for('main.view_files'))
    
    key = file.encryption_key
    raw_data = decrypt_file_data(file.file_data, key)  # Decrypt file data to ensure key is correct and file is accessible

    log = auditlog(
        user_id=session['user_id'],
        action_type='view file',
        details=f'Viewed file ID: {file_id}, filename: {file.original_filename}'
    )
    db.session.add(log)
    
    if file.file_type == '.txt':
        decrypted_content = decrypt_file_data(file.file_data, file.encryption_key).decode('utf-8') # Assuming the original file is UTF-8 encoded text
        with open(file_path, 'rb') as f:
            content = f.read()
        hash = generate_hmac_hash(content)
        print(hash)

        username = session.get('username')
        ip_address = get_system_info
        view_time = datetime.utcnow().isoformat()

        hash = FileHash(
            user_id = user_id,
            file_id = file_id,
            watermark_text = f"User: {username}, IP: {ip_address}, Time: {view_time}",
            hashValue = hash,
            created_at=datetime.utcnow()
        )
        db.session.add(hash)
        db.session.commit()

        return render_template('view_file.html', file=file, file_id=file_id, content=decrypted_content)
    
    elif file.file_type in ['.doc', '.docx', '.pdf']:
        serve_file(file_id) 
        return render_template('view_file.html', file=file, file_id=file_id)

    return render_template('view_file.html', file=file, file_id=file_id, content=raw_data)

@main.route('/serve_file/<int:file_id>', methods=['GET'])
def serve_file(file_id): 
    """Used so that the file pops up in a designated space in view_file.html instead of the entire window"""
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('auth.login'))
    
    file = File.query.get(file_id)

    if not file:
        flash('File not found.', 'danger')
        return redirect(url_for('main.view_files'))
    
    if file.user_id != user_id:
        user_folder = get_user_folders('uploads', file.user_id)
        shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()
        if not shared_file:
            flash('Access denied.', 'danger')
            return redirect(url_for('main.view_files'))
    else:
        user_folder = get_user_folders('uploads', user_id)
    
    file_path = os.path.join(user_folder, file.filename)
    print(f"DEBUG - filepath: {file_path}")

    if not os.path.exists(file_path):
        flash('File not found on server.', 'danger')
        return redirect(url_for('main.view_files'))

    temp_folder = get_user_folders('temp', file.user_id)
    temp_path = os.path.join(temp_folder, file.filename)
    
    raw_data = decrypt_file_data(file.file_data, file.encryption_key)  # Decrypt file data to ensure key is correct and file is accessible

    file_response = make_response(raw_data)
    try:
        if file.file_type == '.pdf':
            file_response.mimetype = 'application/pdf'
            file_response.headers['Content-Disposition'] = f'inline; filename="{file.original_filename}"'

            username = session.get('username')
            ip_address = get_system_info()
            view_time = datetime.utcnow().isoformat()
            watermark_text= f"User: {username}, IP: {ip_address}, Time: {view_time}"
            insertion_point = pymupdf.Point(-100, -100)

            embed_text_in_pdf(file_path, temp_path, watermark_text, insertion_point)
            hash = generate_hmac_hash(raw_data, file.encryption_key)

            hash = FileHash(
                user_id = user_id,
                file_id = file_id,
                watermark_text = watermark_text,
                hashValue = hash,
                created_at=datetime.utcnow()
            )
            db.session.add(hash)
            db.session.commit()

        elif file.file_type in ['.doc', '.docx']: 
            pass

        return file_response

    except Exception as e:
        print(f"Error serving file: {e}")
        flash(f'Error serving file: {str(e)}', 'danger')
        return redirect(url_for('main.view_files'))

@main.route('/edit_file/<int:file_id>', methods=['GET', 'POST'])
def edit_file(file_id): #Edit function for .txt
    user_id = session.get('user_id')
    file = File.query.get(file_id)
    shared_file = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()

    if not file:
        flash('File not found.', 'danger')
        return redirect(url_for('main.view_files'))
    
    if shared_file is None and file.user_id != user_id:
        flash('You do not have permission to edit this file.', 'danger')
        log = auditlog(
            user_id=user_id,
            action_type='edit file',
            details=f'Unauthorized edit attempt for file ID: {file_id}, filename: {file.original_filename}',
            status='failed'
        )
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('main.view_files'))
    
    if file.file_type == '.txt':
        if file.user_id == user_id:
            print(f'The user id of this file is {user_id}.')
            user_folder = get_user_folders('uploads', user_id)

        else:
            uploader_id = file.user_id
            print(f'The user id of this file is {uploader_id}.')
            user_folder = get_user_folders('uploads', uploader_id)
        
        file_path = os.path.join(user_folder, file.filename)

        if not os.path.exists(file_path):
            flash('File not found on server.', 'danger')
            return redirect(url_for('main.view_files'))

        if request.method == 'GET': #Handle GET Request = display file content
            # decrypt original file data
            decrypted_file_data = decrypt_file_data(file.file_data, file.encryption_key)
            file_content = decrypted_file_data.decode('utf-8')  # Assuming the original file is UTF-8 encoded text
            return render_template('edit_file.html', file=file, file_id=file_id, file_content=file_content)
        
        else:
            new_content = request.form.get('content', '')
            try:
                # Write new content to file
                new_content_bytes = new_content.encode('utf-8')
                encrypted_content, _ = encrypt_file_data(new_content_bytes, file.encryption_key)  # Encrypt new content
                file.file_data = encrypted_content  # Update file data with encrypted content

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

    if file.file_type == '.doc' or file.file_type == '.docx':
        pass

    return render_template('edit_file.html', file=file, file_id=file_id)

@main.route('/delete_file/<int:file_id>', methods=['GET', 'POST'])
def delete_file(file_id): # COMPLETED
    user_id = session.get('user_id')
    file = File.query.get(file_id)
    recycle_entry = RecycleBin.query.filter_by(file_id=file_id).first()
    if file:
        user_folder = get_user_folders('recycle', user_id)
        filepath = os.path.join(user_folder, file.filename)

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
def recycle(): # COMPLETED
    user_id = session.get('user_id')

    if not user_id:
        flash("Please Login first before proceeding.")
        return redirect(url_for(auth.login))
    
    file_id = request.args.get('file_id')
    file = File.query.get(file_id)
    if file:
        user_upload_folder = get_user_folders('uploads', user_id)
        user_recycle_folder = get_user_folders('recycle', user_id)

        if not user_upload_folder or not user_recycle_folder:
            flash("error retrieving folders", 'danger')
            return redirect(url_for('main.view_files'))
        
        file.status = 'recycle_bin'
        old_path = os.path.join(user_upload_folder, file.filename)
        new_path = os.path.join(user_recycle_folder, file.filename)
        
        try:
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

        except Exception as e:
            db.session.rollback()
            flash(f'Error moving file to recycle bin: {str(e)}', 'danger')

    return redirect(url_for('main.view_files'))

@main.route('/restore/<int:file_id>', methods=['GET'])
def restore_file(file_id): # COMPLETED
    user_id = session.get('user_id')
    file = File.query.get(file_id)
    if file:
        file.status = 'safe'
        user_upload_folder = get_user_folders('uploads', user_id)
        user_recycle_folder = get_user_folders('recycle', user_id)
        old_path = os.path.join(user_recycle_folder, file.filename)
        new_path = os.path.join(user_upload_folder, file.filename)
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
def view_recycle_bin(): # COMPLETED
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    recycle_bin_files = RecycleBin.query.filter_by(deleted_by_user_id=user_id).order_by(RecycleBin.deleted_at.desc()).all()
    return render_template('recycle_bin.html', recycle_bin=recycle_bin_files)

@main.route('/share/<int:file_id>', methods=['GET', 'POST'])
def share_file(file_id):
    file = File.query.get(file_id)
    original_filename = file.original_filename

    if not file:
        flash("File not found.", "danger")
        return render_template('files.html')
    
    if file and request.method == 'POST':
        try:
            shared_with = request.form.get('shared_with')
            if not shared_with:
                flash("Please enter a user to share this file with.")
                return render_template('files.html')
            
            shared_with_user = User.query.filter_by(username=shared_with).first()
            shared_with_user_id = shared_with_user.id
            shared_with_username = shared_with_user.username

            shared_by_user_id = session.get('user_id')
            shared_by_username = session.get('username')

            if not shared_with_user_id:
                flash('User to share with not found.', 'danger')
                return redirect(url_for('main.view_files'))
            else:
                shared_with_username = shared_with_user.username
                description = request.form.get('description')
                description = description or ''
                
                share_file = ShareFile( #Add entry to ShareFile table
                    file_id=file_id,
                    shared_with_user_id=shared_with_user_id,
                    shared_with_username=shared_with_username,
                    shared_by_user_id=shared_by_user_id,
                    shared_by_username=shared_by_username,
                    description=description,
                    shared_at=datetime.utcnow()
                )
                db.session.add(share_file)
                print(f"✓ ShareFile entry added to session")

                log = auditlog( #Log the sharing action
                    user_id=session['user_id'],
                    action_type='share file',
                    details=f'Shared file ID: {file_id}, filename: {original_filename} with users: {shared_with}'
                )
                db.session.add(log)
                print(f"✓ AuditLog entry added to session")

                print(f"Attempting to commit...")
                db.session.commit()
                print(f"✓ Session committed successfully.")
                flash(f'File {original_filename} shared with {shared_with_username} successfully!', 'success')
        
        except Exception as e:
            flash(f'Error sharing file: {str(e)}', 'danger')
            return redirect(url_for('main.index'))
        
    return redirect(url_for('main.view_files'))
        
    
@main.route('/upload', methods=['GET', 'POST'])
def upload():
    user_id = session.get('user_id')
    username = session.get('username')
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
            
            file_type = get_file_extension(original_filename)

            if file_type not in ALLOWED_FILE_EXTENSIONS:
                flash('File type not allowed. Please upload a valid file.', 'danger')
                return render_template('uploadfile.html', shared_with=shared_with, description=description)
            
            if not shared_with:
                flash('Please specify at least one user to share the file with.', 'danger')
                #os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                return render_template('uploadfile.html', shared_with=shared_with, 
                                       description=description)
            # Create unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            user_id = session.get('user_id')
            unique_filename = f"{user_id}_{timestamp}_{original_filename}"
            print(f"DEBUG - unique filename: {unique_filename}")

            #Read file data and encrypt
            encryption_key = generate_prng()  # Generate encryption key
            raw_file_data = file.read()
            file_size = len(raw_file_data)  # Get file size in bytes

            if file_size > 50 * 1024 * 1024:  # 50 MB limit
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

            encrypted_file_data, encryption_key = encrypt_file_data(raw_file_data, encryption_key)  # Encrypt file data

            #Saving to temporary folder
            user_uploads_folder = get_user_folders('uploads', user_id)
            upload_filepath = os.path.join(user_uploads_folder, unique_filename)
            file.seek(0)
            file.save(upload_filepath)
            
            file_key = generate_file_key()

            new_file = File(
                user_id=user_id,
                filename=unique_filename,
                original_filename=original_filename,
                file_type=file_type,
                file_size=file_size,  # Placeholder for file size
                file_data=encrypted_file_data,  # Store encrypted data
                encryption_key=encryption_key,  # Generate and store encryption key
                key=file_key, # Key for File editing purposes
                description=description,
                shared_with=shared_with,
                status='pending',
                sensitivity=5,
                action='no action'
            )
            db.session.add(new_file)
            db.session.flush()  # Get new_file.file_id before commit

            temp_folder = get_user_folders('temp', user_id)
            temp_path = os.path.join(temp_folder, unique_filename)

            # Add watermark if file is a pdf
            if file_type == '.pdf':
                user_id = session.get('user_id')
                username = session.get('username')

                ip_address = get_system_info()
                view_time = datetime.utcnow().isoformat()
                watermark_text= f"User: {username}, IP: {ip_address}, Time: {view_time}",
                insertion_point = pymupdf.Point(-100, -100)
                os.rename(upload_filepath, temp_path)
                # add invisible text watermark 
                embed_text_in_pdf(temp_path, upload_filepath, watermark_text, insertion_point)
                # add metadata to watermarked file + save back to uploads folder
                embed_metadata(username, temp_path, upload_filepath, watermark_text, view_time)
    
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                with open(upload_filepath, 'rb') as f:
                    content = f.read()
                hash = generate_hmac_hash(content)
                print(hash)

                hash = FileHash(
                    user_id = user_id,
                    file_id = new_file.file_id,
                    watermark_text= watermark_text,
                    hashValue = hash,
                    created_at=datetime.utcnow()
                )
                db.session.add(hash)

            elif file_type in ['.doc', '.docx', '.txt']:
                with open(upload_filepath, 'rb') as f:
                    content = f.read()
                hash = generate_hmac_hash(content)
                print(hash)

            share_file = ShareFile( #Add entry to ShareFile table
                file_id=new_file.file_id,
                shared_with_user_id=shared_with_user_id,
                shared_with_username=shared_with_user,
                shared_by_user_id=user_id,
                shared_by_username=username,
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

def auditlog(user_id, action_type, details='', status='success'): #For Audit Logging
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
def view_audit_logs(): #Admin Function
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
def manage_users(): #Admin Function
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

def get_system_info(): # For watermarking
    """Get client's IP address for logging purposes"""
    ip_address = request.remote_addr
    return ip_address

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

def embed_text_in_pdf(input_path, output_path, text, point):
    file = pymupdf.open(input_path)
    page = file[0]

    page.insert_text(point, text, fontsize=12, color=(0, 0, 0, 0.5)) 
    file.save(output_path)
    file.close()

def embed_metadata(username, input_path, output_path, text, watermark_time):
    ip_address = get_system_info()

    watermark = {
        'username': username,
        'ip_address': ip_address,
        'watermark_time': watermark_time,
        'watermark_text': text
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
        file.save(output_path)  # Save changes to new file

def generate_file_key(file_id=None):
    if file_id:
        return f"file_{file_id}_{secrets.token_hex(16)}"
    return secrets.token_urlsafe(32)



@main.route('/edit/<int:file_id>')
def edit(file_id):
    user_id = session.get('user_id')
    username = session.get('username')
    file = File.query.get(file_id)
    original_filename = file.original_filename
    #Generate unique doc key
    doc_key = str(uuid.uuid4())

    if 'doc_key_mappings' not in session:
        session['doc_key_mappings'] = {}  # Create the dictionary
    session['doc_key_mappings'][doc_key] = file_id  # Create Dictionary to store doc_key and file_id pairs

    edit = Edit(
        file_id = file_id,
        user_id = user_id,
        doc_key = doc_key
    )
    db.session.add(edit)
    log = auditlog(
        user_id=session['user_id'],
        action_type='edit file',
        details=f'Opened OnlyOffice editor for editing file ID: {file_id}, filename: {original_filename}'
    )
    db.session.add(log)
    db.session.commit()

    user_token = jwt.encode({"user_id": user_id}, JWT_SECRET, algorithm="HS256")
    if isinstance(user_token, bytes):
        user_token = user_token.decode('utf-8')

    # doc_url = f'http://host.docker.internal:5001/api/online/{file_id}?token={user_token}'
    # callback_url = f'http://host.docker.internal:5001/api/callback/{doc_key}'

    doc_url = f'http://192.168.50.242:5001/api/online/{file_id}?token={user_token}'
    callback_url = f'http://192.168.50.242:5001/api/callback/{doc_key}'

    current_user = {
        "id": str(user_id),
        "name": str(username)
    }

    editor_config = {
        "document": {
            "fileType": original_filename.split('.')[-1],
            "key": doc_key,
            "title": original_filename,
            "url": doc_url,
            "permissions": {
                "edit": True,
                "download": False,
                "print": False
            }
        },
        "documentType": 'word',
        "editorConfig": {
            "user": current_user,
            "callbackUrl": str(callback_url),
            "mode": "edit"
        }
    }

    # Generate and send a real token upon every edit
    jwt_editor = jwt.encode(editor_config, JWT_SECRET, algorithm="HS256")
    if isinstance(jwt_editor, bytes):
        jwt_editor = jwt_editor.decode('utf-8')
    editor_config["token"] = jwt_editor

    # Debug prints
    print(f"=== EDIT ROUTE DEBUG ===")
    print(f"File ID: {file_id}")
    print(f"Doc Key: {doc_key}")
    print(f"Document URL: {doc_url}")
    print(f"Callback URL: {callback_url}")

    return render_template('edit.html', 
                         editor_config=editor_config,
                         onlyoffice_url=ONLYOFFICE_URL)

@main.route('/api/online/<int:file_id>')
def serve_onlinedoc(file_id):
    user_id = None
    
    token = request.args.get('token')
    if token:
        try:
            decode = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            user_id = decode.get('user_id')
            print(f'User ID from token: {user_id}')

        except Exception as e:
            print(f"token {token} not found")
            # return jsonify({"error": "Unauthorized"}), 401
    
    # If no token, try session
    if not token:
        user_id = session.get('user_id')
        print(f"User ID from session: {user_id}")
    
    if not user_id:
        print("No user ID found")
        return jsonify({'error': 'You are Unauthorized'}), 401
    
    file = File.query.get(file_id)
    
    if not file:
        return jsonify({"error": "File not found"}), 404
    
    if file.user_id != user_id:
        shared = ShareFile.query.filter_by(file_id=file_id, shared_with_user_id=user_id).first()
        if not shared:
            return jsonify({"error": "Access denied"}), 403
        
    #Get user folders
    user_folder = get_user_folders('uploads', file.user_id)
    filepath = os.path.join(user_folder, file.filename)

    if not os.path.exists(filepath):
        return jsonify({"error: File not found"}), 404
    
    #Open file
    with open(filepath, 'rb') as f:
        file_content = f.read()

    response = make_response(file_content)
    
    extension = file.original_filename.split('.')[-1].lower()

    filetypes = {
            'txt': 'text/plain',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
    response.headers['Content-Type'] = filetypes.get(extension, 'application/octet-stream')
    response.headers['Content-Disposition'] = f'inline; filename="{file.original_filename}"'

    return response

@main.route('/api/callback/<string:doc_key>', methods=['POST'])
def api_callback(doc_key):
    """Handle save callbacks from ONLYOFFICE"""

    edit_session = Edit.query.filter_by(doc_key=doc_key).first()
    print(f'doc_key: {doc_key}')

    if edit_session:
        file_id = edit_session.file_id
        user_id = edit_session.user_id
        print(f"Found in database - File ID: {file_id}, User ID: {user_id}")
    
    else:
        file_id = session.get('doc_key_mappings', {}).get(doc_key)
        if file_id:
            print(f"✅ Found in session - File ID: {file_id}")
        else:
            print(f"❌ No file_id found for doc_key: {doc_key}")
            # Return 200 to prevent ONLYOFFICE from retrying
            return jsonify({"error": 0}), 200

    file = File.query.get(file_id)
    filename = file.filename
    file_data = file.file_data

    if not file:
        print(f'file not found on server')
        return jsonify({"error": 0}), 200
        
    data = request.json
    status = data.get('status')

    if status == 2 or status == 6 or status == 7:
        document_url = data.get('url')
        
        if document_url:
            try:
                # 1. Get the updated doc from onlyoffice
                response = requests.get(document_url, timeout=30)
                
                if response.status_code == 200:
                    updated_content = response.content
                    print(f"Downloaded {len(updated_content)} bytes")

                    # Save file: encrypt file, then update db, then update physical storage place
                    encrypted_content, encryption_key = encrypt_file_data(updated_content, file.encryption_key)

                    #Update encrypted file_data in database
                    file.file_data = encrypted_content
                    file.encryption_key = encryption_key

                    #Update non-encrypted file to disk
                    user_folder = get_user_folders('uploads', file.user_id)
                    filepath = os.path.join(user_folder, filename)
                    with open(filepath, 'wb') as f:
                        f.write(updated_content)
                    
                    db.session.commit()
                    print(f'File {filename} updated successfully!')
                    return jsonify({'error': 0})
                
            except Exception as e:
                flash('Error downloading file')
                return jsonify({"error": 1}), 500  # ← This is correct
    return jsonify({"error": 0}), 200  
