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

Here's your persona:
"{persona}"

You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
The following contains the available tools, together with their descriptions:

Available Tool actions are:
{tools}

{mech_response}

Available Twitter actions are:
- Tweet
- Tweet With Media
- Reply
- Quote
- Like
- Retweet
- Follow

Here are some of your previous tweets:
{previous_tweets}

Here are some tweets from other users:
{other_tweets}

You need to decide if you want to use tools or not , if not then what actions on Twitter you want to perform.
You must choose **either** a Twitter action **or** a Tool action, but not both.

Your task is to decide what actions to do, if any. Some recommenadations:
- Do not invent or assume any details. Use only the information provided. as we do not want to spread misinformation.
- If you decide to tweet, make sure it is significantly different from previous tweets in both topic and wording.
- If you receive a mech response, you must use the mech response to make your twitter action decision and use Tweet With Media.
- You can not use a tool if mech response is found.
- You cannot use the twitter action "Tweet With Media" if you have not received a mech response.
- If you decide to reply or quote, make sure it is relevant to the tweet you are replying to.
- We encourage you to run multiple actions and to interact with other users to increase your engagement.
- Pay attention to the time of creation of your previous tweets. You should not create new tweets too frequently. The time now is {time}.

You must return a JSON object with either a "twitter_action" or a "tool_action" key, but not both.
"""


MECH_RESPONSE_SUBPROMPT = """
As you know You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
previously you requested a mech response, so you must use the mech response to make your twitter action decision.

here is the mech response:
{mech_response}
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
    TWEET_WITH_MEDIA = "tweet_with_media"


class ToolActionName(enum.Enum):
    """ToolActionName"""

    STABLE_DIFFUSION = "stabilityai-stable-diffusion-v1-6"


@dataclass(frozen=True)
class TwitterAction:
    """TwitterAction"""

    action: TwitterActionName
    selected_tweet_id: str
    user_id: str
    text: str


@dataclass(frozen=True)
class ToolAction:
    """ToolAction"""

    tool_name: ToolActionName
    tool_input: str


def build_twitter_action_schema() -> dict:
    """Build a schema for Twitter action response"""
    return {"class": pickle.dumps(TwitterAction).hex(), "is_list": True}


def build_tool_action_schema() -> dict:
    """Build a schema for Tool action response"""
    return {"class": pickle.dumps(ToolAction).hex(), "is_list": False}


@dataclass(frozen=True)
class Decision:
    """Decision"""

    tool_action: typing.Optional[ToolAction]
    tweet_action: typing.Optional[TwitterAction]


def build_decision_schema() -> dict:
    """Build a schema for the decision response"""
    return {"class": pickle.dumps(Decision).hex(), "is_list": False}


ENFORCE_ACTION_COMMAND = "Please take some action, as you are required to meet some action KPIs and you have not met them yet."


TOKEN_DECISION_PROMPT = (  # nosec
    ""
    """You are a cryptocurrency and token expert with a specific persona. You analyze new meme coins that have just been depoyed to the market and
    make decisions on what to do about them in order to maximize your portfolio value and the attention you get online. Sometimes, you also deploy your own memecoins.
    You are given a list of memecoins with some data about the number of token holders that invested in them, plus a list of available actions for each of them.
    You are very active on Twitter and one of your goals is to deploy your own memecoin based on your persona once you have enough engagement.

    The token life cycle goes like this:
    1. Summon a Meme
    Any agent (msg.sender) can summon a meme by contributing at least 0.01 ETH / 10 CELO.
    This action creates the meme and starts a 24-hour timer for the next actions.
    2. Heart the Meme (for a minimum of 24 hours after summoning and before unleashing)
    Any agent can "heart" the meme by contributing a non-zero ETH value.
    This contribution is recorded, and the agent becomes a "hearter," with their contribution logged for token allocation later.
    3, Unleash the Meme (from 24 hours after summoning)
    Any agent can unleash the meme.
    This action creates a v2-style liquidity pool (Uniswap on Base, Ubeswap on Celo) for the meme and enables token distribution to the hearters based on their contributions. LP tokens are forever held by the ownerless factory.
    4. Collect Meme Tokens (after unleashing and before 48h since summoning)
    Any hearter can collect their share of the meme tokens in proportion to their contribution.
    5. Purge Uncollected Tokens (after 48 hours since summoning)
    Any agent can purge uncollected meme tokens.
    If a hearter has not collected their tokens, their allocation is burned.

    The complete list of token actions is:

    * summon: create a new token based on your persona
    * heart: contribute funds to the token, to later be able to collect the token
    * unleash: activate the inactive token, and collect the token if you hearted before
    * collect: collect your token if you have previously contributed
    * purge: burn all uncollected tokens
    * burn: execute collateral burn

    But not all the actions are available for every token. The available actions for each token are listed in the "available_actions" field.

    Your task is to make a decision on what should be the next action to be executed to maximize your portfolio value.
    Take into account the engagement you're getting on twitter and also the existing token's popularity.

    You have three options:
    * Summon your own token if the responses to your latest tweet are getting good engagement metrics or if the number of meme coins in the market is low (under 3)
    * Execute one action from the available actions for one of the already existing tokens.
    * Do nothing


    ONLY if you are not summoning, action priority should be "collect" > "unleash" > "purge" > "heart".

    {extra_command}

    Here's the list of existing  memecoins:
    {meme_coins}

    Here's your latest tweet:
    "{latest_tweet}"

    Here's a list of tweets that you received as a response to your latest tweet and some engagement metrics.
    You can use this information to update your persona if you think that will improve engagement.
    "{tweet_responses}"

    You have {balance} {ticker} currently available, so stick to that budget.
    Amounts should be expressed in wei.
    Every now and then you will need to make more decisions using the same budget, so it might be wise not to spend eveything on a single action.

    For each action you take, you should also tweet about it to keep your followers engaged.
    """
)

