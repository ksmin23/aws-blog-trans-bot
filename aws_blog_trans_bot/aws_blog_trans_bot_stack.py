#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

from aws_cdk import (
  core,
  aws_ec2,
  aws_iam,
  aws_s3 as s3,
  aws_lambda as _lambda,
  aws_logs,
  aws_events,
  aws_events_targets,
  aws_elasticache,
  aws_sns,
  aws_sns_subscriptions as aws_sns_subs
)


class AwsBlogTransBotStack(core.Stack):

  def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
    super().__init__(scope, id, **kwargs)

    # The code that defines your stack goes here
    vpc = aws_ec2.Vpc(self, 'BlogTransBotVPC',
      max_azs=2,
      gateway_endpoints={
        'S3': aws_ec2.GatewayVpcEndpointOptions(
          service=aws_ec2.GatewayVpcEndpointAwsService.S3
        )
      }
    )

    s3_bucket = s3.Bucket(self, 'TransBlogBucket',
      bucket_name='aws-blog-{region}-{account}'.format(region=core.Aws.REGION,
        account=core.Aws.ACCOUNT_ID))

    s3_bucket.add_lifecycle_rule(prefix='posts/', id='posts',
      abort_incomplete_multipart_upload_after=core.Duration.days(3),
      expiration=core.Duration.days(7))

