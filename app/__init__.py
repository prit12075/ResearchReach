import logging
from flask import Flask
from flask_cors import CORS
from .core.config import config

def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    CORS(app)

    # Register blueprints
    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
