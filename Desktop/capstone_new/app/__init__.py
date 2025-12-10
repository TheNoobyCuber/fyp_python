from flask import Flask

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
    
     # Register the blueprint
    from app.routes import auth, main  # Must be imported here to avoid circular dependencies
    app.register_blueprint(auth)
    app.register_blueprint(main)
    
    return app
# End of app/__init__.py