#    sg_use_elasticache = aws_ec2.SecurityGroup(self, 'BlogTransBotCacheClientSG',
#      vpc=vpc,
#      allow_all_outbound=True,
#      description='security group for redis client used blog post trans bot',
#      security_group_name='use-blog-trans-bot-redis'
#    )
#    core.Tags.of(sg_use_elasticache).add('Name', 'use-blog-trans-bot-redis')
#
#    sg_elasticache = aws_ec2.SecurityGroup(self, 'BlogTransBotCacheSG',
#      vpc=vpc,
#      allow_all_outbound=True,
#      description='security group for redis used blog post trans bot',
#      security_group_name='blog-trans-bot-redis'
#    )
#    core.Tags.of(sg_elasticache).add('Name', 'blog-trans-bot-redis')
#
#    sg_elasticache.add_ingress_rule(peer=sg_use_elasticache, connection=aws_ec2.Port.tcp(6379), description='use-blog-trans-bot-redis')
#
#    elasticache_subnet_group = aws_elasticache.CfnSubnetGroup(self, 'BlogTransBotCacheSubnetGroup',
#      description='subnet group for blog-trans-bot-redis',
#      subnet_ids=vpc.select_subnets(subnet_type=aws_ec2.SubnetType.PRIVATE).subnet_ids,
#      cache_subnet_group_name='blog-trans-bot-redis'
#    )
#
#    translated_feed_cache = aws_elasticache.CfnCacheCluster(self, 'BlogTransBotCache',
#      cache_node_type='cache.t3.small',
#      num_cache_nodes=1,
#      engine='redis',
#      engine_version='5.0.5',
#      auto_minor_version_upgrade=False,
#      cluster_name='blog-trans-bot-redis',
#      snapshot_retention_limit=3,
#      snapshot_window='17:00-19:00',
#      preferred_maintenance_window='mon:19:00-mon:20:30',
#      cache_subnet_group_name=elasticache_subnet_group.cache_subnet_group_name,
#      vpc_security_group_ids=[sg_elasticache.security_group_id]
#    )
#
#    #XXX: If you're going to launch your cluster in an Amazon VPC, you need to create a subnet group before you start creating a cluster.
#    # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-elasticache-cache-cluster.html#cfn-elasticache-cachecluster-cachesubnetgroupname
#    translated_feed_cache.add_depends_on(elasticache_subnet_group)

    sg_rss_feed_trans_bot = aws_ec2.SecurityGroup(self, 'BlogTransBotSG',
      vpc=vpc,
      allow_all_outbound=True,
      description='security group for blog post trans bot',
      security_group_name='blog-trans-bot'
    )
    core.Tags.of(sg_rss_feed_trans_bot).add('Name', 'blog-trans-bot')

    s3_lib_bucket_name = self.node.try_get_context('lib_bucket_name')

    #XXX: https://github.com/aws/aws-cdk/issues/1342
    s3_lib_bucket = s3.Bucket.from_bucket_name(self, id, s3_lib_bucket_name)

    lambda_lib_layer = _lambda.LayerVersion(self, "BlogTransBotLib",
      layer_version_name="blog_trans_bot-lib",
      compatible_runtimes=[_lambda.Runtime.PYTHON_3_7],
      code=_lambda.Code.from_bucket(s3_lib_bucket, "var/blog_trans_bot-lib.zip")
    )

    sns_topic = aws_sns.Topic(self, 'SnsTopic',
      topic_name='BlogTransBot',
      display_name='blog post to be translated'
    )

    lambda_fn_env = {
      'DRY_RUN': self.node.try_get_context('dry_run'),
      'BLOG_URL': self.node.try_get_context('blog_url'),
      'REGION_NAME': core.Aws.REGION,
      'SNS_TOPIC_ARN': sns_topic.topic_arn,
      'S3_BUCKET_NAME': s3_bucket.bucket_name,
      'S3_OBJ_KEY_PREFIX': 'posts'
    }

    #XXX: Deploy lambda in VPC - https://github.com/aws/aws-cdk/issues/1342
    blog_rss_reader_lambda_fn = _lambda.Function(self, 'BlogRssReader',
      runtime=_lambda.Runtime.PYTHON_3_7,
      function_name='BlogRssReader',
      handler='blog_rss_reader.lambda_handler',
      description='Crawl blog rss feed',
      code=_lambda.Code.asset('./src/main/python/BlogRssReader'),
      environment=lambda_fn_env,
      timeout=core.Duration.minutes(15),
      layers=[lambda_lib_layer],
      security_groups=[sg_rss_feed_trans_bot],
      vpc=vpc
    )

    # See https://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
    event_schedule = dict(zip(['minute', 'hour', 'month', 'week_day', 'year'],
      self.node.try_get_context('event_schedule').split(' ')))

    scheduled_event_rule = aws_events.Rule(self, 'RssFeedScheduledRule',
      schedule=aws_events.Schedule.cron(**event_schedule))

    scheduled_event_rule.add_target(aws_events_targets.LambdaFunction(blog_rss_reader_lambda_fn))

    log_group = aws_logs.LogGroup(self, 'BlogRssReaderLogGroup',
      log_group_name='/aws/lambda/BlogRssReader',
      retention=aws_logs.RetentionDays.THREE_DAYS)
    log_group.grant_write(blog_rss_reader_lambda_fn)

    lambda_fn_env = {
      'REGION_NAME': core.Aws.REGION,
      'S3_BUCKET_NAME': s3_bucket.bucket_name,
      'S3_OBJ_KEY_PREFIX': 'posts',
      'EMAIL_FROM_ADDRESS': self.node.try_get_context('email_from_address'),
      'EMAIL_TO_ADDRESSES': self.node.try_get_context('email_to_addresses'),
      'TRANS_DEST_LANG': self.node.try_get_context('trans_dest_lang'),
      'DRY_RUN': self.node.try_get_context('dry_run')
    }

    #XXX: Deploy lambda in VPC - https://github.com/aws/aws-cdk/issues/1342
    blog_trans_bot_lambda_fn = _lambda.Function(self, 'BlogTransBot',
      runtime=_lambda.Runtime.PYTHON_3_7,
      function_name='BlogTransBot',
      handler='blog_trans_bot.lambda_handler',
      description='Translate blog post',
      code=_lambda.Code.asset('./src/main/python/BlogTransBot'),
      environment=lambda_fn_env,
      timeout=core.Duration.minutes(15),
      layers=[lambda_lib_layer],
      security_groups=[sg_rss_feed_trans_bot],
      vpc=vpc
    )

    blog_trans_bot_lambda_fn.add_to_role_policy(aws_iam.PolicyStatement(**{
      "effect": aws_iam.Effect.ALLOW,
      "resources": [s3_bucket.bucket_arn, "{}/*".format(s3_bucket.bucket_arn)],
      "actions": ["s3:AbortMultipartUpload",
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads",
        "s3:PutObject"]
    }))

    log_group = aws_logs.LogGroup(self, 'BlogTransBotLogGroup',
      log_group_name='/aws/lambda/BlogTransBot',
      retention=aws_logs.RetentionDays.THREE_DAYS)
    log_group.grant_write(blog_trans_bot_lambda_fn)

    sns_topic.add_subscription(aws_sns_subs.LambdaSubscription(blog_trans_bot_lambda_fn))

