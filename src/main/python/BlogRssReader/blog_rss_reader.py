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

import boto3
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

BLOG_URL = os.getenv('BLOG_URL', 'https://aws.amazon.com/ko/blogs/aws/')
BLOG_CATEGORY = BLOG_URL.rstrip('/').split('/')[-1]


def send_sns(client, topic, subject, message):
  client.publish(TopicArn=topic, Subject=subject, Message=message)


def get_meta_data(tag):
  a_tag = tag.find('a', property='url', text='Permalink')
  post_id = hashlib.md5(a_tag['href'].encode('utf-8')).hexdigest()[:16]
  time_tag = tag.find('time', property='datePublished')
  #sections =[e.text for e in tag.find_all('span', property='articleSection')]
  return {'id': post_id, 'link': a_tag['href'], 'pub_date': time_tag['datetime']}


def lambda_handler(event, context):
  LOGGER.info('send new blog post')
  counters = collections.OrderedDict({'total': 0, 'new': 0, 'error': 0})

  res = requests.get(BLOG_URL)
  html = res.text
  soup = BeautifulSoup(html, 'html.parser')
  footers = soup.find_all('footer', class_='blog-post-meta')

  BASIC_DATE = arrow.get(event['time']).shift(days=-1).ceil('day')

  post_list = [get_meta_data(elem) for elem in footers]
  #print('\n'.join([json.dumps(e) for e in post_list]))
  new_post_list = [e for e in post_list if arrow.get(e['pub_date']) >= BASIC_DATE]

  sns_client = boto3.client('sns', region_name=AWS_REGION)
  for elem in new_post_list:
    try:
      send_sns(sns_client, AWS_SNS_TOPIC, BLOG_CATEGORY, json.dumps(elem))
    except Exception as ex:
      counters['error'] += 1

  counters['total'] += len(post_list)
  counters['new'] += len(new_post_list)

  LOGGER.info('done: {}'.format(','.join(['{}={}'.format(k, v) for k, v in counters.items()])))


if __name__ == '__main__':
  event = {
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
  event['time'] = datetime.utcnow().strftime('%Y-%m-%dT%H:00:00')

  start_t = time.time()
  lambda_handler(event, {})
  end_t = time.time()
  LOGGER.info('run_time: {:.2f}'.format(end_t - start_t))

