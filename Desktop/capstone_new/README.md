source# Enterprise Data Leakage Prevention System (DLPS)

A Flask-based web application for secure file storage with client-side encryption, access control, and audit logging.

## Features
- User authentication with password hashing
- Client-side file encryption before upload
- Secure file sharing with permissions
- Activity auditing and logging
- Role-based access control
- Secure file deletion with overwrite

## Requirements
- Python 3.9+
- MySQL/MariaDB
- XAMPP (for local MySQL server)

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/TheNoobyCuber/fyp_python.git
cd capstone_new
```

### 2. Create Virtual Environment (Recommended)
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup
1. Start XAMPP and run MySQL server
2. import dlps.sql


## Running the Application
### 1. Start Development Server
```bash
python run.py
```

### 2. Access Application
Open in browser:
[http://localhost:5000](http://localhost:5000)


## Admin Account Setup
For security reasons, the registration interface does not provide an option to create admin accounts.
To create an administrator user:
### Method 1: Database Modification
1. Register a regular user through the web interface
2. Using phpMyAdmin client:
```sql
UPDATE user SET is_admin = 1 WHERE username = 'your_username';
```

### Method 2: Use Pre-configured Admin (Recommended for Initial Setup)
A default admin account is included in the database schema:
- Username: admin
- Password: 123
- Security Note:
    - Change the password immediately after first login
    - This account should only be used for initial setup
