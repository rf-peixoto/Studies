"""Extension singletons, defined here so any blueprint can import them without
creating an import cycle with the application factory."""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."

limiter = Limiter(key_func=get_remote_address)
