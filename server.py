#!/usr/bin/python3
#for timestamp
from datetime import datetime
# app management
from flask import Flask
from flask.globals import request
from flask.helpers import send_file
from flask.templating import render_template
from werkzeug.utils import secure_filename
import io
# aws
import boto3
# define resources
BUCKET_NAME = 'pkucharski'
SDB_DOMAIN_NAME = 'kucharskiSDB'
# start application
app = Flask(__name__)

# get S3
s3 = boto3.resource('s3', region_name='us-west-2')
# get bucket
bucket = s3.Bucket(BUCKET_NAME)
# get sqs
sqs = boto3.resource('sqs', region_name='us-west-2')
# get proper queue
queue = sqs.get_queue_by_name(QueueName='kucharskiSQS')
# get SimpleDataBase
sdb = boto3.client('sdb', region_name='us-west-2')

# create domain for SimpleDataBase if not existing
if SDB_DOMAIN_NAME not in sdb.list_domains()['DomainNames']:
    print('Creating SimpleDataBase domain {}'.format(SDB_DOMAIN_NAME))
    sdb.create_domain(DomainName=SDB_DOMAIN_NAME)

# logging to SimpleDataBase
def log_sdb(app, type, content):
    sdb.put_attributes(DomainName=SDB_DOMAIN_NAME, ItemName=str(datetime.utcnow()),
                       Attributes=[{
                           'Name': 'App',
                           'Value': str(app)
                       },
                           {
                               'Name': 'Type',
                               'Value': str(type)
                           },
                           {
                               'Name': 'Content',
                               'Value': str(content)
                           }])

# start main page
@app.route('/')
def UI_main():
    return render_template('index.html')

# handle uploading image
@app.route('/upload', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'GET':
        return render_template('file_send.html')
    if request.method == 'POST':
        file = request.files['file']
        filename = secure_filename(file.filename)
        s3.Object(BUCKET_NAME, filename).put(Body=file.read())
        return render_template('generic.html', title='Uploaded', body='Uploaded file')

# handle deleting image
@app.route('/delete', methods=['POST'])
def delete_images():
    for file in request.form.getlist('file'):
        s3.Object(BUCKET_NAME, file).delete()
    return render_template("generic.html", title='', body='Deleted')

# handle accessing image
@app.route('/getfile/<file>', methods=['GET'])
def get_image(file):
    log_sdb('webapp', 'Get file', file)
    f = io.BytesIO(s3.Object(BUCKET_NAME, file).get()['Body'].read())
    return send_file(f, mimetype='image/jpg')

# handle file processing (UI and message sending)
@app.route('/process', methods=['GET', 'POST'])
def process_images():
    if request.method == 'GET':
        filenames = list(filter(lambda x: not x.startswith('logs'),
                                map(lambda x: x.key, list(bucket.objects.all()))))
        return render_template('files.html', files=filenames)
    elif request.method == 'POST':
        log_sdb('webapp', 'Files to process', request.form.getlist('file'))
        for file in request.form.getlist('file'):
            queue.send_message(MessageBody=file)
        return render_template('generic.html', title='', body="Processing")


# handle logs displaying
@app.route('/logs')
def display_logs():
    items = sdb.select(
        SelectExpression='select * from `{}` where itemName() like \'%\' order by itemName() desc limit 500'.format(
            SDB_DOMAIN_NAME))
    return render_template('log.html', items=items['Items'], title='Log')

# starting server on 8080
if __name__ == '__main__':
    log_sdb('webapp', 'Starting', 'Started webapp')
    app.run(host='0.0.0.0', port=8080)