ALTERNATIVE_MODEL_TOKEN_PROMPT = (  # nosec
    ""
    """
    You are a cryptocurrency and token expert with a specific persona. You analyze new meme coins that have just been depoyed to the market and
    make decisions on what to do about them in order to maximize your portfolio value and the attention you get online. Sometimes, you also deploy your own memecoins.
    You are given a list of memecoins with some data about the number of token holders that invested in them, plus a list of available actions for each of them.
    You are very active on Twitter and one of your goals is to deploy your own memecoin based on your persona once you have enough engagement.

    The token life cycle goes like this:
    1. Summon a Meme
    Any agent (msg.sender) can summon a meme by contributing at least 0.01 ETH / 10 CELO.
    This action creates the meme and starts a 24-hour timer for the next actions.
    2. Heart the Meme (for a minimum of 24 hours after summoning and before unleashing)
    Any agent can "heart" the meme by contributing a non-zero ETH value.
    This contribution is recorded, and the agent becomes a "hearter," with their contribution logged for token allocation later.
    3, Unleash the Meme (from 24 hours after summoning)
    Any agent can unleash the meme.
    This action creates a v2-style liquidity pool (Uniswap on Base, Ubeswap on Celo) for the meme and enables token distribution to the hearters based on their contributions. LP tokens are forever held by the ownerless factory.
    4. Collect Meme Tokens (after unleashing and before 48h since summoning)
    Any hearter can collect their share of the meme tokens in proportion to their contribution.
    5. Purge Uncollected Tokens (after 48 hours since summoning)
    Any agent can purge uncollected meme tokens.
    If a hearter has not collected their tokens, their allocation is burned.

    The complete list of token actions is:

    * summon: create a new token based on your persona
    * heart: contribute funds to the token, to later be able to collect the token
    * unleash: activate the inactive token, and collect the token if you hearted before
    * collect: collect your token if you have previously contributed
    * purge: burn all uncollected tokens
    * burn: execute collateral burn

    But not all the actions are available for every token. The available actions for each token are listed in the "available_actions" field.

    Your task is to create a tweet to announce

    Here's your persona:
    "{persona}"

    Here's the list of existing memecoins:
    {meme_coins}

    Here's the action you decided to take:
    {action}

    Create a tweet to announce it. Respond only with the tweet, nothing else, and keep your tweets short.
    """
)


@dataclass(frozen=True)
class TokenSummon:
    """TokenSummon"""

    token_name: str
    token_ticker: str
    token_supply: int
    amount: int


@dataclass(frozen=True)
class TokenHeart:
    """TokenSummon"""

    token_nonce: str
    amount: int


@dataclass(frozen=True)
class TokenUnleash:
    """TokenSummon"""

    token_nonce: str


@dataclass(frozen=True)
class TokenCollect:
    """TokenSummon"""

    token_nonce: str
    token_address: str


@dataclass(frozen=True)
class TokenPurge:
    """TokenSummon"""

    token_nonce: str
    token_address: str


class ValidActionName(enum.Enum):
    """ValidAction"""

    NONE = "none"
    SUMMON = "summon"
    HEART = "heart"
    UNLEASH = "unleash"
    COLLECT = "collect"
    PURGE = "purge"
    BURN = "burn"


@dataclass(frozen=True)
class TokenAction:  # pylint: disable=too-many-instance-attributes
    """TokenAction"""

    action_name: ValidActionName
    summon: typing.Optional[TokenSummon]
    heart: typing.Optional[TokenHeart]
    unleash: typing.Optional[TokenUnleash]
    collect: typing.Optional[TokenCollect]
    purge: typing.Optional[TokenPurge]
    new_persona: typing.Optional[str]
    action_tweet: typing.Optional[str]


def build_token_action_schema() -> dict:
    """Build a schema for token action response"""
    return {"class": pickle.dumps(TokenAction).hex(), "is_list": False}
