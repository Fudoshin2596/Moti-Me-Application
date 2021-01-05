from __future__ import print_function
from twilio.twiml.messaging_response import MessagingResponse
import boto3
from boto3.dynamodb.conditions import Attr
from twilio.rest import Client
import requests
import json

######################## GLOBAL RESCOURSES #####################################

# AWS SSM encrypted parameter store
ssm = boto3.client('ssm')
dynamodb_table = 'QuotesM'
dynamodb = boto3.resource('dynamodb')
DynamoDBTable = dynamodb.Table(dynamodb_table)


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


# The session object makes use of a secret key.
TWILIO_ACCOUNT_SID = get_ssm_param('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = get_ssm_param('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = get_ssm_param('TWILIO_PHONE_NUMBER')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


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


def update_quotetrxn(data):
    to_sid = data['to_sid']
    vote = data['vote']
    from_sid = data['from_sid']

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

    print(f"This is the DynamoDB response: {response}")
    return response


def new_func(to_number, from_number, from_sid, vote):
    """Respond with the number of text messages sent between two parties."""
    sids = []

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json?From={from_number}&To={to_number}&PageSize=4"
    print(url)

    r = requests.get(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    messages = json.loads(r.content)['messages']
    print(messages)

    for outbound in messages:
        print(outbound)
        if outbound['direction'] == 'outbound-api':
            sids.append(outbound['sid'])

    try:
        to_sid = sids[0]
        data = {
            'to_sid': to_sid,
            'from_sid': from_sid,
            'vote': vote
        }
        print(
            f'success with API fetch, this is the sid we are checking DB for: {to_sid}')

        _ = update_quotetrxn(data)
        print(
            f"Received '{vote}' from: {from_number} | with from sid: {from_sid}, in response to_sid {to_sid}")
        return "Thanks, your feedback has been recieved"
    except Exception as e:
        return f'Could not make API call to Twilio, got error {e}'


def lambda_handler(event, context):
    resp = MessagingResponse()
    print("Received event: " + str(event))

    to_number = event["From"]
    from_number = event["To"]
    vote = event["Body"]
    from_sid = event["MessageSid"]

    print("testing update function now!")

    response_msg = new_func(to_number, from_number, from_sid, vote)

    print("Done with update function")
    resp.message(response_msg)
    return str(resp)

# if __name__ == '__main__':
#     import pprint
#     import sys

#     event = {
#         "Body": "",
#         "MessageSid": "",
#         "From": "",
#         "To": ""
#     }

#     response = lambda_handler(event, None)
#     pprint.pprint(response)
