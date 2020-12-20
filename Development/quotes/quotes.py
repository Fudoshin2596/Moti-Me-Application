import requests
import random
import re
import pandas as pd
from collections import Counter
from bs4 import BeautifulSoup as Soup
import os
import json
from dotenv import load_dotenv
load_dotenv()

Twitter_auth = os.getenv("Twitter_BEARER_TOKEN")
XRAPIDURL = os.getenv('XRAPIDURL')
xrapidapihost = os.getenv('XRAPIDHOST')
xrapidapikey = os.getenv('XRAPIDKEY')


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
