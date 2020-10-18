#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

from datetime import datetime
import collections
import time
import logging
import os
import json
import hashlib
import traceback

import boto3
import botocore
from bs4 import BeautifulSoup
import requests
import arrow

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
AWS_SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_OBJ_KEY_PREFIX = os.getenv('S3_OBJ_KEY_PREFIX', 'posts')

BLOG_BASE_URL = os.getenv('BLOG_BASE_URL', 'https://aws.amazon.com/blogs')
BLOG_CATEGORIES = os.getenv('BLOG_CATEGORIES')

def isfile_s3(s3_client, s3_bucket_name, s3_obj_key):
  try:
    res = s3_client.head_object(Bucket=s3_bucket_name, Key=s3_obj_key)
    return True
  except botocore.exceptions.ClientError as ex:
    err_code, err_msg = ex.response['Error']['Code'], ex.response['Error']['Message']
    if (err_code, err_msg) == ('404', 'Not Found'):
      return False
    else:
      raise ex


def send_sns(client, topic, subject, message):
  return client.publish(TopicArn=topic, Subject=subject, Message=message)


def get_meta_data(tag):
  a_tag = tag.find('a', property='url', text='Permalink')
  post_id = hashlib.md5(a_tag['href'].encode('utf-8')).hexdigest()[:16]
  time_tag = tag.find('time', property='datePublished')
  #sections =[e.text for e in tag.find_all('span', property='articleSection')]
  return {'id': post_id, 'link': a_tag['href'], 'pub_date': time_tag['datetime']}


def lambda_handler(event, context):
  LOGGER.info('send new blog post')
  counters = collections.OrderedDict({'total': 0, 'new': 0, 'error': 0})

  LinkData = collections.namedtuple('LinkData', ['category', 'props'])
  BASIC_DATE = arrow.get(event['time']).shift(days=-3).ceil('day')

  cand_post_list = []
  for category in BLOG_CATEGORIES.split(','):
    blog_url = '{base_url}/{path}'.format(base_url=BLOG_BASE_URL, path=category)
    res = requests.get(blog_url)
    html = res.text
    soup = BeautifulSoup(html, 'html.parser')
    footers = soup.find_all('footer', class_='blog-post-meta')

    post_list = [LinkData(category, get_meta_data(elem)) for elem in footers]
    cand_post_list.extend([e for e in post_list if arrow.get(e.props['pub_date']) >= BASIC_DATE])
    counters['total'] += len(post_list)

  s3_client = boto3.client('s3', region_name=AWS_REGION)
  new_post_list = []
  for elem in cand_post_list:
    s3_obj_key = '{}/{}-{}.html'.format(S3_OBJ_KEY_PREFIX,
      arrow.get(elem.props['pub_date']).format('YYYYMMDD'), elem.props['id'])
    if not isfile_s3(s3_client, S3_BUCKET_NAME, s3_obj_key):
      new_post_list.append(elem)

  sns_client = boto3.client('sns', region_name=AWS_REGION)
  for category, elem in new_post_list:
    try:
      if DRY_RUN:
        print(category, json.dumps(elem))
        continue
      send_sns(sns_client, AWS_SNS_TOPIC_ARN, category, json.dumps(elem))
    except Exception as ex:
      traceback.print_exc()
      counters['error'] += 1

  counters['new'] += len(new_post_list)
  LOGGER.info('done: {}'.format(','.join(['{}={}'.format(k, v) for k, v in counters.items()])))


if __name__ == '__main__':
  test_event = {
    "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
    "detail-type": "Scheduled Event",
    "source": "aws.events",
    "account": "",
    "time": "1970-01-01T00:00:00Z",
    "region": "us-east-1",
    "resources": [
      "arn:aws:events:us-east-1:123456789012:rule/ExampleRule"
    ],
    "detail": {}
  }
  test_event['time'] = datetime.utcnow().strftime('%Y-%m-%dT%H:00:00')

  start_t = time.time()
  lambda_handler(test_event, {})
  end_t = time.time()
  LOGGER.info('run_time: {:.2f}'.format(end_t - start_t))

