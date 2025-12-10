from extensions import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)

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