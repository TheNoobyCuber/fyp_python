from flask import Flask, render_template
from app.models import db
from .routes import *
from flask_mail import Mail

def create_app():
    app = Flask(__name__)
    mail = Mail()

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route('/<page_name>')
    def show_page(page_name):
        if page_name.endswith('.html'):
            page_name = page_name[:-5]
        return render_template(f'{page_name}.html')
    
    @app.route('/debug-routes')
    def debug_routes():
        output = []
        for rule in app.url_map.iter_rules():
            output.append(f"{rule.endpoint:30s} {rule.rule}")
        return "<br>".join(sorted(output))

    # Configuration
    app.config['SECRET_KEY'] = '22077237dsecretkey'

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost:3306/DLPS'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = True  # Set to True to see SQL queries

    #Upload folder configuration
    app.config['UPLOAD_FOLDER'] = 'app/secure_uploads/'

    #Mail configuration 
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = '22077237dcapstone@gmail.com'
    app.config['MAIL_PASSWORD'] = 'mnxv ezbm iaou zwgn'
    app.config['MAIL_DEFAULT_SENDER'] = '22077237dcapstone@gmail.com'

    db.init_app(app)
    mail.init_app(app)
    
    # Register the blueprint
    from app.routes import auth ,main  # Must be imported here to avoid circular dependencies
    app.register_blueprint(auth)
    app.register_blueprint(main)

    return app