# # Imports
import sys
import uuid
import os
import itertools
import http.client
import requests
import re
import json
from random import randint
from collections import Counter, defaultdict

# # Third party libaries
from functools import wraps
from werkzeug.exceptions import HTTPException
from flask import Flask, jsonify, redirect, render_template, session, url_for
from authlib.integrations.flask_client import OAuth
from six.moves.urllib.parse import urlencode
from hashids import Hashids
from dotenv import load_dotenv, find_dotenv

# # AWS
import boto3
from boto3.dynamodb.conditions import Key, Attr

load_dotenv(find_dotenv())

ENV = 'PROD'

######################## GLOBAL RESCOURSES #####################################

# AWS SSM encrypted parameter store
ssm = boto3.client('ssm')


def get_ssm_param(param_name: str, required: bool = True) -> str:
    """Get an encrypted AWS Systems Manger secret."""
    response = ssm.get_parameter(
        Name=param_name,
        WithDecryption=True,
    )
    if not response['Parameter']:
        if not required:
            return None
        raise Exception(
            f"Configuration error: missing AWS SSM parameter: {param_name}")
    return response['Parameter']['Value']


if ENV == 'DEV':
    SERVER = os.getenv('SERVER_LOCAL')
else:
    SERVER = os.getenv('SERVER_PROD')
