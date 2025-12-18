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

# class RegisterForm(FlaskForm):
#     username = StringField('Username', validators=[InputRequired(), Length(min=4, max=80)], render_kw={"placeholder": "Username"})
#     email = StringField('Email', validators=[InputRequired(), Length(min=6, max=80)], render_kw={"placeholder": "Email"})
#     password = PasswordField('Password', validators=[InputRequired(), Length(min=6)], render_kw={"placeholder": "Password"})
#     confirm_password = PasswordField('Confirm Password', validators=[InputRequired(), Length(min=6)], render_kw={"placeholder": "Confirm Password"})
#     position = SelectField('Position', choices=[('Employee', 'Employee'), ('Manager', 'Manager'), ('Admin', 'Admin')], validators=[InputRequired()])

#     submit = SubmitField('Register')

#     def validate_username(self, username):
#         existing_username = User.query.filter_by(username=username.data).first()
#         if existing_username:
#             raise ValidationError('Username is already taken. Please choose a different one.')
        
#     def validate_email(self, email):
#         existing_email = User.query.filter_by(email=email.data).first()
#         if existing_email:
#             raise ValidationError('Email is already registered. Please choose a different one.')
    
#     def validate_confirm_password(self, confirm_password):
#         if confirm_password.data != self.password.data:
#             raise ValidationError('Passwords do not match.')
        

# class LoginForm(FlaskForm):
#     username = StringField('Username', validators=[InputRequired(), Length(min=4, max=80)], render_kw={"placeholder": "Username"})
#     password = PasswordField('Password', validators=[InputRequired(), Length(min=6)], render_kw={"placeholder": "Password"})

#     submit = SubmitField('Login')
        

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