# Primary imports
import os
import re
import json
import jsonpickle
import random
from random import randint
import requests
import logging
import http.client
import itertools
from collections import Counter, defaultdict

# third-party imports
from bs4 import BeautifulSoup as Soup
from twilio.rest import Client
import boto3
from boto3.dynamodb.conditions import Attr
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from dotenv import load_dotenv
from hashids import Hashids

# helpers
load_dotenv()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
patch_all()


def json_response(data, response_code=200):
    return json.dumps(data), response_code, {'Content-Type': 'application/json'}


def update_logger(data_list):
    for item in data_list:
        logger.info(jsonpickle.encode(item))

#################### GLOBAL ENV VARIBLES #######################################
# AWS SSM encrypted parameter store
ssm = boto3.client('ssm')

def get_ssm_param(param_name: str, required: bool = True) -> str:
    """Get an encrypted AWS Systems Manger secret."""
    response = ssm.get_parameters(
        Names=[param_name],
        WithDecryption=True,
    )
    if not response['Parameters'] or not response['Parameters'][0] or not response['Parameters'][0]['Value']:
        if not required:
            return None
        raise Exception(
            f"Configuration error: missing AWS SSM parameter: {param_name}")
    return response['Parameters'][0]['Value']


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

logger.info('## ENVIRONMENT VARIABLES\r' + jsonpickle.encode(dict(**os.environ)))

######################## GLOBAL RESCOURSES #####################################
hashids = Hashids()

dynamodb_table = "QuotesM"

clientlb = boto3.client('lambda')
clientlb.get_account_settings()

clientdb = boto3.client('dynamodb')
cognitoclient = boto3.client('cognito-idp')

dynamodb = boto3.resource('dynamodb')
DynamoDBTable = dynamodb.Table(dynamodb_table)

TwilioClient = Client(account_sid, auth_token)

######################## HELPER FUNCTIONS #####################################


def getMGMT_API_ACCESS_TOKEN():
    conn = http.client.HTTPSConnection(AUTH0_DOMAIN)
    load = {
        "client_id": AUTH0M_CLIENT_ID,
        "client_secret": AUTH0M_CLIENT_SECRET,
        "audience": AUTH0MAUDIENCE,
        "grant_type": "client_credentials"
    }
    payload = json.dumps(load)

    headers = {'content-type': "application/json"}

    conn.request("POST", "/oauth/token", payload, headers)

    res = conn.getresponse()
    data = json.loads(res.read().decode('utf-8'))
    return data['access_token']


def get_all_users_fromAuth0(test=False):
    user_info = []
    conn = http.client.HTTPSConnection(AUTH0_DOMAIN)

    TOKEN = getMGMT_API_ACCESS_TOKEN()
    MGMT_API_ACCESS_TOKEN = f"Bearer {TOKEN}"

    headers = {'Authorization': MGMT_API_ACCESS_TOKEN}

    url = f"https://{AUTH0_DOMAIN}/api/v2/users?sort=created_at%3A1&search_engine=v3"
    conn.request("GET", url, headers=headers)

    res = conn.getresponse()
    users = json.loads(res.read().decode('utf-8'))

    for user in users:
        user_info.append(
            {
                'email': user['email'],
                'id': user['user_id'],
                'number': re.findall(r"[0-9]*$", user['user_metadata']['phone_number'])[0],
            }
        )

    if test:
        return json.dumps(user_info, indent=4)

    return user_info


def get_user_fromAuth0(user_id, event, context="", test=False):
    """
    return list of users with dict of user info and quote
    [
        {
        email: email,
        id: username,
        number: number,
        event:
            {
                author: author,
                quote: quote
            }
        }
    ]
    """
    user_info = []
    conn = http.client.HTTPSConnection(AUTH0_DOMAIN)

    TOKEN = getMGMT_API_ACCESS_TOKEN()
    MGMT_API_ACCESS_TOKEN = f"Bearer {TOKEN}"

    headers = {'Authorization': MGMT_API_ACCESS_TOKEN}

    url = f"https://{AUTH0_DOMAIN}/api/v2/users/{user_id}"
    conn.request("GET", url, headers=headers)

    res = conn.getresponse()
    data = json.loads(res.read().decode('utf-8'))

    user_info.append(
        {
            'email': data['email'],
            'id': data['user_id'],
            'number': re.findall(r"[0-9]*$", data['user_metadata']['phone_number'])[0],
            'event': event
        }
    )

    if test:
        return json.dumps(user_info, indent=4)

    return user_info


