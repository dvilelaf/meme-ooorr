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

"""Test prompts"""

import json
import os
import pickle  # nosec
import random

import dotenv
import google.generativeai as genai  # type: ignore

from packages.dvilela.skills.memeooorr_abci.prompts import (
    TOKEN_DECISION_PROMPT,
    build_token_action_schema,
)


dotenv.load_dotenv(override=True)

PERSONA = """
A crazy software engineer trying to fix issues on a AI agent project that creates memecoins
"""

PREVIOUS_TWEETS = """
tweet_id: 1
text: Spent the day battling a rogue semicolon in my AI's code. The memecoin generation is still unstable. Help me. Please send pizza.
timestamp: 2025-01-17 15:29:00
"""

OTHER_TWEETS = [
    {
        "tweet_id": 2,
        "user_id": 20,
        "tweet_text": "Hahahaha!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 3,
        "user_id": 30,
        "tweet_text": "Pizza is the best food ever!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 4,
        "user_id": 40,
        "tweet_text": "Stop coding! AI is the future :)",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 5,
        "user_id": 50,
        "tweet_text": "memecoins! memecoins everywhere!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
]

tweet_responses_str = "\n\n".join(
    [
        f"tweet_id: {t['tweet_id']}\ntweet_text: {t['tweet_text']}\nuser_id: {t['user_id']}\nviews: {t['view_count']}\nquotes: {t['quote_count']}\nretweets: {t['retweet_count']}"
        for t in OTHER_TWEETS
    ]
)

TIME = """
2025-01-17 16:29:00
"""

AVAILABLE_ACTIONS = ["heart", "unleash", "collect", "purge"]

TOKENS = [
    {
        "token_name": "Wave",
        "token_ticker": "WAVE",
        "token_address": "",
        "heart_count": 4,
        "is_unleashed": False,
        "meme_nonce": 4,
        "token_nonce": 4,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
    {
        "token_name": "Meme",
        "token_ticker": "MEME",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680e",
        "heart_count": 5,
        "is_unleashed": True,
        "meme_nonce": 5,
        "token_nonce": 5,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
    {
        "token_name": "Flow",
        "token_ticker": "FLOW",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680a",
        "heart_count": 6,
        "is_unleashed": True,
        "meme_nonce": 6,
        "token_nonce": 6,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
]
random.shuffle(TOKENS)

genai.configure(api_key=os.getenv("GENAI_API_KEY"))

model = genai.GenerativeModel("gemini-2.0-flash")

# fmt: off
TOKEN_SUMMARY = (  # nosec
    """
    token nonce: {token_nonce}
    token address: {token_address}
    token name: {token_name}
    token symbol: {token_ticker}
    heart count: {heart_count}
    available actions: {available_actions}
    """
)
# fmt: on

meme_coins = "\n".join(
    TOKEN_SUMMARY.format(**meme_coin)
    for meme_coin in TOKENS
    if meme_coin["available_actions"]  # Filter out tokens with no available actions
)

schema = build_token_action_schema()
schema_class = pickle.loads(bytes.fromhex(schema["class"]))  # nosec

prompt = TOKEN_DECISION_PROMPT.format(
    meme_coins=meme_coins,
    latest_tweet=PREVIOUS_TWEETS,
    tweet_responses=tweet_responses_str,
    balance=0.1,
    extra_command="",
    ticker="ETH",
)

response = model.generate_content(
    prompt,
    generation_config=genai.types.GenerationConfig(
        temperature=2.0,
        response_mime_type="application/json",
        response_schema=schema_class,
    ),
)


print(json.loads(response.text))
