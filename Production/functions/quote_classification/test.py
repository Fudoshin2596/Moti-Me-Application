import requests
import json
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

url = os.getenv("lambda_function_name_url")
quote = "I saw the best minds of my generation destroyed by madness, starving hysterical naked."
payload = f'{{ "payload": "{quote}" }}'
res = requests.post(url, data=payload)
response_info = json.loads(res.content)['body']
print(response_info)
