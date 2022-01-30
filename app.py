#!/usr/bin/env python3

import aws_cdk as cdk

from aws_blog_trans_bot.aws_blog_trans_bot_stack import AwsBlogTransBotStack


app = cdk.App()
AwsBlogTransBotStack(app, "AwsBlogTransBot")

app.synth()
