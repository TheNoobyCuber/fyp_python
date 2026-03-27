from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
# from flask_wtf import FlaskForm
# from wtforms import StringField, PasswordField, SubmitField, SelectField
# from wtforms.validators import InputRequired, ValidationError, Length

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'User'

    id = db.Column('ID', db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column('password', db.String(255), nullable=False)
    #password_hash = db.Column(db.String(200))
    position = db.Column(db.String(50), nullable=False)  # Employee, Manager, Admin
    otp = db.Column(db.String(6), nullable=False)
    otp_expiry = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
class File(db.Model):
    __tablename__ = 'File'
    file_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer)
    file_data = db.Column(db.LargeBinary, nullable=False)  # Store file data as binary
    encryption_key = db.Column(db.String(255), nullable=False)  # Store encryption key
    key = db.Column(db.String(128), nullable=False)
    file_reference_key = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    shared_with = db.Column(db.String(255))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, scanned, flagged, safe
    sensitivity = db.Column(db.Integer)  # 1-10
    action = db.Column(db.String(20))  # 'block', 'alert', 'quarantine', 'no action'

class ShareFile(db.Model):
    __tablename__ = 'ShareFile'
    share_id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('File.file_id'))
    shared_with_user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    shared_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

class RecycleBin(db.Model):
    __tablename__ = 'RecycleBin'
    delete_id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('File.file_id'))
    filename = db.Column(db.String(200), nullable=False)
    deleted_by_user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)

class FileHash(db.Model):
    __tablename__ = 'FileHash'
    hash_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    file_id = db.Column(db.Integer, db.ForeignKey('File.file_id'))
    watermark_text = db.Column(db.String(255), nullable=False)
    hashValue = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'AuditLog'
    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    action_type = db.Column(db.String(50), nullable=False)  # e.g., 'upload', 'delete', 'share'
    details = db.Column(db.Text)  # Additional details about the action
    status = db.Column(db.String(50), default='success')  # success, failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Edit(db.Model):
    __tablename__ = 'Edit'
    edit_id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('File.file_id'))
    user_id = db.Column(db.Integer, db.ForeignKey('User.ID'))
    doc_key = db.Column(db.String(255), nullable=False)
    
