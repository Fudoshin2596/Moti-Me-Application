# Primary imports
import os
import json
import jsonpickle
import logging

# third-party imports
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

logger.info('## ENVIRONMENT VARIABLES\r' +
            jsonpickle.encode(dict(**os.environ)))

######################## GLOBAL RESCOURSES #####################################

clientlb = boto3.client('lambda')
clientlb.get_account_settings()

dynamodb_table = 'QuotesM'
dynamodb = boto3.resource('dynamodb')
DynamoDBTable = dynamodb.Table(dynamodb_table)

TwilioClient = Client(account_sid, auth_token)

#################################################################################

def update_logger(data_list):
    for item in data_list:
        logger.info(jsonpickle.encode(item))
    
def _get_response(msg):
    xml_response = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{msg}</Message></Response>"
    update_logger([f"XML response: {xml_response}"])
    return xml_response

def getusertrxn(to_sid):
    """
    Takes a unique user id and scans dynamodb for all quotes recieved by that user and the associated meta data
    returns a list of quote ids and a new dict with PK as primary keys and the full meta data as the value
    """
    quotetrxnitem = DynamoDBTable.scan(
        FilterExpression=Attr('VoteData.to_sid').eq(to_sid))

    quotetrxn = quotetrxnitem['Items']
    PK = quotetrxn[0]['PK']
    SK = quotetrxn[0]['SK']

    return PK, SK


def update_quotetrxn(to_sid, vote, from_sid):
    PK, SK = getusertrxn(to_sid)

    response = DynamoDBTable.update_item(
        Key={
            'PK': PK,
            'SK': SK,
        },
        UpdateExpression="set VoteData.vote=:r, VoteData.from_sid=:a",
        ExpressionAttributeValues={
            ':r': vote,
            ':a': from_sid
        },
        ReturnValues="UPDATED_NEW"
    )
    return response


def resp_and_save(vote, from_sid, phone_number):
    """ Sends response to inbound sms recieved, and saves details to database"""
    sent_sms = TwilioClient.messages.list(to=phone_number, limit=4)
    for record in sent_sms:
        if record.direction == "outbound-api":
            to_sid = record.sid
            # print(f"this is the to_sid info {to_sid} with content {vote}")
            ue = update_quotetrxn(to_sid, vote, from_sid)
            update_logger([f"this is the to_sid info {to_sid}", ue])
            # print(f"this is the to_sid info {to_sid}")
            # print(ue)
            break
 
def lambda_handler(event, context=""):
    update_logger([f"this is the event: {event}"])

    phone_number = event["From"]
    vote = event["Body"]
    from_sid = event["MessageSid"]

    update_logger(["testing update function now!"])
    # print("testing update function now!")
    resp_and_save(vote, from_sid, phone_number)

    response_msg = "Thanks, your feedback has been recieved"
    update_logger(
        [f"Received '{vote}' from: {phone_number} | with sid: {from_sid}"])
    # print(f"Received '{vote}' from: {phone_number} | with sid: {from_sid}")

    return _get_response(response_msg)

# if __name__ == "__main__":
    # event = {'ToCountry': 'US', 'ToState': 'AL', 'SmsMessageSid': 'SMfabe16063d7c3bee42389a694a79ec70', 
    #         'NumMedia': '0', 'ToCity': 'OAKMAN', 'FromZip': '10011', 'SmsSid': 'SMfabe16063d7c3bee42389a694a79ec70', 
    #         'FromState': 'NY', 'SmsStatus': 'received', 'FromCity': 'NEW+YORK', 'Body': 'No', 'FromCountry': 'US', 'To': '%2B12056228196', 
    #         'ToZip': '35546', 'NumSegments': '1', 'MessageSid': 'SMfabe16063d7c3bee42389a694a79ec70', 'AccountSid': 'ACf332ed87ff1d38f604fc1415d41f6274', 
    #         'From': '%2B13479955684', 'ApiVersion': '2010-04-01'}

    # context = ""

    # out = lambda_handler(event, context)
    # print(out)
