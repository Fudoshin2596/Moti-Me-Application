from flask import request
from twilio.rest import Client
from database.manage_db import Manage_db
from twilio.twiml.messaging_response import MessagingResponse
from pyngrok import ngrok
import os
from dotenv import load_dotenv
load_dotenv()


class TwilioClient():
    def __init__(self, quote=None, author=None, recipient=None):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.client = Client(self.account_sid, self.auth_token)
        self.recipient = recipient
        self.sender = os.getenv("TWILIO_PHONE_NUMBER")
        self.quote = quote
        self.author = author

    def format(self):
        if self.author is None:
            body = self.quote
        else:
            body = f"{self.quote} | Author: {self.author}"
        return body

    def send_sms(self):
        """ sends quote using twilio API"""
        body = self.format()
        message = self.client.messages.create(
            to=self.recipient,
            from_=self.sender,
            body=body
            )
        print("TwilioClient sent a SMS")
        return message.sid

    def respond_to_sms(self):
        """ Sends response to inbound sms recieved, and saves details to database"""
        resp = MessagingResponse()
        sent_sms = self.client.messages.list(to=self.recipient, limit=1)
        for record in sent_sms:
            to_sid = record.sid
        from_sid = request.values.get('MessageSid', None)
        body = request.values.get('Body', None)
        DB = Manage_db(to_sid=to_sid)
        DB.modify_db(from_sid=from_sid, body=body)
        resp.message("Thanks, your feedback was recieved!")
        return str(resp)

    def incoming_sms(self, sid):
        """ Gets information from inbound sms"""
        message = self.client.messages(sid).fetch()
        body = message.body
        return body

    def start_ngrok(self):
        url = ngrok.connect(5000)
        print(' * Tunnel URL:', url)
        self.client.incoming_phone_numbers.list(
            phone_number=self.sender)[0].update(
                sms_url=url + '/rsms')
