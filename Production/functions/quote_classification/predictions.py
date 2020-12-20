import joblib
import logging
import boto3
from botocore.exceptions import ClientError
import os
from flask import Flask, render_template, request, redirect, send_file, url_for, json
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# env vars
BUCKET_NAME = os.getenv("BUCKET_NAME")
region_name = os.getenv("region_name")
aws_access_key_id = os.getenv("aws_access_key_id")
aws_secret_access_key = os.getenv("aws_secret_access_key")
aws_profile_name = os.getenv("aws_profile_name")

# session = boto3.Session()  # profile_name=aws_profile_name
s3 = boto3.client(service_name='s3', region_name=region_name,
                  aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

#local path/ s3 files
filename = 'text_classification.pkl'
MPATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'downloads')
MODEL_LOCAL_PATH = f'{MPATH}/{filename}'

app = Flask(__name__)
app.logger.setLevel(logging.ERROR)


@app.route('/', methods=['POST'])
def index():
  payload = json.loads(request.get_data().decode('utf-8'))
  prediction = predictfunc(payload['payload'])
  return {
      'statusCode': 200,
      'body': json.dumps(prediction)
  }


@app.route("/storage")
def storage():
    contents = list_files(BUCKET_NAME)
    return render_template('storage.html', contents=contents)

 
@app.route("/upload", methods=['POST'])
def upload():
    if request.method == "POST":
        f = request.files['file']
        f.save(f.filename)
        upload_file(f"{f.filename}", BUCKET_NAME)

        return redirect("/storage")


@app.route("/download/<filename>", methods=['GET'])
def download(filename):
    if request.method == 'GET':
        output = download_file(filename, BUCKET_NAME)

        return send_file(output, as_attachment=True)


def predictfunc(data, path=MODEL_LOCAL_PATH):
  pipeline = load_model(path)
  labels_text = ['aspirations', 'emotional', 'personal', 'thoughtful', 'work']
  ans = pipeline.predict([data])
  return labels_text[int(ans)]


def list_files(bucket, s3_client=s3):
  """
  Function to list files in a given S3 bucket
  """
  contents = []
  try:
    for item in s3_client.list_objects(Bucket=bucket)['Contents']:
        print(item)
        contents.append(item)
  except Exception as e:
    pass

  return contents


def upload_file(file_name, bucket, object_name=None,  s3_client=s3):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def download_file(file_name, bucket, s3_client=s3):
    """
    Function to download a given file from an S3 bucket
    """
    output = f"downloads/{file_name}"
    s3_client.download_file(bucket, file_name, output)

    return output


def load_model(path):
    # load the pipeline object
    pipeline = joblib.load(path)
    return pipeline


# if __name__ == '__main__':
    # app.run(debug=True)