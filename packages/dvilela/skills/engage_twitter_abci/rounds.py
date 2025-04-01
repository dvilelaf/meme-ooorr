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

"""This package contains the rounds of MemeooorrAbciApp."""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple

from packages.dvilela.skills.engage_twitter_abci.payloads import EngageTwitterPayload
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    BaseTxPayload,
    CollectSameUntilThresholdRound,
    DegenerateRound,
    EventToTimeout,
    get_name
)
from packages.dvilela.skills.decision_making_abci.tool_output import ToolOutput


class Event(Enum):
    """MemeooorrAbciApp Events"""

    DONE = "done"
    ERROR = "error"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    @property
    def tool_output(self) -> Optional[ToolOutput]:
        """Get the tool output."""
        tool_output = self.db.get("tool_output", None)
        if not tool_output:
            return None
        return ToolOutput.from_dict(self.db.get("tool_output"))


class EventRoundBase(CollectSameUntilThresholdRound):
    """EventRoundBase"""

    synchronized_data_class = SynchronizedData
    payload_class = BaseTxPayload  # will be overwritten
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            event = Event(self.most_voted_payload)
            synchronized_data = self.synchronized_data

            if event == Event.DONE:

                tool_output = ToolOutput.from_dict({
                    "tool_name": "engage_twitter",
                    "status": ToolOutput.Status.DONE,
                    "request": ToolOutput.Request.NONE,
                    "reentry_point": None,
                    "message": "Engage Twitter has finished succesfully",
                })
                synchronized_data = self.synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(SynchronizedData.tool_output): tool_output.to_dict(),
                    },
                )

            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class EngageTwitterRound(EventRoundBase):
    """EngageTwitterRound"""

    payload_class = EngageTwitterPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.ERROR, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class FinishedEngageTwitterRound(DegenerateRound):
    """FinishedEngageTwitterRound"""


class FinishedEngageTwitterErrorRound(DegenerateRound):
    """FinishedEngageTwitterErrorRound"""


class EngageTwitterAbciApp(AbciApp[Event]):
    """EngageTwitterAbciApp"""

    initial_round_cls: AppState = EngageTwitterRound
    initial_states: Set[AppState] = {
        EngageTwitterRound,
    }
    transition_function: AbciAppTransitionFunction = {
        EngageTwitterRound: {
            Event.DONE: FinishedEngageTwitterRound,
            Event.ERROR: FinishedEngageTwitterErrorRound,
            Event.NO_MAJORITY: EngageTwitterRound,
            Event.ROUND_TIMEOUT: EngageTwitterRound,
        },
        FinishedEngageTwitterRound: {},
        FinishedEngageTwitterErrorRound: {},
    }
    final_states: Set[AppState] = {
        FinishedEngageTwitterRound,
        FinishedEngageTwitterErrorRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset(["persona"])
    db_pre_conditions: Dict[AppState, Set[str]] = {
        EngageTwitterRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedEngageTwitterRound: set(),
        FinishedEngageTwitterErrorRound: set(),
    }
