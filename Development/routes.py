"""Logged-in page routes."""
import os
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required, logout_user
from twilioclient import twilio
# import local modules
from database.manage_db import Manage_db
# import external modules / libaries
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# Blueprint Configuration
main_bp = Blueprint(
    'main_bp', __name__,
    template_folder='templates',
    static_folder='static'
)


@main_bp.route('/', methods=['GET'])
@login_required
def dashboard():
    """Logged-in User Dashboard."""
    return render_template(
        'dashboard.jinja2',
        title='Login Page.',
        template='dashboard-template',
        current_user=current_user,
        body="You are now logged in!"
    )


@main_bp.route("/logout")
@login_required
def logout():
    """User log-out logic."""
    logout_user()
    return redirect(url_for('auth_bp.login'))


@main_bp.route('/rsms', methods=['POST'])
def respond_and_save():
    users = Manage_db()
    active = os.getenv('TWILIO_RECP')
    single_user = users.get_users(active)
    twil = twilio.TwilioClient(recipient=single_user)
    resp = twil.respond_to_sms()
    return str(resp)