account_sid = get_ssm_param('TWILIO_ACCOUNT_SID')
auth_token = get_ssm_param('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = get_ssm_param("TWILIO_PHONE_NUMBER")
Twitter_auth = get_ssm_param("Twitter_BEARER_TOKEN")
XRAPIDURL = get_ssm_param('XRAPIDURL')
xrapidapihost = get_ssm_param('XRAPIDHOST')
xrapidapikey = get_ssm_param('XRAPIDKEY')
prediction_lambda_url = get_ssm_param("lambda_function_name_url")

SERVER_LOCAL = get_ssm_param('SERVER_LOCAL')
AUTH0_CALLBACK = get_ssm_param('AUTH0_CALLBACK')
AUTH0_CALLBACK_URL = f"{SERVER_LOCAL}{AUTH0_CALLBACK}"
AUTH0_CLIENT_ID = get_ssm_param('AUTH0_CLIENT_ID')
AUTH0_CLIENT_SECRET = get_ssm_param('AUTH0_CLIENT_SECRET')
AUTH0_DOMAIN = get_ssm_param('AUTH0_DOMAIN')
AUTH0_BASE_URL = 'https://' + AUTH0_DOMAIN
AUTH0_AUDIENCE = ""
JWT_PAYLOAD = get_ssm_param('JWT_PAYLOAD')
PROFILE_KEY = get_ssm_param('PROFILE_KEY')
AUTH0M_CLIENT_ID = get_ssm_param('AUTH0M_CLIENT_ID')
AUTH0M_CLIENT_SECRET = get_ssm_param('AUTH0M_CLIENT_SECRET')
AUTH0MAUDIENCE = get_ssm_param('AUTH0MAUDIENCE')

SECRET_KEY = str(uuid.uuid4())

hashids = Hashids()
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
dynamodb_table = "QuotesM"
DynamoDBTable = dynamodb.Table(dynamodb_table)

class Config(object):
    """Base config, uses staging database server."""
    SECRET_KEY = SECRET_KEY

    @property
    def DATABASE_URI(self):         # Note: all caps
        return 'sqlite:///:memory:'

class ProductionConfig(Config):
    """Uses production database server."""
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

# ######################## APP PREP #####################################

# # create and configure the app
application = Flask(__name__)

if ENV == 'DEV':
    # load the dev config
    application.config.from_object(DevelopmentConfig())
else:
    # load the prod config
    application.config.from_object(ProductionConfig())

oauth = OAuth(application)

auth0 = oauth.register(
    'auth0',
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    api_base_url=AUTH0_BASE_URL,
    access_token_url=AUTH0_BASE_URL + '/oauth/token',
    authorize_url=AUTH0_BASE_URL + '/authorize',
    client_kwargs={
        'scope': 'openid profile email',
    },
)

@application.errorhandler(Exception)
def handle_auth_error(ex):
    response = jsonify(message=str(ex))
    response.status_code = (ex.code if isinstance(ex, HTTPException) else 500)
    return response

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if PROFILE_KEY not in session:
            return redirect('/login')
        return f(*args, **kwargs)

    return decorated

# ######################## HELPER FUNCTIONS #####################################

def merge(shared_key, *iterables):
    """
    Merges two or more dictionaries based on a shared key
    Returns single merged dictionary
    """
    result = defaultdict(dict)
    for dictionary in itertools.chain.from_iterable(iterables):
        result[dictionary[shared_key]].update(dictionary)
        for dictionary in result.values():
            dictionary.pop(shared_key)
    return result


def getquotes(quote_id, user_id):
    """
    Takes a unique quote id and scans dynamodb for that quotes meta data 
    returns a new dict with the PK as primary keys and the full meta data as the value
    """
    key_to_be_deleted = ["SK", "GSI1"]
    L4ID = user_id[-4:]
    last4unique_userid = f"quotetrxn_{quote_id}_{L4ID}"

    quote_list = DynamoDBTable.scan(
        FilterExpression=Attr('PK').eq(
            str(quote_id)) & (Attr('SK').eq(last4unique_userid) | Attr('SK').eq('meta'))
    )
    quote_dict = merge("PK", quote_list['Items'])[quote_id]

    for key_ in key_to_be_deleted:
        quote_dict.pop(key_)

    quote_dict_merged = {**quote_dict['QuoteData'], **quote_dict['VoteData']}
    return quote_dict_merged


def getusertrxns(user_id):
    """
    Takes a unique user id and scans dynamodb for all quotes recieved by that user and the associated meta data
    returns a list of quote ids and a new dict with PK as primary keys and the full meta data as the value
    """
    quotetrxnitems = DynamoDBTable.scan(
        FilterExpression=Attr('GSI1').eq(str(user_id))
    )
    quotetrxn = quotetrxnitems['Items']
    quote_ids = getusersquotes(quotetrxn)

    return quote_ids


def getusersquotes(quotetrxn):
    """
    Takes a quote trxn result from DynamoDB Scan and extracts all unique quote PKs 
    """
    quote_ids = []
    for item in quotetrxn:
        quote_ids.append(item["PK"])

    return quote_ids


def create_usertable_info(user_id):
    """
    Returns a dict with all the needed info to populate frontend user table showing key information about
    the quotes they received and thier responses to the quotes if any
    """
    user_quote_list = []
    quote_ids = getusertrxns(user_id)

    for id in quote_ids:
        quote_items = getquotes(id, user_id)
        user_quote_list.append(quote_items)

    return user_quote_list

# ######################## ROUTES #####################################

@application.route('/')
def home():
    return render_template('index.html')

@application.route('/callback')
def callback_handling():
    auth0.authorize_access_token()
    resp = auth0.get('userinfo')
    userinfo = resp.json()

    session[JWT_PAYLOAD] = userinfo
    session[PROFILE_KEY] = {
        'user_id': userinfo['sub'],
        'name': userinfo['name'],
        'nickname': userinfo['https://motime.com/name'],
        'picture': userinfo['picture'],
        'phone_number': userinfo['https://motime.com/phone_number']
    }
    
    return redirect('/dashboard')

@application.route('/login')
def login():
    return auth0.authorize_redirect(redirect_uri=AUTH0_CALLBACK_URL, audience=AUTH0_AUDIENCE)

@application.route('/logout')
def logout():
    session.clear()
    params = {'returnTo': url_for(
        'home', _external=True), 'client_id': AUTH0_CLIENT_ID}
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))

@application.route('/dashboard')
@requires_auth
def dashboard():
    userinfo = session[PROFILE_KEY]
    id = userinfo['user_id']
    quote_info = create_usertable_info(id)
    return render_template('dashboard.html',
                           userinfo=session[PROFILE_KEY], quote_info=quote_info,
                           userinfo_pretty=json.dumps(session[JWT_PAYLOAD], indent=4))


# if __name__ == "__main__":
#     application.run(debug=True, use_reloader=False)
