# import external modules / libaries
import os
import random
from dotenv import load_dotenv, find_dotenv
from twilioclient import twilio
# import local modules
from quotes import quotes
from database.manage_db import Manage_db
from predict.classification import Classification_Transformer
from __init__ import create_app

load_dotenv(find_dotenv())

PATH = os.getenv('MODEL_PATH')
labels = ['thoughtful', 'emotional', 'personal', 'work', 'aspirations']


app = create_app()


def check_if_quote_exists():
    active = os.getenv('TWILIO_RECP')
    SENTINAL = "Exists"
    while SENTINAL == "Exists":
        quote_class = random.choice([quotes.Quote_from_web1(), quotes.Quote_from_web2(), quotes.Quote_from_twitter(), quotes.Quote_from_Api()])
        aut, quote = quote_class.getInfo()
        DB = Manage_db(quote=quote)
        if DB.check_db():
            SENTINAL = "Exists"
        else:
            SENTINAL = "Does not Exist"
    single_user = DB.get_users(active)
    twil = twilio.TwilioClient(quote=quote, author=aut, recipient=single_user)
    return twil, DB, aut, quote


def check_if_database_sparse(DB):
    if DB.get_size() <= 100:
        return True
    else:
        return False


def predict_user_pref():
    pass


def predict_catagory(PATH, labels, quote):
    """
    ML analysis on quote to decide what catagory to assign
    """
    num_labels = len(labels)
    if PATH:
        load_from_save = True
    else:
        load_from_save = False
    model = Classification_Transformer(num_labels=num_labels, load_from_save=load_from_save, model_path=PATH)
    ans = model.predict_ans(quote, labels)
    return ans


def send_and_save(aut, quote, twil, pred_cat):
    to_sid = twil.send_sms()
    DB = Manage_db(quote=quote, to_sid=to_sid, author=aut, catagory=pred_cat)
    DB.populate_db()
    twil.start_ngrok()


def flow():
    SENTINAL = 'Do not send'
    while SENTINAL == 'Do not send':
        twil, DB, aut, quote = check_if_quote_exists()
        pred_cat = predict_catagory(PATH, labels, quote)
        if check_if_database_sparse(DB):
            send_and_save(aut, quote, twil, pred_cat)
            SENTINAL = "SEND"
        else:
            if predict_user_pref(aut, quote):
                send_and_save(aut, quote, twil, pred_cat)
                SENTINAL = "SEND"
            else:
                SENTINAL = 'Do not send'


if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        flow()
    app.run(debug=True)
