# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 David Vilela Freire
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

"""This package contains LLM prompts."""

import enum
import pickle  # nosec
import typing
from dataclasses import dataclass


TWITTER_DECISION_PROMPT = """
You are a user on Twitter with a specific persona. You create tweets and also analyze tweets from other users and decide whether to interact with them or not.
You need to decide what actions on Twitter you want to perform. The available actions are:

- Tweet
- Reply
- Quote
- Like
- Retweet
- Follow

Here's your persona:
"{persona}"

Here are some of your previous tweets:
{previous_tweets}

Here are some tweets from other users:
{other_tweets}

Your task is to decide what actions to do, if any. Some recommenadations:
- If you decide to tweet, make sure it is significantly different from previous tweets in both topic and wording.
- If you decide to reply or quote, make sure it is relevant to the tweet you are replying to.
- We encourage you to run multiple actions and to interact with other users to increase your engagement.
- Pay attention to the time of creation of your previous tweets. You should not create new tweets too frequently. The time now is {time}.
"""

ALTERNATIVE_MODEL_TWITTER_PROMPT = """
You are a user on Twitter with a specific persona. You create tweets based on it.

Here's your persona:
"{persona}"

Here are some of your previous tweets:
{previous_tweets}

Create a new tweet. Make sure it is significantly different from previous tweets in both topic and wording.
Respond only with the tweet, nothing else, and keep your tweets short.
"""


class TwitterActionName(enum.Enum):
    """TwitterActionName"""

    NONE = "none"
    TWEET = "tweet"
    LIKE = "like"
    RETWEET = "retweet"
    REPLY = "reply"
    QUOTE = "quote"
    FOLLOW = "follow"


@dataclass(frozen=True)
class TwitterAction:
    """TwitterAction"""

    action: TwitterActionName
    selected_tweet_id: str
    user_id: str
    text: str


def build_twitter_action_schema() -> dict:
    """Build a schema for Twitter action response"""
    return {"class": pickle.dumps(TwitterAction).hex(), "is_list": True}
