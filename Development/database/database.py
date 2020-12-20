from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv
load_dotenv()


db = SQLAlchemy()


def init_db(app):
    """Connect the database to our Flask app."""
    import database.models
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.app = app
    db.init_app(app)
    with app.app_context():
        db.create_all()
    print("Connected to DB.")
    return app
