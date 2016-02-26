#!/usr/bin/python3
from datetime import datetime
import io

import boto3
from flask import Flask
from flask.globals import request
from flask.helpers import send_file
from flask.templating import render_template
from werkzeug.utils import secure_filename

BUCKET_NAME = 'pkucharski'
SDB_DOMAIN_NAME = 'kucharskiSDB'

app = Flask(__name__)

s3 = boto3.resource('s3', region_name='us-west-2')
bucket = s3.Bucket(BUCKET_NAME)
sqs = boto3.resource('sqs', region_name='us-west-2')
queue = sqs.get_queue_by_name(QueueName='kucharskiSQS')
sdb = boto3.client('sdb', region_name='us-west-2')

if SDB_DOMAIN_NAME not in sdb.list_domains()['DomainNames']:
    print('Creating SDB domain {}'.format(SDB_DOMAIN_NAME))
    sdb.create_domain(DomainName=SDB_DOMAIN_NAME)


def log_simpledb(app, type, content):
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


@app.route('/')
def hello_world():
    return render_template('index.html')


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'GET':
        return render_template('file_send.html')
    if request.method == 'POST':
        file = request.files['file']
        filename = secure_filename(file.filename)
        s3.Object(BUCKET_NAME, filename).put(Body=file.read())
        return render_template('generic.html', title='Uploaded', body='Uploaded file')


@app.route('/process', methods=['GET', 'POST'])
def process_files():
    if request.method == 'GET':
        filenames = list(filter(lambda x: not x.startswith('logs'),
                                map(lambda x: x.key, list(bucket.objects.all()))))
        return render_template('files.html', files=filenames)
    elif request.method == 'POST':
        log_simpledb('webapp', 'Files to process', request.form.getlist('file'))
        # print(request.form.getlist('file'))
        for file in request.form.getlist('file'):
            queue.send_message(MessageBody=file)
        return render_template('generic.html', title='', body="Processing")


@app.route('/delete', methods=['POST'])
def delete_files():
    for file in request.form.getlist('file'):
        s3.Object(BUCKET_NAME, file).delete()
    return render_template("generic.html", title='', body='Deleted')


@app.route('/getfile/<file>', methods=['GET'])
def get_image(file):
    # print(file)
    log_simpledb('webapp', 'Get file', file)
    f = io.BytesIO(s3.Object(BUCKET_NAME, file).get()['Body'].read())
    return send_file(f, mimetype='image/jpg')


@app.route('/logs')
def show_logs():
    items = sdb.select(
        SelectExpression='select * from `{}` where itemName() like \'%\' order by itemName() desc limit 500'.format(
            SDB_DOMAIN_NAME))
    return render_template('log.html', items=items['Items'], title='Log')


if __name__ == '__main__':
    log_simpledb('webapp', 'Starting', 'Started webapp')
    app.run(host='0.0.0.0', port=8080)