def get_unique_words(quote):
    quote_list = re.split('[' ', ;, \., :, \n, \t]', quote)
    quote_list = [x for x in quote_list if x]  # remove empty strings
    counter = Counter(quote_list)
    return len(counter)


def modify(quote_obj):
    for i in quote_obj:
        quote = i['QuoteData']['quote']["S"]
        i['QuoteData']["quote_length"] = {"N": len(quote)}
        i['QuoteData']["unique_words"] = {"N": get_unique_words(quote)}
    return quote_obj


def merge(shared_key, *iterables):
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
    quote_ids = []
    for item in quotetrxn:
        quote_ids.append(item["PK"])

    return quote_ids


def create_usertable_info(user_id):
    user_quote_list = []
    quote_ids = getusertrxns(user_id)

    for id in quote_ids:
        quote_items = getquotes(id, user_id)
        user_quote_list.append(quote_items)

    return user_quote_list


def get_quote_category(quote):
    payload = f'{{ "payload": "{quote}" }}'
    res = requests.post(prediction_lambda_url, data=payload)
    response_info = json.loads(res.content)['body']
    return response_info.strip('"')


def add_data_to_db(event, context=""):
    """
    returns Dynamo DB put response
    """
    user_id = event["user_id"]
    PK = hashids.encode(randint(525, 98524))
    L4ID = user_id[-4:]
    SK = f"quotetrxn_{PK}_{L4ID}"
    quote = event["quote"]
    author = event["author"]
    to_sid = event["to_sid"]
    quote_length = len(quote)
    num_unique_words = get_unique_words(quote)
    quote_category = get_quote_category(quote)

    put_quote_res = clientdb.put_item(
        TableName=dynamodb_table,
        Item={
            "PK": {"S": PK},
            "SK": {"S": 'meta'},
            "QuoteData": {"M": {
                "quote": {"S": quote},
                "author": {"S": author},
                "category": {"S": quote_category},
                "quote_length": {"N": str(quote_length)},
                "unique_words": {"N": str(num_unique_words)}
            }}
        })

    put_trxn_res = clientdb.put_item(
        TableName=dynamodb_table,
        Item={
            "PK": {"S": PK},
            "SK": {"S": SK},
            "GSI1": {"S": user_id},
            "VoteData": {"M": {
                "to_sid": {"S": to_sid},
                "from_sid": {"S": "TBD"},
                "vote": {"S": "TBD"}
            }}
        })

    return (put_quote_res, put_trxn_res)

