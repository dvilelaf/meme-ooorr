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
import random
from typing import Generator, Optional, Tuple, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import (
    ALTERNATIVE_MODEL_TOKEN_PROMPT,
    ENFORCE_ACTION_COMMAND,
    TOKEN_DECISION_PROMPT,
    build_token_action_schema,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    ActionDecisionPayload,
    ActionDecisionRound,
    Event,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


JSON_RESPONSE_REGEX = r"json.?({.*})"

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

MIN_TOKEN_SUPPLY = 10**24  # 1M ETH in wei


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
                action,
                token_address,
                token_nonce,
                token_name,
                token_ticker,
                token_supply,
                amount,
                tweet,
                new_persona,
            ) = yield from self.get_event()

            payload = ActionDecisionPayload(
                sender=self.context.agent_address,
                event=event,
                action=action,
                token_address=token_address,
                token_nonce=token_nonce,
                token_name=token_name,
                token_ticker=token_ticker,
                token_supply=token_supply,
                amount=amount,
                tweet=tweet,
                new_persona=new_persona,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-statements
        self,
    ) -> Generator[
        None,
        None,
        Tuple[
            str,
            Optional[str],
            Optional[str],
            Optional[int],
            Optional[str],
            Optional[str],
            Optional[int],
            Optional[float],
            Optional[str],
            Optional[str],
        ],
    ]:
        """Get the next event"""

        # Filter out tokens with no available actions and
        # randomly sort to avoid the LLM to always selecting the first ones
        meme_coins = self.synchronized_data.meme_coins
        random.shuffle(meme_coins)
        meme_coins_str = "\n".join(
            TOKEN_SUMMARY.format(**meme_coin)
            for meme_coin in meme_coins
            if meme_coin["available_actions"]
        )

        self.context.logger.info(f"Action options:\n{meme_coins_str}")

        valid_nonces = [c["token_nonce"] for c in self.synchronized_data.meme_coins]

        native_balances = yield from self.get_native_balance()
        safe_native_balance = native_balances["safe"]
        if not safe_native_balance:
            safe_native_balance = 0

        tweets = yield from self.get_tweets_from_db()
        latest_tweet = tweets[-1]["text"] if tweets else "No previous tweet"

        tweet_responses = "\n\n".join(
            [
                f"tweet: {t['text']}\nviews: {t['view_count']}\nquotes: {t['quote_count']}\nretweets{t['retweet_count']}"
                for t in self.synchronized_data.feedback
            ]
        )

        is_staking_kpi_met = self.synchronized_data.is_staking_kpi_met
        extra_command = ENFORCE_ACTION_COMMAND if is_staking_kpi_met is False else ""

        prompt_data = {
            "meme_coins": meme_coins_str,
            "latest_tweet": latest_tweet,
            "tweet_responses": tweet_responses,
            "balance": safe_native_balance,
            "ticker": self.get_native_ticker(),
            "extra_command": extra_command,
        }

        llm_response = yield from self._call_genai(
            method="generate_content",
            kwargs={
                "prompt": TOKEN_DECISION_PROMPT.format(**prompt_data),
                "schema": build_token_action_schema(),
            },
        )
        self.context.logger.info(f"LLM response: {llm_response}")

        # We didnt get a response
        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return (
                Event.WAIT.value,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )

        try:
            response = json.loads(llm_response)
            action_name = response.get("action_name", "none")
            action = response.get(action_name, {})
            new_persona = response.get("new_persona", None)
            tweet = response.get("action_tweet", None)

            # Optionally, replace the tweet with one generated by the alternative LLM
            current_persona = yield from self.get_persona()
            new_tweet = yield from self.replace_tweet_with_alternative_model(
                prompt=ALTERNATIVE_MODEL_TOKEN_PROMPT.format(
                    persona=current_persona, meme_coins=meme_coins_str, action=action
                )
            )
            tweet = new_tweet or tweet

            token_name = action.get("token_name", None)
            token_ticker = action.get("token_ticker", None)
            token_supply = action.get("token_supply", None)
            amount = int(action.get("amount", 0))
            token_nonce = action.get("token_nonce", None)
            token_address = action.get("token_address", None)

            if isinstance(token_nonce, str) and token_nonce.isdigit():
                token_nonce = int(token_nonce)

            if isinstance(token_supply, str) and token_supply.isdigit():
                token_supply = int(token_supply)

            if isinstance(token_supply, int):
                token_supply = max(token_supply, MIN_TOKEN_SUPPLY)

            if action_name == "none":
                self.context.logger.info("Action is none")
                return (
                    Event.WAIT.value,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )

            if action_name in ["heart", "unleash"] and token_nonce not in valid_nonces:
                self.context.logger.info(
                    f"Token nonce {token_nonce} is not in valid_nonces={valid_nonces}"
                )
                return (
                    Event.WAIT.value,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )

            available_actions = []
            for t in self.synchronized_data.meme_coins:
                if t["token_nonce"] == token_nonce:
                    available_actions = t["available_actions"]
                    break

            if action_name != "summon" and action_name not in available_actions:
                self.context.logger.info(
                    f"Action [{action_name}] is not in available_actions={available_actions}"
                )
                return (
                    Event.WAIT.value,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )

            # Fix amounts
            if action_name == "summon":
                chain_id = self.get_chain_id()

                amount = max(
                    amount,
                    int(getattr(self.params, f"min_summon_amount_{chain_id}") * 1e18),
                )
                amount = min(
                    amount,
                    int(getattr(self.params, f"max_summon_amount_{chain_id}") * 1e18),
                )

                if token_name.lower() in ["olas"] or token_ticker.lower() in ["olas"]:
                    raise ValueError(
                        f"Cannot summon token with name/ticker {token_name}/{token_ticker}. Invalid name or ticker."
                    )

            if action_name == "heart":
                chain_id = self.get_chain_id()

                amount = max(
                    amount,
                    1,  # 1 wei
                )
                amount = min(
                    amount,
                    int(getattr(self.params, f"max_heart_amount_{chain_id}") * 1e18),
                )

            self.context.logger.info("The LLM returned a valid response")
            if new_persona:
                yield from self._write_kv({"persona": new_persona})
            return (
                Event.DONE.value,
                action_name,
                token_address,
                token_nonce,
                token_name,
                token_ticker,
                token_supply,
                amount,
                tweet,
                new_persona,
            )

        # The response is not a valid json
        except (json.JSONDecodeError, ValueError) as e:
            self.context.logger.error(f"Error loading the LLM response: {e}")
            return (
                Event.WAIT.value,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
