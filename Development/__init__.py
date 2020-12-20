"""Initialize app."""
from flask import Flask
from flask_login import LoginManager
from database.database import init_db

login_manager = LoginManager()


def create_app():
    """Construct the core app object."""
    app = Flask(__name__, instance_relative_config=False)

    # Application Configuration
    app.config.from_object('config.Config')

    # Initialize Plugins
    login_manager.init_app(app)

    with app.app_context():
        import routes
        import auth
        from assets import compile_static_assets

        # Register Blueprints
        app.register_blueprint(routes.main_bp)
        app.register_blueprint(auth.auth_bp)

        # Create Database Models
        app = init_db(app)

        # Compile static assets
        if app.config['FLASK_ENV'] == 'development':
            compile_static_assets(app)

        return app
