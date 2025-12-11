from flask import Flask
from app.models import db

def create_app():
    app = Flask(__name__)
    
    @app.route("/")
    def home():
        from flask import render_template
        return render_template("index.html")
    
    @app.route('/<page_name>')
    def show_page(page_name):
        from flask import render_template
        if page_name.endswith('.html'):
            page_name = page_name[:-5]
        return render_template(f'{page_name}.html')
    
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-here-change-this-in-production'
    
    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost:5000/DLPS'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False  # Set to True to see SQL queries
    
    db.init_app(app)
    
     # Register the blueprint
    from app.routes import auth ,main  # Must be imported here to avoid circular dependencies
    app.register_blueprint(auth)
    app.register_blueprint(main)
    
    return app
# End of app/__init__.py