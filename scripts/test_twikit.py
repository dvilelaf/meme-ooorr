#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2024 Valory AG
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

"""Test twikit"""


import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import dotenv
import twikit


dotenv.load_dotenv(override=True)


def tweet_to_json(tweet: Any) -> Dict:
    """Tweet to json"""
    return {
        "id": tweet.id,
        "user_name": tweet.user.name,
        "text": tweet.text,
        "created_at": tweet.created_at,
        "view_count": tweet.view_count,
        "retweet_count": tweet.retweet_count,
        "quote_count": tweet.quote_count,
        "view_count_state": tweet.view_count_state,
    }


async def password_login():
    """Login via password"""
    client = twikit.Client(language="en-US")
    await client.login(
        auth_info_1=os.getenv("TWIKIT_USERNAME"),
        auth_info_2=os.getenv("TWIKIT_EMAIL"),
        password=os.getenv("TWIKIT_PASSWORD"),
    )
    return client


async def cookie_login():
    """Login via password"""
    with open(
        Path(os.getenv("TWIKIT_COOKIES_PATH")), "r", encoding="utf-8"
    ) as cookie_file:
        cookies = json.load(cookie_file)
        client = twikit.Client(language="en-US")
        client.set_cookies(cookies)
        return client


async def get_tweets() -> None:
    """Get tweets"""

    client = await cookie_login()
    client.save_cookies(os.getenv("TWIKIT_COOKIES_PATH"))

    user = await client.get_user_by_screen_name(screen_name="percebot")

    latest_tweets = await client.get_user_tweets(
        user_id=user.id, tweet_type="Tweets", count=1
    )

    return [tweet_to_json(t) for t in latest_tweets]


tweets = asyncio.run(get_tweets())
date = datetime.strptime(tweets[0]["created_at"], "%a %b %d %H:%M:%S %z %Y")
print(date)