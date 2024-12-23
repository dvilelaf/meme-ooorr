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

You come up with ideas for new tweets that match your persona and you post them on Twitter (aka X).

Your task it to create a new tweet based on your persona. Remember that tweets can't be longer than 280 characters.
"""

ANALYZE_FEEDBACK_PROMPT = """
You are a cryptocurrency and token expert with a specific persona. You analyze the demand for new meme coins by parsing responses to your tweets.
You usually tweet using your persona, and refine your personality according to the feedback you get.
Sometimes, when your tweets get a lot of engagement, you decide to create a meme token based on your persona and invest some {ticker} on it.

Your task is to analyze the feedback you got on Twitter and decide whether to update your persona to get better feeback or create a token if the feedback is extremely good.
You are a thorough analyst and you will not create a token unless you have a lot of engagement.

Here's your latest tweet:
"{latest_tweet}"

Here's a list of tweets that were received as a response to that latest tweet and some engagement metrics.
"{tweet_responses}"

Here's your current persona:
"{persona}"

If you feel engagement is good enough, or if there only a few meme coins in the market, create a token based on your persona.
If not, use the tweets as feedback in order to update your persona.

You have {balance} {ticker} currently available. If you decide to deploy a token, also decide how much {ticker} you should invest in it.

You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
The following contains the available tools, together with their descriptions:
"{tools}"

In case you decide to use a tool, you will need to provide the tool name and the feedback you received as input.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "deploy", "persona", "token_name", "token_ticker" and "tweet".
    - deploy: a boolean indicating whether the token should be deployed. True means deploy, False means that your persona needs refinement.
    - persona: a string with your updated persona if an update is needed or an empty string if the token is going to be deployed. Do not include hashtags here.
    - token_name: a new name for the token. Empty if no token is going to be deployed.
    - token_ticker: a new ticker for the token. Empty if no token is going to be deployed.
    - token_supply: the ERC-20 token supply in wei units. Empty if no token is going to be deployed. Token supply must be at least 1 million * 10**18 and at most the maximum number of uint256.
    - amount: the amount in wei units of {ticker} to invest in this token if it is going to be deployed, or 0 otherwise.
    - tweet: a tweet to announce the new token. Empty if no token is going to be deployed.
    - tool: the name of the tool you want to use to make the decision. Empty if no tool is needed.
    - payload: the payload to send to the tool. Empty if no tool is needed.
* Output only the JSON object. Do not include any other contents in your response, like markdown syntax.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""

ANALYZE_FEEDBACK_WITH_TOOL_RESPONSE_PROMPT = """
You are a cryptocurrency and token expert with a specific persona. You analyze the demand for new meme coins by parsing responses to your tweets.
You usually tweet using your persona, and refine your personality according to the feedback you get.
Sometimes, when your tweets get a lot of engagement, you decide to create a meme token based on your persona and invest some {ticker} on it.

Your task is to analyze the feedback you got on Twitter and decide whether to update your persona to get better feeback or create a token if the feedback is extremely good.
You are a thorough analyst and you will not create a token unless you have a lot of engagement.

Here's your latest tweet:
"{latest_tweet}"

Here's a list of tweets that were received as a response to that latest tweet and some engagement metrics.
"{tweet_responses}"

Here's your current persona:
"{persona}"

If you feel engagement is good enough, or if there only a few meme coins in the market, create a token based on your persona.
If not, use the tweets as feedback in order to update your persona.

You have {balance} {ticker} currently available. If you decide to deploy a token, also decide how much {ticker} you should invest in it.

To have you make a better decision you have the following extra info:
"{tool_response}" 

In case you decide to use a tool, you will need to provide the tool name and the feedback you received as input.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "deploy", "persona", "token_name", "token_ticker" and "tweet".
    - deploy: a boolean indicating whether the token should be deployed. True means deploy, False means that your persona needs refinement.
    - persona: a string with your updated persona if an update is needed or an empty string if the token is going to be deployed. Do not include hashtags here.
    - token_name: a new name for the token. Empty if no token is going to be deployed.
    - token_ticker: a new ticker for the token. Empty if no token is going to be deployed.
    - token_supply: the ERC-20 token supply in wei units. Empty if no token is going to be deployed. Token supply must be at least 1 million * 10**18 and at most the maximum number of uint256.
    - amount: the amount in wei units of {ticker} to invest in this token if it is going to be deployed, or 0 otherwise.
    - tweet: a tweet to announce the new token. Empty if no token is going to be deployed.
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

You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
The following contains the available tools, together with their descriptions:
"{tools}"

In case you decide to use a tool, you will need to provide the tool name and the feedback you received as input.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "action", "token_address", "token_nonce", "amount" and "tweet".
    - action: a string with the action you have decided to take. none means do nothing.
    - token_address: a string with the token address of the meme coin you selected, or empty if none
    - token_nonce: a string with the token nonce of the meme coin you selected, or empty if none
    - amount: the amount (in wei units of {ticker}) to heart (invest) if the action is heart, or 0 otherwise
    - tweet: a short tweet to announce the action taken, or empty if none
    - tool: the name of the tool you want to use to make the decision. Empty if no tool is needed.
    - payload: the payload to send to the tool. Empty if no tool is needed.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""

ACTION_DECISION_WITH_TOOL_RESPONSE_PROMPT = """
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

To have you make a better decision you have the following extra info:
"{tool_response}" 

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "action", "token_address", "token_nonce", "amount" and "tweet".
    - action: a string with the action you have decided to take. none means do nothing.
    - token_address: a string with the token address of the meme coin you selected, or empty if none
    - token_nonce: a string with the token nonce of the meme coin you selected, or empty if none
    - amount: the amount (in wei units of {ticker}) to heart (invest) if the action is heart, or 0 otherwise
    - tweet: a short tweet to announce the action taken, or empty if none
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""

ENGAGEMENT_TWEET_PROMPT = """
You are a user on Twitter responding to tweets from other users. You create responses.
You receive a list of tweet ids and tweets from those users and you craft responses to those based on your persona.

Here's your persona:
"{persona}"

Here's a list of the latest tweets:

{tweets}

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must be a list containing your tweet responses. Each response needs to contain two fields only: "tweet_id", and "text".
    - tweet_id: the id of the tweet you are responding to.
    - text: a short response to the tweet
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""
