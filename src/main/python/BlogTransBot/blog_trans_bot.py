#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

from datetime import datetime
import time
import logging
import io
import os
import json

import boto3
import arrow
from newspaper import Article
from googletrans import Translator

LOGGER = logging.getLogger()
if len(LOGGER.handlers) > 0:
  # The Lambda environment pre-configures a handler logging to stderr.
  # If a handler is already configured, `.basicConfig` does not execute.
  # Thus we set the level directly.
  LOGGER.setLevel(logging.INFO)
else:
  logging.basicConfig(level=logging.INFO)

DRY_RUN = True if 'true' == os.getenv('DRY_RUN', 'true') else False

AWS_REGION = os.getenv('REGION_NAME', 'us-east-1')

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_OBJ_KEY_PREFIX = os.getenv('S3_OBJ_KEY_PREFIX', 'posts')

EMAIL_FROM_ADDRESS = os.getenv('EMAIL_FROM_ADDRESS')
EMAIL_TO_ADDRESSES = os.getenv('EMAIL_TO_ADDRESSES')
EMAIL_TO_ADDRESSES = [e.strip() for e in EMAIL_TO_ADDRESSES.split(',')]

TRANS_DEST_LANG = os.getenv('TRANS_DEST_LANG', 'ko')

MAX_SINGLE_TEXT_SIZE = 15*1204


def fwrite_s3(s3_client, doc, s3_bucket, s3_obj_key):
  output = io.StringIO()
  output.write(doc)

  ret = s3_client.put_object(Body=output.getvalue(),
    Bucket=s3_bucket,
    Key=s3_obj_key)

  output.close()
  try:
    status_code = ret['ResponseMetadata']['HTTPStatusCode']
    return (200 == status_code)
  except Exception as ex:
    return False


def gen_html(elem):
  HTML_FORMAT = '''<!DOCTYPE html>
<html>
<head>
<style>
table {{
  font-family: arial, sans-serif;
  border-collapse: collapse;
  width: 100%;
}}
td, th {{
  border: 1px solid #dddddd;
  text-align: left;
  padding: 8px;
}}
tr:nth-child(even) {{
  background-color: #dddddd;
}}
</style>
</head>
<body>
<h2>{title}</h2>
<table>
  <tr>
    <th>key</th>
    <th>value</th>
  </tr>
  <tr>
    <td>doc_id</th>
    <td>{doc_id}</td>
  </tr>
  <tr>
    <td>link</th>
    <td>{link}</td>
  </tr>
  <tr>
    <td>pub_date</th>
    <td>{pub_date}</td>
  </tr>
  <tr>
    <td>section</th>
    <td>{section}</td>
  </tr>
  <tr>
    <td>title_{lang}</th>
    <td>{title_trans}</td>
  </tr>
  <tr>
    <td>body_{lang}</th>
    <td>{body_trans}</td>
  </tr>
  <tr>
    <td>tags</th>
    <td>{tags}</td>
  </tr>
</table>
</body>
</html>'''


  html_doc = HTML_FORMAT.format(title=elem['title'],
    doc_id=elem['doc_id'],
    link=elem['link'],
    pub_date=elem['pub_date'],
    section=elem['section'],
    title_trans=elem['title_trans'],
    body_trans='<br/>'.join([e for e in elem['body_trans']]),
    tags=elem['tags'],
    lang=elem['lang'])

  return html_doc


def send_email(ses_client, from_addr, to_addrs, subject, html_body):
  ret = ses_client.send_email(Destination={'ToAddresses': to_addrs},
    Message={'Body': {
        'Html': {
          'Charset': 'UTF-8',
          'Data': html_body
        }
      },
      'Subject': {
        'Charset': 'UTF-8',
        'Data': subject
      }
    },
    Source=from_addr
  )
  return ret


def mk_translator(dest='ko'):
  for i in range(1, 7):
    try:
      translator = Translator()
      _ = translator.translate('Hello', dest=dest)
      return translator
    except Exception as ex:
      LOGGER.error(repr(ex))
      wait_time = min(pow(2, i), 60)
      LOGGER.info('retry to translate after %s sec' % wait_time)
      time.sleep(wait_time)
  else:
    raise RuntimeError()


