import email
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy.exc import SQLAlchemyError
from wtforms import ValidationError
# from app import AuditLog
from .models import User, db
from datetime import datetime
import time
import random

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

@main.route('/')
def index():
    """Home page - shows after login"""
    return render_template('dashboard.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        #remember = request.form.get('remember')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect('/dashboard.html')
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
            print(f"Creating user: {username}, {email}, position: {position}") # Debug print
            
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
            
            # Checking OTP validity
            registration_otp = session.get('registration_otp', {})
            stored_otp = registration_otp.get('otp')
            stored_email = registration_otp.get('email')
            stored_username = registration_otp.get('username')
            expiry = registration_otp.get('expiry', 0)
            
            # if not stored_otp or email != stored_email:
            #     flash('Please request a new verification code', 'danger')
            #     return render_template('register.html', username=username, email=email)
            
            # if datetime.now().timestamp() > expiry:
            #     flash('Verification code has expired. Please request a new one', 'danger')
            #     return render_template('register.html', username=username, email=email)
            
            #if otp != stored_otp:
                #flash('Invalid verification code', 'danger')
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
            start_time = time.time()
            db.session.commit()
            commit_time = time.time() - start_time
            print(f"Commit took: {commit_time:.2f} seconds")
            
            # # Logging the registration event
            # log = AuditLog(
            #     user_id=new_user.user_id,
            #     action_type='register',
            #     details='New user registration with email verification'
            # )
            # db.session.add(log)
            # db.session.commit()
            
            # Clearing the OTP session data
            # session.pop('registration_otp', None)
            
            flash('Account created successfully! You can now login.', 'success')
            return redirect(url_for('auth.login'))
        
        return render_template('register.html')

    except Exception as e:
        # Log the actual error
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
    
# @auth.route('/logout')
# def logout():
#     session.clear()
#     flash('You have been logged out.', 'info')
#     return redirect(url_for('auth.login'))

@auth.route('/upload', methods=['GET', 'POST'])
def upload_file():

    return "Upload file page - To be implemented"

