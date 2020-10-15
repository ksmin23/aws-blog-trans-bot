#!/usr/bin/env python3

from aws_cdk import core

from aws_blog_trans_bot.aws_blog_trans_bot_stack import AwsBlogTransBotStack


app = core.App()
AwsBlogTransBotStack(app, "aws-blog-trans-bot")

app.synth()
