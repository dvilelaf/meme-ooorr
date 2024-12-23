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

"""This package contains round behaviours of MemeooorrAbciApp."""

import json
import re
from typing import Dict, Generator, Optional, Tuple, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.twitter import (
    is_tweet_valid,
)
from packages.dvilela.skills.memeooorr_abci.prompts import (
    ACTION_DECISION_PROMPT,
    ANALYZE_FEEDBACK_PROMPT,
    ANALYZE_FEEDBACK_WITH_TOOL_RESPONSE_PROMPT,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    ActionDecisionPayload,
    ActionDecisionRound,
    AnalizeFeedbackPayload,
    AnalizeFeedbackRound,
    Event,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


JSON_RESPONSE_REGEX = r"json({.*})"

# fmt: off
TOKEN_SUMMARY = (  # nosec
    """
    token nonce: {token_nonce}
    token address: {token_address}
    token name: {token_name}
    token symbol: {token_ticker}
    total supply (wei): {token_supply}
    decimals: {decimals}
    heath count: {heart_count}
    available actions: {available_actions}
    """
)
# fmt: on


class AnalizeFeedbackBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """AnalizeFeedbackBehaviour"""

    matching_round: Type[AbstractRound] = AnalizeFeedbackRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            analysis = yield from self.get_analysis()
            self.context.logger.info(f"Analysis: {analysis}")

            payload = AnalizeFeedbackPayload(
                sender=self.context.agent_address,
                analysis=json.dumps(analysis, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_analysis(  # pylint: disable=too-many-locals,too-many-return-statements
        self,
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""

        if self.synchronized_data.feedback is None:
            return None

        tweet_responses = "\n\n".join(
            [
                f"tweet: {t['text']}\nviews: {t['view_count']}\nquotes: {t['quote_count']}\nretweets{t['retweet_count']}"
                for t in self.synchronized_data.feedback
            ]
        )

        native_balance = yield from self.get_native_balance()
        if not native_balance:
            native_balance = 0

        prompt_data = {
            "latest_tweet": self.synchronized_data.latest_tweet["text"],
            "tweet_responses": tweet_responses,
            "persona": self.get_persona(),
            "balance": native_balance,
            "ticker": "ETH" if self.params.home_chain_id == "BASE" else "CELO",
        }

        if len(self.synchronized_data.mech_responses) > 0:
            # we have a previous tool response, we make use of it
            prompt_data = {
                **prompt_data,
                "tool_response": self.synchronized_data.mech_responses[-1].result,
            }
            prompt = ANALYZE_FEEDBACK_WITH_TOOL_RESPONSE_PROMPT.format(**prompt_data)
        else:
            tools_to_description = "\n".join(
                f"{k}: {v}" for k, v in self.params.tools_to_description.items()
            )
            prompt_data = {
                **prompt_data,
                "tools": tools_to_description,
            }
            prompt = ANALYZE_FEEDBACK_PROMPT.format(**prompt_data)

        llm_response = yield from self._call_genai(prompt=prompt)
        self.context.logger.info(f"LLM response: {llm_response}")

        # We didnt get a response
        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return None

        # The response is not a valid json
        try:
            response = json.loads(llm_response)
        except json.JSONDecodeError as e:
            self.context.logger.error(f"Error loading the LLM response: {e}")
            return None

        # check if the llm decided to use a tool
        if "tool" in response and response["tool"] in self.params.tools_to_description and "payload" in response:
            self.context.logger.info(f"LLM decided to use the tool {response['tool']}")
            response["use_mech_tool"] = True
            return response

        # Tweet too long
        if (
            response["deploy"]
            and "tweet" not in response
            and not is_tweet_valid(response["tweet"])
        ):
            self.context.logger.error("Announcement tweet is too long.")
            return None

        # Missing token data
        if (
            response["deploy"]
            and "token_name" not in response
            or "token_ticker" not in response
            or "token_supply" not in response
            or "amount" not in response
        ):
            self.context.logger.error(
                f"Missing some token data from the response: {response}"
            )
            return None

        # Missing persona
        if not response["deploy"] and "persona" not in response:
            self.context.logger.error("Missing the new persona from the response.")
            return None

        # Write new persona to the database
        if not response["deploy"]:
            yield from self._write_kv({"persona": response["persona"]})
            self.context.logger.info("Wrote persona to db")

        return response


class ActionDecisionBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """ActionDecisionBehaviour"""

    matching_round: Type[AbstractRound] = ActionDecisionRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            (
                event,
                token_nonce,
                token_address,
                action,
                amount,
                tweet,
            ) = yield from self.get_event()

            payload = ActionDecisionPayload(
                sender=self.context.agent_address,
                event=event,
                token_nonce=token_nonce,
                token_address=token_address,
                action=action,
                amount=amount,
                tweet=tweet,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(  # pylint: disable=too-many-locals,too-many-return-statements
        self,
    ) -> Generator[
        None,
        None,
        Tuple[
            str,
            Optional[int],
            Optional[str],
            Optional[str],
            Optional[float],
            Optional[str],
        ],
    ]:
        """Get the next event"""

        meme_coins = "\n".join(
            TOKEN_SUMMARY.format(**meme_coin)
            for meme_coin in self.synchronized_data.meme_coins
        )

        self.context.logger.info(f"Action options:\n{meme_coins}")

        valid_nonces = [c["token_nonce"] for c in self.synchronized_data.meme_coins]

        native_balance = yield from self.get_native_balance()
        if not native_balance:
            native_balance = 0

        prompt_data = {
            "meme_coins": meme_coins,
            "balance": native_balance,
            "ticker": "ETH" if self.params.home_chain_id == "BASE" else "CELO",
        }

        llm_response = yield from self._call_genai(
            prompt=ACTION_DECISION_PROMPT.format(**prompt_data)
        )
        self.context.logger.info(f"LLM response: {llm_response}")

        # We didnt get a response
        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return Event.WAIT.value, None, None, None, None, None

        try:
            llm_response = llm_response.replace("\n", "").strip()
            match = re.search(JSON_RESPONSE_REGEX, llm_response)
            if match:
                llm_response = match.groups()[0]
            response = json.loads(llm_response)

            action = response.get("action", "none")
            token_address = response.get("token_address", None)
            token_nonce = (
                int(response["token_nonce"]) if "token_nonce" in response else None
            )
            amount = float(response.get("amount", 0))
            tweet = response.get("tweet", None)

            if action == "none":
                self.context.logger.info("Action is none")
                return Event.WAIT.value, None, None, None, None, None

            if token_nonce not in valid_nonces:
                self.context.logger.info(
                    f"Token nonce {token_nonce} is not in valid_nonces={valid_nonces}"
                )
                return Event.WAIT.value, None, None, None, None, None

            available_actions = []
            for t in self.synchronized_data.meme_coins:
                if t["token_nonce"] == token_nonce:
                    available_actions = t["available_actions"]
                    break

            if action not in available_actions:
                self.context.logger.info(
                    f"Action [{action}] is not in available_actions={available_actions}"
                )
                return Event.WAIT.value, None, None, None, None, None

            if not tweet:
                self.context.logger.info("Tweet is none")
                return Event.WAIT.value, None, None, None, None, None

            # Fix amount if it is lower than the min required amount
            if action == "heart":
                amount = max(
                    amount,
                    self.get_min_deploy_value(),
                )

            self.context.logger.info("The LLM returned a valid response")
            return Event.DONE.value, token_nonce, token_address, action, amount, tweet

        # The response is not a valid json
        except (json.JSONDecodeError, ValueError) as e:
            self.context.logger.error(f"Error loading the LLM response: {e}")
            return Event.WAIT.value, None, None, None, None, None
