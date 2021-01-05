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


#################
# Flask configs
SECRET_KEY = 'xHhsZkr0Ajo4TRfPB81QNwjrVxlHpWfd'
FLASK_APP = 'application.py'
FLASK_ENV = 'development'
SERVER_LOCAL = 'http://localhost:3000/'
SERVER_PROD = 'http://motimefrontend-env.eba-5ihw4kgi.us-east-1.elasticbeanstalk.com/'

# Auth0
AUTH0_CLIENT_ID = 'UnSgI1mjRNql7vJwan8fcWl2tHF47Vdi'
AUTH0_DOMAIN = 'dev-376w9ix0.us.auth0.com'
AUTH0_CLIENT_SECRET = 'vF3zywhe0tyv7J09t_PhhmXaJ95KQBjDSJZ_zuHn3JDl_O3_dswtdJV5OZ9zzg21'
AUTH0_CALLBACK = 'callback'
AUTH0_AUDIENCE = ""
PROFILE_KEY = 'profile'
JWT_PAYLOAD = 'jwt_payload'

# Auth0 Mgmt api
AUTH0M_CLIENT_ID = '9fhVvKCubpj3z8DuFkWoD9sF0QChJz2a'
AUTH0M_CLIENT_SECRET = 'ycnMv89b-TBAwOxScngTQ6uL1ca8NbS8FDUPoshc5pgcvMnZMQBBWW_LX4kTfRgC'
AUTH0MAUDIENCE = "https://dev-376w9ix0.us.auth0.com/api/v2/"

# Tokens for Twilio Twitter
Twitter_API_KEY = "IMwr4e2eKCLNY7ksZkjCygiIj"
Twitter_API_SECRET = "v3rhjBml9gvrTy3DYZSdZDsLwnM2ENvbTjy54D4dmHea0QyO4E"
Twitter_BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAEocHAEAAAAAYSPA20OBX0wPQLVh900yye7%2FD%2Bs%3DU6whZLaa1AxDvFnqroQVxOAeeC6TXDxp5S1CXBZFkiOWRq04ZB"

# Tokens for Twilio
Target_number1 = "+13479955684"  # Joel's number
Target_number2 = "+17188090577"  # Ash's number
TWILIO_PHONE_NUMBER = "+12056228196"
TWILIO_ACCOUNT_SID = "ACf332ed87ff1d38f604fc1415d41f6274"
TWILIO_AUTH_TOKEN = "f3fe3f53e86d83170260bfdfa22a9582"
TWILIO_RECP = 'Test User'

# XRAPID
XRAPIDURL = "https://quotes15.p.rapidapi.com/quotes/random/"
XRAPIDHOST = "quotes15.p.rapidapi.com"
XRAPIDKEY = "6febe2776cmsh840e1df37a1deddp1df229jsn4ae2d256adca"

#AWS
dynamodb_table = "QuotesM"
AWS_ACCESS_KEY = "AKIAXRO5VIL535NVKNBU"
AWS_SECRET_KEY = "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"
lambda_function_name_url = 'https://57xcgue90i.execute-api.eu-central-1.amazonaws.com/dev'
FLASKS3_BUCKET_NAME = 'moti-me-dashboard'
FLASKS3_REGION = 'us-east-1'

#######################################
# ######################## GLOBAL RESCOURSES #####################################

# # AWS SSM encrypted parameter store
# ssm = boto3.client('ssm', region_name='us-east-1')

# def get_ssm_param(param_name, required=True):
#     """Get an encrypted AWS Systems Manger secret."""
#     response = ssm.get_parameters(
#         Names=[param_name],
#         WithDecryption=True,
#     )
#     if not response['Parameters'] or not response['Parameters'][0] or not response['Parameters'][0]['Value']:
#         if not required:
#             return None
#         raise Exception(
#             f"Configuration error: missing AWS SSM parameter: {param_name}")
#     return response['Parameters'][0]['Value']


# if ENV == 'DEV':
#     SERVER = os.getenv('SERVER_LOCAL')
# else:
#     SERVER = os.getenv('SERVER_PROD')
SERVER = SERVER_PROD
# AUTH0_CALLBACK = os.getenv('AUTH0_CALLBACK')
AUTH0_CALLBACK_URL = f"{SERVER}{AUTH0_CALLBACK}"
# AUTH0_CLIENT_ID = os.getenv('AUTH0_CLIENT_ID')
# AUTH0_CLIENT_SECRET = os.getenv('AUTH0_CLIENT_SECRET')
# AUTH0_DOMAIN = os.getenv('AUTH0_DOMAIN')
AUTH0_BASE_URL = 'https://' + AUTH0_DOMAIN
# AUTH0_AUDIENCE = ""
# JWT_PAYLOAD = os.getenv('JWT_PAYLOAD')
# PROFILE_KEY = os.getenv('PROFILE_KEY')
# AUTH0M_CLIENT_ID = os.getenv('AUTH0M_CLIENT_ID')
# AUTH0M_CLIENT_SECRET = os.getenv('AUTH0M_CLIENT_SECRET')
# AUTH0MAUDIENCE = os.getenv('AUTH0MAUDIENCE')

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


if __name__ == "__main__":
    application.run(debug=True, use_reloader=False)