def lambda_handler(event, context):
  LOGGER.debug('receive SNS message')

  s3_client = boto3.client('s3', region_name=AWS_REGION)
  ses_client = boto3.client('ses', region_name=AWS_REGION)

  for record in event['Records']:
    msg = json.loads(record['Sns']['Message'])
    LOGGER.debug('message: %s' % json.dumps(msg))

    doc_id = msg['id']
    url = msg['link']
    article = Article(url)
    article.download()
    article.parse()
    meta_data = article.meta_data

    section = meta_data['article']['section']
    tag = meta_data['article']['tag']
    published_time = meta_data['article']['published_time']

    title, body_text = article.title, article.text

    #XX: https://py-googletrans.readthedocs.io/en/latest/
    assert len(body_text) < MAX_SINGLE_TEXT_SIZE

    translator = mk_translator(dest=TRANS_DEST_LANG)
    title_translated = translator.translate(title, dest=TRANS_DEST_LANG)
    trans_title = title_translated.text

    sentences = [e for e in body_text.split('\n') if e]
    trans_sentences = translator.translate(sentences, dest=TRANS_DEST_LANG)
    trans_body_texts = [e.text for e in trans_sentences]

    doc = {
      'doc_id': doc_id,
      'link': url,
      'lang': TRANS_DEST_LANG,
      'pub_date': published_time,
      'section': section, 
      'title': title,
      'title_trans': trans_title,
      'body_trans': trans_body_texts,
      'tags': tag
    }
    html = gen_html(doc)

    subject = '''[translated] {title}'''.format(title=doc['title'])
    send_email(ses_client, EMAIL_FROM_ADDRESS, EMAIL_TO_ADDRESSES, subject, html)

    s3_obj_key = '{}/{}-{}.html'.format(S3_OBJ_KEY_PREFIX,
      arrow.get(published_time).format('YYYYMMDD'), doc['doc_id'])
    fwrite_s3(s3_client, html, S3_BUCKET_NAME, s3_obj_key) 
  LOGGER.debug('done')


if __name__ == '__main__':
  test_sns_event = {
    "Records": [
      {
        "EventSource": "aws:sns",
        "EventVersion": "1.0",
        "EventSubscriptionArn": "arn:aws:sns:us-east-1:{{{accountId}}}:ExampleTopic",
        "Sns": {
          "Type": "Notification",
          "MessageId": "95df01b4-ee98-5cb9-9903-4c221d41eb5e",
          "TopicArn": "arn:aws:sns:us-east-1:123456789012:ExampleTopic",
          "Subject": "example subject",
          "Message": "example message",
          "Timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
          "SignatureVersion": "1",
          "Signature": "EXAMPLE",
          "SigningCertUrl": "EXAMPLE",
          "UnsubscribeUrl": "EXAMPLE",
          "MessageAttributes": {
            "Test": {
              "Type": "String",
              "Value": "TestString"
            },
            "TestBinary": {
              "Type": "Binary",
              "Value": "TestBinary"
            }
          }
        }
      }
    ]
  }

  msg_body = {
    "id": "6da2a3be3378d3f1",
    "link": "https://aws.amazon.com/blogs/aws/new-redis-6-compatibility-for-amazon-elasticache/",
    "pub_date": "2020-10-07T14:50:59-07:00"
  }
  message = json.dumps(msg_body, ensure_ascii=False)

  test_sns_event['Records'][0]['Sns']['Subject'] = 'blog posts from {topic}'.format(topic='AWS')
  test_sns_event['Records'][0]['Sns']['Message'] = message
  LOGGER.debug(json.dumps(test_sns_event))

  start_t = time.time()
  lambda_handler(test_sns_event, {})
  end_t = time.time()
  LOGGER.info('run_time: {:.2f}'.format(end_t - start_t))

