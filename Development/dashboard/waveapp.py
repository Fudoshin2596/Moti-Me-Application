# Primary imports
from dotenv import load_dotenv, find_dotenv
import os
import json
import logging

# third-party imports
import boto3
from boto3.dynamodb.conditions import Attr, Key
from dotenv import load_dotenv
from h2o_wave import main, app, Q, ui, site

# helpers
load_dotenv()
logger = logging.getLogger()
logger.setLevel(logging.INFO)


######################## GLOBAL RESCOURSES #####################################

dynamodb_table = os.getenv("dynamodb_table")

clientdb = boto3.client('dynamodb')

dynamodb = boto3.resource('dynamodb')
DynamoDBTable = dynamodb.Table(dynamodb_table)

_id = 0

def dump_table(table_name):
    results = []
    last_evaluated_key = None
    while True:
        if last_evaluated_key:
            response = clientdb.scan(
                TableName=dynamodb_table,
                ExclusiveStartKey=last_evaluated_key
            )
        else:
            response = clientdb.scan(TableName=dynamodb_table)
        last_evaluated_key = response.get('LastEvaluatedKey')

        results.extend(response['Items'])

        if not last_evaluated_key:
            break
    return results


data = dump_table(dynamodb_table)
# print(json.dumps(data[0], indent=4))
# print(json.dumps(data[0]['quote']['S'], indent=4))

class Issue:
    def __init__(self, to_sid: str, from_sid: str, quote_category: str, quote_length: int, num_unique_words: int, vote: str, quote: str, author: str):
        global _id
        _id += 1
        self.id = f'I{_id}'
        self.to_sid = to_sid
        self.from_sid = from_sid
        self.quote = quote
        self.author = author
        self.quote_category = quote_category
        self.vote = vote
        self.quote_length = quote_length
        self.num_unique_words = num_unique_words


# # Create some issues
issues = [ Issue(
        to_sid=item['to_sid']['S'],
        from_sid=item['from_sid']['S'],
        quote=item['quote']['S'],
        author=item['author']['S'],
        quote_category=item['quote_category']['S'],
        vote=item['vote']['S'],
        quote_length=item['quote_length']['N'],
        num_unique_words=item['num_unique_words']['N'],
        ) 
        for item in data 
    ]

print(issues)

# # Create columns for our issue table.
columns = [
    ui.table_column(name='to_sid', label='To_Sid', sortable=False,
                    searchable=True, max_width='300'),
    ui.table_column(name='from_sid', label='From_Sid', sortable=False),
    ui.table_column(name='quote',
                    label='Quote', filterable=True),
    ui.table_column(name='author', label='Author', filterable=True),
    ui.table_column(name='quote_category', label='Category',
                    sortable=True, filterable=True),
    ui.table_column(name='vote', label='Vote',
                    sortable=True, filterable=True),
    ui.table_column(name='quote_length', label='Quote_Length',
                    sortable=True, data_type='number'),
    ui.table_column(name='num_unique_words', label='Unique_Words',
                    sortable=True, data_type='number')
]

sample_markdown = ''' # Welcome to Moti Me Home Page '''

@app('/')
async def serve(q: Q):
    hash = q.args['#']

    if hash == 'form':
        q.page['navigation'] = ui.form_card(box='1 1 -1 11', items=[
                                        ui.table(
                                            name='issues',
                                            columns=columns,
                                            rows=[ui.table_row(
                                                name=issue.id,
                                                cells=[issue.to_sid, issue.from_sid, issue.quote, issue.author,
                                                    issue.quote_category, issue.vote, str(issue.quote_length), str(issue.num_unique_words)]
                                            ) for issue in issues],
                                            groupable=True,
                                            downloadable=False,
                                            resettable=True,
                                            height='800px'
                                        ),
                                           ui.button(name='show_tabs', label='Back', primary=True),
                                    ])
    elif hash == 'home':
        q.page['navigation'] = ui.form_card(box='1 1 4 -1', items=[
            ui.text(sample_markdown),
            ui.button(name='show_tabs', label='Back', primary=True),
        ])
    else:
        q.page['navigation'] = ui.tab_card(
            box='1 1 4 1',
            items=[
                ui.tab(name='#home', label='Home'), 
                ui.tab(name='#form', label='Quote Table')
            ],
            link = True,
        )

    await q.page.save()
