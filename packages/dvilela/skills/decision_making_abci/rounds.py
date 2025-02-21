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

"""This package contains the rounds of DecisionMakingAbciApp."""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple

from packages.dvilela.skills.decision_making_abci.models import ToolOutput
from packages.dvilela.skills.decision_making_abci.payloads import DecisionMakingPayload
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
)
import pickle
from dataclasses import dataclass


class Event(Enum):
    """DecisionMakingAbciApp Events"""

    DONE = "done"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    SETTLE = "settle"


@dataclass(frozen=True)
class SystemEvent:
    """SystemEvent"""

    tool_event: Event
    tool_arguments: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary."""
        return {
            "tool_event": self.tool_event,
            "tool_arguments": self.tool_arguments.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemEvent":
        """Create an instance from a dictionary."""
        return cls(
            tool_event=data["tool_event"],
            tool_arguments=data["tool_arguments"],
        )

    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"SystemEvent(tool_event={self.tool_event}, tool_arguments={self.tool_arguments}"


def build_llm_response_schema() -> dict:
    """Build a schema for the llm response"""
    return {"class": pickle.dumps(SystemEvent).hex(), "is_list": False}


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def final_tx_hash(self) -> Optional[str]:
        """Get the verified tx hash."""
        return self.db.get("final_tx_hash", None)

    @property
    def tool_output(self) -> Optional[ToolOutput]:
        """Get the tool output."""
        tool_output = self.db.get("tool_output", None)
        if not tool_output:
            return None
        return ToolOutput.from_dict(self.db.get("tool_output"))


class DecisionMakingRound(CollectSameUntilThresholdRound):
    """DecisionMakingPayload"""

    payload_class = DecisionMakingPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            event = Event(self.most_voted_payload)
            return self.synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class FinishedToSettlementRound(DegenerateRound):
    """FinishedToSettlementRound"""


class FinishedToResetRound(DegenerateRound):
    """FinishedToResetRound"""


class DecisionMakingAbciApp(AbciApp[Event]):
    """DecisionMakingAbciApp"""

    initial_round_cls: AppState = DecisionMakingRound
    initial_states: Set[AppState] = {
        DecisionMakingRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DecisionMakingRound: {
            Event.DONE: FinishedToResetRound,
            Event.SETTLE: FinishedToSettlementRound,
            Event.NO_MAJORITY: DecisionMakingRound,
            Event.ROUND_TIMEOUT: DecisionMakingRound,
        },
        FinishedToSettlementRound: {},
        FinishedToResetRound: {},
    }
    final_states: Set[AppState] = {
        FinishedToSettlementRound,
        FinishedToResetRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = set()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        DecisionMakingRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedToSettlementRound: {"most_voted_tx_hash"},
        FinishedToResetRound: set(),
    }
