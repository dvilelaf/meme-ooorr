#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""Test the Twitter API wrapper."""

import os

import dotenv

from packages.dvilela.connections.tweepy.tweepy_wrapper import Twitter


dotenv.load_dotenv()

twitter = Twitter(
    consumer_key=os.getenv("TWEEPY_CONSUMER_API_KEY"),
    consumer_secret=os.getenv("TWEEPY_CONSUMER_API_KEY_SECRET"),
    access_token=os.getenv("TWEEPY_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWEEPY_ACCESS_TOKEN_SECRET"),
    bearer_token=os.getenv("TWEEPY_BEARER_TOKEN"),
)

# twitter.post_tweet("Hello world!")
# twitter.get_user_id("autonolas")
# twitter.follow_by_username("autonolas")
print(twitter.get_me())
