from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
# from flask_wtf import FlaskForm
# from wtforms import StringField, PasswordField, SubmitField, SelectField
# from wtforms.validators import InputRequired, ValidationError, Length

db = SQLAlchemy()

class User(db.Model):
    id = db.Column('ID', db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column('password', db.String(255), nullable=False)
    #password_hash = db.Column(db.String(200))
    position = db.Column(db.String(50), nullable=False)  # Employee, Manager, Admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    #filepath = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, scanned, flagged, safe
    dlp_policy_id = db.Column(db.Integer, db.ForeignKey('dlp_policy.id'))
    scan_results = db.Column(db.Text)  # JSON or text summary of scan results
        

class DlpPolicy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    pattern = db.Column(db.Text)  # Regex pattern
    sensitivity = db.Column(db.Integer)  ##### 1-5
    action = db.Column(db.String(20))  # 'block', 'alert', 'quarantine'
    is_active = db.Column(db.Boolean, default=True)

class DlpAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    policy_id = db.Column(db.Integer, db.ForeignKey('dlp_policy.id'))
    severity = db.Column(db.String(20))
    content = db.Column(db.Text)  # Redacted sensitive data
    file_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default='new')  # new, reviewed, resolved
    action_taken = db.Column(db.String(50))