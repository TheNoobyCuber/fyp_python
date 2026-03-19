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

    # Database configuration + pool settings to handle long-running operations
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost:3306/DLPS'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = True  # Set to True to see SQL queries
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,  # Recycle connections after 1 hour
    'pool_pre_ping': True,  # Test connections before using
}
    
    #Upload and Upload folder configuration
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)),  'secure_uploads/')
    app.config['RECYCLE_BIN_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)),  'recycle_bin/')
    app.config['TEMP_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)),  'temp/')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RECYCLE_BIN_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB limit

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