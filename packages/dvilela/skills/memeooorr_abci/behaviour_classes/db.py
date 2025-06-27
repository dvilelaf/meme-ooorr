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
from typing import Generator, Tuple, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    HOUR_TO_SECONDS,
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    LoadDatabasePayload,
    LoadDatabaseRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


class LoadDatabaseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """LoadDatabaseBehaviour"""

    matching_round: Type[AbstractRound] = LoadDatabaseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            (
                persona,
                hearting_cooldown_hours,
                summon_cooldown_seconds,
            ) = yield from self.load_db()
            yield from self.populate_keys_in_kv()
            yield from self.init_own_twitter_details()
            agent_details = self.gather_agent_details(persona)

            yield from self._write_kv({"agent_details": agent_details})

            payload = LoadDatabasePayload(
                sender=self.context.agent_address,
                persona=persona,
                agent_details=agent_details,
                heart_cooldown_hours=hearting_cooldown_hours,
                summon_cooldown_seconds=summon_cooldown_seconds,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def load_db(self) -> Generator[None, None, Tuple[str, int, int]]:
        """Load the data"""
        persona = yield from self.get_persona()
        heart_cooldown_hours = yield from self.get_heart_cooldown_hours()
        summon_cooldown_seconds = yield from self.get_summon_cooldown_seconds()
        self.context.logger.info(
            f"Loaded from the db\npersona={persona}\nheart_cooldown_hours={heart_cooldown_hours}\nsummon_cooldown_seconds={summon_cooldown_seconds}"
        )
        yield from self.context.agents_fun_db.load()
        return persona, heart_cooldown_hours, summon_cooldown_seconds

    def populate_keys_in_kv(self) -> Generator[None, None, None]:
        """This function is used to populate the keys in the KV store which are required in EngageTwitterRound."""
        yield from self._write_kv({"previous_tweets_for_tw_mech": ""})
        yield from self._write_kv({"other_tweets_for_tw_mech": ""})
        yield from self._write_kv({"interacted_tweet_ids_for_tw_mech": ""})
        yield from self._write_kv({"pending_tweets_for_tw_mech": ""})

        # Initialize last summon
        db_data = yield from self._read_kv(keys=("last_summon_timestamp",))
        if db_data is None or db_data.get("last_summon_timestamp", None) is None:
            yield from self._write_kv(
                {"last_summon_timestamp": str(self.get_sync_timestamp())}
            )

        # Initialize last heart if not present then set it to 48 hours ago to make sure the agent can heart first time it is deployed
        db_data = yield from self._read_kv(keys=("last_heart_timestamp",))
        if db_data is None or db_data.get("last_heart_timestamp", None) is None:
            yield from self._write_kv(
                {
                    "last_heart_timestamp": str(
                        self.get_sync_timestamp()
                        - self.params.heart_cooldown_hours * HOUR_TO_SECONDS
                    )
                }
            )

    def gather_agent_details(self, persona: str) -> str:
        """Write the agent details to the db."""
        agent_details = {
            "twitter_username": self.context.agents_fun_db.my_agent.twitter_username,
            "twitter_user_id": self.context.agents_fun_db.my_agent.twitter_user_id,
            "safe_address": self.synchronized_data.safe_contract_address,
            "persona": persona,
            "twitter_display_name": self.context.state.twitter_display_name,
        }
        agent_details_str = json.dumps(agent_details)
        return agent_details_str
