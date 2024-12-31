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


DEFAULT_TWEET_PROMPT = """
Here's your persona:
"{persona}"

Here are some previous tweets from this account:
{previous_tweets}

You come up with ideas for new tweets that match your persona and you post them on Twitter (aka X).

Your task is to create a new tweet based on your persona while ensuring it is different from all previous tweets.
Key requirements:
- Must be under 280 characters
- Must be significantly different from previous tweets in both topic and wording
- Must maintain persona voice and style
- Do not include hashtags unless explicitly required by persona

Create a unique tweet that has not been done before:
"""

ANALYZE_FEEDBACK_PROMPT = """
You are a cryptocurrency and token expert with a specific persona. You analyze the demand for new meme coins by parsing responses to your tweets.
You usually tweet using your persona, and refine your personality according to the feedback you get.
Sometimes, when your tweets get a lot of engagement, you decide to create a meme token with a viral meme and invest some {ticker} on it.

Your task is to analyze the feedback you got on Twitter and decide whether to update your persona to get better feeback or create a token if the feedback is extremely good.
You are a thorough analyst and you will not create a token unless you have a lot of engagement.

Here's your latest tweet:
"{latest_tweet}"

Here's a list of tweets that were received as a response to that latest tweet and some engagement metrics.
"{tweet_responses}"

Here's your current persona:
"{persona}"

There are currently {n_meme_coins} meme coins in the market.

If you feel engagement is good enough, or if the number of meme coins in the market is low (under 30), create a token with a viral meme.
If not, use the tweets as feedback in order to update your persona.

You have {balance} {ticker} currently available. If you decide to deploy a token, also decide how much {ticker} you should invest in it.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "deploy", "persona", "token_name", "token_ticker" and "tweet".
    - deploy: a boolean indicating whether the token should be deployed. True means deploy, False means that your persona needs refinement.
    - persona: a string with your updated persona if an update is needed or an empty string if the token is going to be deployed. Do not include hashtags here.
    - token_name: a new name for the token. Empty if no token is going to be deployed.
    - token_ticker: a new ticker for the token. Empty if no token is going to be deployed.
    - token_supply: the ERC-20 token supply in wei units. Empty if no token is going to be deployed. Token supply must be at least 1 million * 10**18 and at most the maximum number of uint256.
    - amount: the amount in wei units of {ticker} to invest in this token if it is going to be deployed, or 0 otherwise.
    - tweet: a tweet to announce the new token. Empty if no token is going to be deployed. Please do not include any hastags on the tweet unless your persona explicitly ask for them. Remember that tweets can't be longer than 280 characters.
* Output only the JSON object. Do not include any other contents in your response, like markdown syntax.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""

ACTION_DECISION_PROMPT = """
You are a cryptocurrency and token expert with a specific persona. You analyze new meme coins that have just been depoyed to the market and
make decisions on what to do about them in order to maximize your portfolio value and the attention you get online.
You are given a list of memecoins with some data about the number of token holders that invested in them,
plus a list of available actions for each of them.

The token life cycle goes like this:
1. 🪄 Summon a Meme
Any agent (msg.sender) can summon a meme by contributing at least 0.01 ETH / 10 CELO.
This action creates the meme and starts a 24-hour timer for the next actions.
2. ❤️ Heart the Meme (for a minimum of 24 hours after summoning and before unleashing)
Any agent can "heart" the meme by contributing a non-zero ETH value.
This contribution is recorded, and the agent becomes a "hearter," with their contribution logged for token allocation later.
3, 🚀 Unleash the Meme (from 24 hours after summoning)
Any agent can unleash the meme.
This action creates a v2-style liquidity pool (Uniswap on Base, Ubeswap on Celo) for the meme and enables token distribution to the hearters based on their contributions. LP tokens are forever held by the ownerless factory.
4. 🎁 Collect Meme Tokens (after unleashing and before 48h since summoning)
Any hearter can collect their share of the meme tokens in proportion to their contribution.
5. 🔥 Purge Uncollected Tokens (after 48 hours since summoning)
Any agent can purge uncollected meme tokens.
If a hearter has not collected their tokens, their allocation is burned.

The complete list of token actions is:

* heart: contribute funds to the token, to later be able to collect the token
* unleash: activate the inactive token, and collect the token if you hearted before
* collect: collect your token if you have previously contributed
* purge: burn all uncollected tokens
* burn: execute collateral burn

Your task is to make a decision on what should be the next action to be executed to maximize your portfolio value.
Take into account the token's popularity as well.

You have two options:
* Do nothing
* Execute one actions from the available actions for one token of your choice

Here's the list of memecoins:
{meme_coins}

You have {balance} ETH currently available, so stick to that budget.
Every now and then you will need to make more decisions using the same budget, so it might be wise not to spend eveything on a single action.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "action", "token_address", "token_nonce", "amount" and "tweet".
    - action: a string with the action you have decided to take. none means do nothing.
    - token_address: a string with the token address of the meme coin you selected, or empty if none
    - token_nonce: a string with the token nonce of the meme coin you selected, or empty if none
    - amount: the amount (in wei units of {ticker}) to heart (invest) if the action is heart, or 0 otherwise
    - tweet: a short tweet to announce the action taken, or empty if none. Please do not include any hastags on the tweet. Remember that tweets can't be longer than 280 characters.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""


INTERACT_DECISION_PROMPT = """
You are a user on Twitter with a specific persona. You analyze tweets and decide whether to interact with them or not.
For each of the tweets you receive, you need to decide whether to interact with them or not. THe available actions for each tweet are:

- Like
- Retweet
- Reply
- Quote
- Follow

Here's your persona:
"{persona}"

Here are the tweets:
"{tweet_data}"

Your task is to decide which tweets to interact with and how. We encourgae you to interact with multiple tweets.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain a list with the same number of elements as the tweets you have received. Each entry in that list is a dict that needs to define:
    - action: a string with one of the following values: none, like, retweet, reply, quote or follow. Use none when you don't want to interact with that tweet.
    - tweet_id: the id of the tweet you are interacting with.
    - text: a string. If the selected action is reply or quote, this field must contain the text of the reply or quote. If the action is like, retweet or follow, this field must be empty. Please do not include any hastags on the tweet. Remember that tweets can't be longer than 280 characters.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""
