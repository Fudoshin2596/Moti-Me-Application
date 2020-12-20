# Primary imports
import os
import jsonpickle
import logging

# third-party imports
from twilio.rest import Client
import boto3
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from dotenv import load_dotenv

# helpers
load_dotenv()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
patch_all()

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(account_sid, auth_token)

dynamodb_table = "QuoteDB"
table = boto3.resource('dynamodb').Table(dynamodb_table)


def update_logger(data_list):
    for item in data_list:
        logger.info(jsonpickle.encode(item))


def _get_response(msg):
    xml_response = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{msg}</Message></Response>"
    update_logger([f"XML response: {xml_response}"])
    return xml_response

def get_update_params(body):
    """Given a dictionary we generate an update expression and a dict of values
    to update a dynamodb table.
    Params:
        body (dict): Parameters to use for formatting.
    Returns:
        update expression, dict of values.
    """
    update_expression = ["set "]
    update_values = dict()

    for key, val in body.items():
        update_expression.append(f" {key} = :{key},")
        update_values[f":{key}"] = val

    return "".join(update_expression)[:-1], update_values


def update(body, key):
    a, v = get_update_params(body)
    response = table.update_item(
        Key={'to_sid': key},
        UpdateExpression=a,
        ExpressionAttributeValues=dict(v)
        )
    return response


def resp_and_save(vote, from_sid, phone_number):
    """ Sends response to inbound sms recieved, and saves details to database"""
    sent_sms = client.messages.list(to=phone_number, limit=2)
    for record in sent_sms:
        if record.direction == "outbound-api":
            to_sid = record.sid
            # print(f"this is the to_sid info {to_sid} with content {vote}")
            update_dict = {"vote": vote, "from_sid": from_sid}
            ue = update(update_dict, to_sid)
            update_logger([f"this is the to_sid info {to_sid}", ue])
            # print(f"this is the to_sid info {to_sid}")
            # print(ue)
            break


def lambda_handler(event, context):
    update_logger([ f"this is the event: {event}"])

    phone_number = event["From"]
    vote = event["Body"]
    from_sid = event["MessageSid"]

    update_logger(["testing update function now!"])
    # print("testing update function now!")
    resp_and_save(vote, from_sid, phone_number)

    response_msg = "Thanks, your feedback has been recieved"
    update_logger([f"Received '{vote}' from: {phone_number} | with sid: {from_sid}"])
    # print(f"Received '{vote}' from: {phone_number} | with sid: {from_sid}")

    return _get_response(response_msg)


# event = {'ToCountry': 'US', 'ToState': 'AL', 'SmsMessageSid': 'SMfabe16063d7c3bee42389a694a79ec70', 
#         'NumMedia': '0', 'ToCity': 'OAKMAN', 'FromZip': '10011', 'SmsSid': 'SMfabe16063d7c3bee42389a694a79ec70', 
#         'FromState': 'NY', 'SmsStatus': 'received', 'FromCity': 'NEW+YORK', 'Body': 'No', 'FromCountry': 'US', 'To': '%2B12056228196', 
#         'ToZip': '35546', 'NumSegments': '1', 'MessageSid': 'SMfabe16063d7c3bee42389a694a79ec70', 'AccountSid': 'ACf332ed87ff1d38f604fc1415d41f6274', 
#         'From': '%2B13479955684', 'ApiVersion': '2010-04-01'}

# context = ""

# out = lambda_handler(event, context)
# print(out)