######################## get quote class #######################################
class Quotes():
    def getInfo(self):
        author, quote = self.get_quote()
        return author, quote

    def make_event(self):
        """
        formats quote into a lambda event structure
        """
        event_dict = {}
        quote = ""
        while quote == "":
            aut, quote = self.get_quote()
        event_dict["author"] = aut
        event_dict["quote"] = quote
        return event_dict

    def catch(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (TypeError, AttributeError) as e:
            pass


class Quote_from_web1(Quotes):
    def __init__(self):
        self.baseurl = 'https://www.greatest-quotations.com/search/quotes_popular.html'
        self.soup = self.make_soup(self.baseurl)

    def make_soup(self, url):
        resfromsource = requests.get(url)
        source_html_page = resfromsource.content
        soup = Soup(source_html_page, "lxml")
        return soup

    def max_page(self):
        table = self.soup.find(attrs={"class": "pageslist pageslist-right"})
        counter = Counter(table.find_all('a', href=True))
        return len(counter)

    def random_search_url(self):
        mp = self.max_page()
        page = random.choice(range(mp))
        random_page = f"{self.baseurl}?page={page}"
        return random_page

    def get_quote(self):
        url = self.random_search_url()
        new_soup = self.make_soup(url)
        ls = [self.catch(lambda: {tag.find('img', alt=True)['alt']: tag.find(attrs={"class": "fbquote"}).text}) for tag in new_soup.ul.find_all("li", recursive=True)]
        choice = random.choice(list(filter(None, ls)))
        for aut, quote in choice.items():
            return aut, quote


class Quote_from_web2(Quotes):
    def __init__(self):
        self.baseurl = 'https://www.successories.com/iquote/category/'
        self.sourceurl = 'https://www.successories.com/iquote/categories/most'

    def make_soup(self, url):
        resfromsource = requests.get(url)
        source_html_page = resfromsource.content
        soup = Soup(source_html_page, "lxml")
        return soup

    def get_cats(self, soup):
        dict = {}
        table = soup.find(attrs={"class": "quotedb_navresults"})
        for link in table.find_all("a"):
            dict[link.text] = re.search('(?<=\/category\/).*[^\][\/\d*$]', link.get("href")).group(0)
        return dict

    def max_page(self, soup):
        list = []
        table = soup.find(attrs={"class": "pager"})
        for link in table.find_all("li"):
            list.append(link.text)
        list2 = [item for subitem in list for item in subitem.split() if item.isdigit()]
        return max(list2)

    def random_search_url(self, categories_dict):
        cat = random.choice(list(categories_dict))
        random_cat = self.baseurl+categories_dict[cat]
        random_page = self.make_soup(random_cat)
        page = random.choice(range(1, int(self.max_page(random_page))))
        return self.baseurl+categories_dict[cat]+"/"+str(page)

    def randomize(self):
        soup = self.make_soup(self.sourceurl)
        categories_dict = self.get_cats(soup)
        url = self.random_search_url(categories_dict)
        return url

    def get_quote(self):
        url = self.randomize()
        soup = self.make_soup(url)
        dict = {}
        table = soup.find(attrs={"class": "quotedb_quotelist"})
        for link in table.find_all(attrs={"class": "quotebox"}):
            quote_link = link.find(attrs={"class": "quote"})
            author_link = link.find(attrs={"class": "author"})
            auth = re.search('(?<=Author:).[^\s]+', author_link.text).group(0)
            dict[auth] = quote_link.text
        aut = random.choice(list(dict))
        quote = dict[aut]
        # print('Grabbing new quote from_web')
        return aut, quote


class Quote_from_Api(Quotes):
    def __init__(self):
        self.url = XRAPIDURL
        self.querystring = {"language_code": "en"}
        self.headers = {
            'x-rapidapi-host': xrapidapihost,
            'x-rapidapi-key': xrapidapikey
            }

    def get_response(self):
        response = requests.get(self.url, headers=self.headers, params=self.querystring)
        res = json.loads(response.text)
        return res

    def get_quote(self):
        res = self.get_response()
        quote = res['content']
        aut = res['originator']['name']
        return aut, quote


class Quote_from_twitter(Quotes):
    def __init__(self):
        self.auth = Twitter_auth
        self.headers = {"Authorization": "Bearer {}".format(self.auth)}

    def create_url(self):
        """
            # Tweet fields are adjustable.
            # Options include:
                # attachments, author_id, context_annotations,
                # conversation_id, created_at, entities, geo, id,
                # in_reply_to_user_id, lang, non_public_metrics, organic_metrics,
                # possibly_sensitive, promoted_metrics, public_metrics, referenced_tweets,
                # source, text, and withheld
        """
        target_list = ['MomentumdashQ', 'LeadershipQuote', 'BrainyQuote', 'UpliftingQuotes', 'GreatestQuotes']
        target = random.choice(target_list)
        query = f"from:{target}"
        tweet_fields = "tweet.fields=text"
        url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&{tweet_fields}"
        return url

    def connect_to_endpoint(self, url, headers):
        response = requests.request("GET", url, headers=headers)
        if response.status_code != 200:
            raise Exception(response.status_code, response.text)
        return response.json()

    def get_tweet(self):
        working = False
        tweets_quote = []
        tweets_aut = []
        while working is False:
            try:
                url = self.create_url()
                json_response = self.connect_to_endpoint(url, self.headers)
                for response in json_response['data']:
                    regex_q = r'(.*?)(?=(\-|\"|\~))'
                    regex_a = r'(?<=(\-|\~))(.*?)(?=(\#|\"|(http)|\n|\@))'
                    test_str = response['text']
                    try:
                        quote = re.search(regex_q, test_str).group(0)
                    except AttributeError:
                        continue
                    try:
                        aut = re.search(regex_a, test_str).group(0)
                    except AttributeError:
                        aut = None
                    tweets_quote.append(quote)
                    tweets_aut.append(aut)
                working = True
            except KeyError:
                working = False
        tweets_list = [(x, y) for x in tweets_quote for y in tweets_aut]
        return tweets_list

    def get_quote(self):
        tweet_list = self.get_tweet()
        quotetup = random.choice(tweet_list)
        quote = quotetup[0]
        aut = quotetup[1]
        return aut, quote


######################## get quote function ####################################
def lambda_handlergq(event, context):
    """
    return dict
    {
    quote: quote
    author: author
    }
    """
    SENTINAL = True
    while SENTINAL:
        cl = random.choice(
            [Quote_from_web1(), Quote_from_web2(), Quote_from_Api(), Quote_from_twitter()])
        newevent = cl.make_event()
        quote = newevent["quote"]
        SENTINAL = check_if_in_db(quote)
    update_logger([newevent])
    return newevent


def check_if_in_db(quote):
    """
    returns Bool, whether quote already in Dynamodb table
    """
    resp = DynamoDBTable.scan(
        FilterExpression=Attr('quote').eq(str(quote))
    )
    if len(resp['Items']) > 0:
        return True
    else:
        return False


######################## get Auth0 user ######################################
def lambda_handlergu(event, context):
    """
    return list of users with dict of user info and quote
    [
        {
        email: email,
        id: username,
        number: number,
        event:
            {
                author: author,
                quote: quote
            }
        }
    ]
    """
    user_info = []
    # response = cognitoclient.list_users(
    #     UserPoolId=UserPoolId,
    #     AttributesToGet=['email', 'phone_number'],
    #     Filter="status = 'Enabled'"
    # )
    response = get_all_users_fromAuth0()

    for i, user in enumerate(response):
        id = user["id"]
        email = user['email']
        num = user['number']
        user_info.append(
            {"email": email, "user_id": id, "number": num, "event": event})

    update_logger([response, user_info])
    return user_info


########## create twilio event with info needed to send sms ####################
def lambda_handlerte(event, context):
    """
    returns dict
    {
        body: quote | author,
        quote: quote,
        author: author,
        account_sid: account_sid,
        auth_token: auth_token,
        to: number,
        from: twilio number,
        user_id: id
    }
    """
    event_dict = {}

    quote = event["event"]["quote"]
    author = event["event"]["author"]
    to = event["number"]
    user_id = event["user_id"]

    if author is None:
        event_dict["body"] = quote
    else:
        event_dict["body"] = f"{quote} | Author: {author}"

    event_dict["quote"] = quote
    event_dict["author"] = author
    event_dict["account_sid"] = account_sid
    event_dict["auth_token"] = auth_token
    event_dict["to"] = to
    event_dict["from"] = TWILIO_PHONE_NUMBER
    event_dict["user_id"] = user_id

    update_logger([event_dict])
    return event_dict


####################### send twilio sms ########################################
def lambda_handlerst(event, context):
    """
    returns dict
    {
        body: quote | author,
        quote: quote,
        author: author,
        account_sid: account_sid,
        auth_token: auth_token,
        to: number,
        from: twilio number,
        to_sid: outbound api sms sid
        user_id: id
    }
    """
    message = TwilioClient.messages.create(
        to=event["to"],
        from_=event["from"],
        body=event["body"]
    )
    event["to_sid"] = message.sid

    update_logger(
        [f"Event: {event}", "TwilioClient sent a SMS", event["to_sid"]])
    return event


######################### save quote in db #####################################
def get_unique_words(quote):
    quote_list = re.split('[' ', ;, \., :, \n, \t]', quote)
    quote_list = [x for x in quote_list if x]
    counter = Counter(quote_list)
    return len(counter)


def get_quote_category(quote):
    payload = f'{{ "payload": "{quote}" }}'
    res = requests.post(prediction_lambda_url, data=payload)
    response_info = json.loads(res.content)['body']
    return response_info.strip('"')


def lambda_handlerdb(event, context):
    """
    returns Dynamo DB put response
    """
    # quote = event["quote"]
    # author = event["author"]
    # sid = event["sid"]
    # quote_length = len(quote)
    # num_unique_words = get_unique_words(quote)
    # quote_category = get_quote_category(quote)

    # res = clientdb.put_item(
    #     TableName=dynamodb_table,
    #     Item={
    #         'quote': {'S': quote},
    #         'author': {'S': author},
    #         'to_sid': {'S': sid},
    #         'quote_length': {'N': str(quote_length)},
    #         'num_unique_words': {'N': str(num_unique_words)},
    #         'from_sid': {'S': "na"},
    #         'vote': {'S': "na"},
    #         'quote_category': {'S': quote_category},
    #     })
    res = add_data_to_db(event)

    update_logger([res])
    return res


#################### PROGRAMATTIC STATEMACHINE #################################
def lambda_handler(event, context):
    # first get unique quote
    unique_quote = lambda_handlergq("", context)
    # next get list of active Users
    list_of_active_users = lambda_handlergu(unique_quote, context)
    # The for each user send quote and save it to DynamoDB
    for user in list_of_active_users:
        # get meta info needed to send twilio message
        meta_data_for_twilio = lambda_handlerte(user, context)
        # send twilio message to single users
        twilio_sent_response = lambda_handlerst(meta_data_for_twilio, context)
        # save info in dynamodb
        dynamo_event = lambda_handlerdb(twilio_sent_response, context)

    update_logger([dynamo_event])
    return json_response(dynamo_event)

################################################################################


# if __name__ == '__main__':
#     outcome = lambda_handler("", "")
#     print(outcome)
