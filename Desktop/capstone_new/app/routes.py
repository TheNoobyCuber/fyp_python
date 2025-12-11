from flask import Blueprint, render_template, request, redirect, url_for, flash, session
# from app import AuditLog
from .models import User, db
from datetime import datetime, timedelta
import random

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        position = request.form.get('position')
        otp = request.form.get('otp')
        
        # Checking and confirm password match
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Checking if full name is filled in 
        if fullname is None or fullname.strip() == '':
            flash('Please fill in your full name', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Checking if position is filled in correctly
        if position is None or position.strip() == '':
            flash('Please fill in your position', 'danger')
            return render_template('register.html', username=username, email=email)
        
        if position not in ['Employee', 'Manager', 'Admin']:
            flash('Please fill in a valid position', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Checking if the username is already taken
        if User.query.filter_by(username=username).first():
            flash('Username is already taken', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Checking if the email is already registered
        if User.query.filter_by(email=email).first():
            flash('Email is already registered', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Checking OTP validity
        registration_otp = session.get('registration_otp', {})
        stored_otp = registration_otp.get('otp')
        stored_email = registration_otp.get('email')
        stored_username = registration_otp.get('username')
        expiry = registration_otp.get('expiry', 0)
        
        if not stored_otp or email != stored_email:
            flash('Please request a new verification code', 'danger')
            return render_template('register.html', username=username, email=email)
        
        if datetime.now().timestamp() > expiry:
            flash('Verification code has expired. Please request a new one', 'danger')
            return render_template('register.html', username=username, email=email)
        
        if otp != stored_otp:
            flash('Invalid verification code', 'danger')
            return render_template('register.html', username=username, email=email)
        
        # Creating a new user
        new_user = User(fullname=fullname, username=username, email=email, position=position)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        # # Logging the registration event
        # log = AuditLog(
        #     user_id=new_user.user_id,
        #     action_type='register',
        #     details='New user registration with email verification'
        # )
        # db.session.add(log)
        # db.session.commit()
        
        # Clearing the OTP session data
        session.pop('registration_otp', None)
        
        flash('Account created successfully! You can now login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')