# Primary imports
from dotenv import load_dotenv, find_dotenv
import os
import re
import json
import jsonpickle
import random
import requests
import logging
from collections import Counter

# third-party imports
from bs4 import BeautifulSoup as Soup
from twilio.rest import Client
import boto3
from boto3.dynamodb.conditions import Attr
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from dotenv import load_dotenv

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

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
Twitter_auth = os.getenv("Twitter_BEARER_TOKEN")
XRAPIDURL = os.getenv('XRAPIDURL')
xrapidapihost = os.getenv('XRAPIDHOST')
xrapidapikey = os.getenv('XRAPIDKEY')
UserPoolId = os.getenv("USER_POOL_ID")
prediction_lambda_url = os.getenv("lambda_function_name_url")

logger.info('## ENVIRONMENT VARIABLES\r' + jsonpickle.encode(dict(**os.environ)))

######################## GLOBAL RESCOURSES #####################################

dynamodb_table = "QuoteDB"

clientlb = boto3.client('lambda')
clientlb.get_account_settings()

clientdb = boto3.client('dynamodb')
cognitoclient = boto3.client('cognito-idp')

dynamodb = boto3.resource('dynamodb')
DynamoDBTable = dynamodb.Table(dynamodb_table)


TwilioClient = Client(account_sid, auth_token)


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
        cl = random.choice([Quote_from_web1(), Quote_from_twitter()])
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


######################## get cognito user ######################################
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
    response = cognitoclient.list_users(
        UserPoolId=UserPoolId,
        AttributesToGet=['email', 'phone_number'],
        Filter="status = 'Enabled'"
    )

    for i, user in enumerate(response["Users"]):
        id = user["Username"]
        email = user["Attributes"][1]["Value"]
        num = re.findall(r"[0-9]*$", user["Attributes"][0]["Value"])[0]
        user_info.append({"email": email, "id": id, "number": num, "event": event})

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
        from: twilio number
    }
    """
    event_dict = {}

    quote = event["event"]["quote"]
    author = event["event"]["author"]
    to = event["number"]

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
        sid: outbound api sms sid
    }
    """
    message = TwilioClient.messages.create(
        to=event["to"],
        from_=event["from"],
        body=event["body"]
        )
    event["sid"] = message.sid

    update_logger([f"Event: {event}", "TwilioClient sent a SMS", event["sid"]])
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
    quote = event["quote"]
    author = event["author"]
    sid = event["sid"]
    quote_length = len(quote)
    num_unique_words = get_unique_words(quote)
    quote_category = get_quote_category(quote)

    res = clientdb.put_item(
      TableName=dynamodb_table,
      Item={
        'quote': {'S': quote},
        'author': {'S': author},
        'to_sid': {'S': sid},
        'quote_length': {'N': str(quote_length)},
        'num_unique_words': {'N': str(num_unique_words)},
        'from_sid': {'S': "na"},
        'vote': {'S': "na"},
        'quote_category': {'S': quote_category},
      })

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
