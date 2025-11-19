# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2025 Valory AG
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

"""This module contains the behaviour of the skill which is responsible for agent performance summary file updation."""

from typing import Any, Dict, Generator, List, Optional, Set, Type, cast

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.base import BaseTxPayload
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.agent_performance_summary_abci.models import (
    AgentPerformanceMetrics,
    AgentPerformanceSummary,
    AgentPerformanceSummaryParams,
    SharedState,
)
from packages.valory.skills.agent_performance_summary_abci.payloads import (
    FetchPerformanceDataPayload,
)
from packages.valory.skills.agent_performance_summary_abci.rounds import (
    AgentPerformanceSummaryAbciApp,
    FetchPerformanceDataRound,
)


DEFAULT_MECH_FEE = 1e16  # 0.01 ETH
QUESTION_DATA_SEPARATOR = "\u241f"
PREDICT_MARKET_DURATION_DAYS = 4

INVALID_ANSWER_HEX = (
    "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)

PERCENTAGE_FACTOR = 100
WEI_IN_ETH = 10**18  # 1 ETH = 10^18 wei

NA = "N/A"


class FetchPerformanceSummaryBehaviour(
    MemeooorrBaseBehaviour,
):
    """A behaviour to fetch and store the agent performance summary file."""

    matching_round = FetchPerformanceDataRound

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Behaviour."""
        super().__init__(**kwargs)
        self._agent_performance_summary: Optional[AgentPerformanceSummary] = None

    @property
    def shared_state(self) -> SharedState:
        """Return the shared state."""
        return cast(SharedState, self.context.state)

    @property
    def params(self) -> AgentPerformanceSummaryParams:
        """Return the skill params."""
        return cast(AgentPerformanceSummaryParams, self.context.params)

    def _get_total_likes_and_retweets(self) -> Generator:
        """Get total likes and retweets from Twitter activity over the last prediction market duration."""
        yield from self.init_own_twitter_details()

        response: List[Dict] | Dict = yield from self._call_tweepy(
            method="get_user_tweets_with_public_metrics",
            **{
                "user_id": self.shared_state.twitter_id,
            },
        )
        if isinstance(response, dict) and "error" in response:
            self.context.logger.warning(
                f"Could not fetch tweets for user ID {self.shared_state.twitter_id}: {response['error']}"
            )
            return None, None

        all_tweets: List[Dict] = response
        total_likes = 0
        total_impressions = 0
        for tweet in all_tweets:
            total_likes += tweet.get("like_count", 0)
            total_impressions += tweet.get("impression_count", 0)

        return total_likes, total_impressions

    def should_fetch_metrics_again(self) -> bool:
        """Check if we should fetch the metrics again based on the TTL."""
        existing_data = self.shared_state.read_existing_performance_summary()
        if not existing_data.timestamp:
            self.context.logger.info("No existing data found.")
            return True

        if any(metric.value == NA for metric in existing_data.metrics):
            self.context.logger.info("Existing data has N/A metrics.")
            return True
        if (
            existing_data.timestamp + self.params.performance_summary_ttl
            > self.shared_state.synced_timestamp
        ):
            self.context.logger.info(
                "Agent performance summary was updated recently. Skipping to avoid rate limits."
            )
            return False
        return True

    def _fetch_agent_performance_summary(self) -> Generator:
        """Fetch the agent performance summary"""
        current_timestamp = self.shared_state.synced_timestamp

        total_likes, total_impressions = yield from self._get_total_likes_and_retweets()

        metrics = []

        metrics.append(
            AgentPerformanceMetrics(
                name="Total Impressions",
                is_primary=True,
                description="Total number of tweet impressions overall",
                value=str(total_impressions) if total_impressions is not None else NA,
            )
        )

        metrics.append(
            AgentPerformanceMetrics(
                name="Total Likes",
                is_primary=False,
                description="Total number of likes overall",
                value=str(total_likes) if total_likes is not None else NA,
            )
        )

        self._agent_performance_summary = AgentPerformanceSummary(
            timestamp=current_timestamp, metrics=metrics, agent_behavior=None
        )

    def _save_agent_performance_summary(
        self, agent_performance_summary: AgentPerformanceSummary
    ) -> None:
        """Save the agent performance summary to a file."""
        existing_data = self.shared_state.read_existing_performance_summary()
        agent_performance_summary.agent_behavior = existing_data.agent_behavior
        self.shared_state.overwrite_performance_summary(agent_performance_summary)

    def async_act(self) -> Generator:
        """Do the action."""
        if not self.params.is_agent_performance_summary_enabled:
            self.context.logger.info(
                "Agent performance summary is disabled. Skipping fetch and save."
            )
            payload = FetchPerformanceDataPayload(
                sender=self.context.agent_address,
                vote=False,
            )
            yield from self.finish_behaviour(payload)
            return

        if not self.should_fetch_metrics_again():
            payload = FetchPerformanceDataPayload(
                sender=self.context.agent_address,
                vote=False,
            )
            yield from self.finish_behaviour(payload)
            return

        with self.context.benchmark_tool.measure(self.behaviour_id).local():

            yield from self._fetch_agent_performance_summary()

            success = all(
                metric.value != NA for metric in self._agent_performance_summary.metrics
            )
            if not success:
                self.context.logger.warning(
                    "Agent performance summary could not be fetched. Saving default values"
                )
            self._save_agent_performance_summary(self._agent_performance_summary)
            payload = FetchPerformanceDataPayload(
                sender=self.context.agent_address,
                vote=success,
            )

        yield from self.finish_behaviour(payload)

    def finish_behaviour(self, payload: BaseTxPayload) -> Generator:
        """Finish the behaviour."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class AgentPerformanceSummaryRoundBehaviour(AbstractRoundBehaviour):
    """This behaviour manages the consensus stages for the AgentPerformanceSummary behaviour."""

    initial_behaviour_cls = FetchPerformanceSummaryBehaviour
    abci_app_cls = AgentPerformanceSummaryAbciApp
    behaviours: Set[Type[BaseBehaviour]] = {FetchPerformanceSummaryBehaviour}  # type: ignore
