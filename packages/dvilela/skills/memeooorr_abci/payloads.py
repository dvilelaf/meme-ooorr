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

"""This module contains the transaction payloads of the MemeooorrAbciApp."""

from dataclasses import dataclass
from typing import Optional

from packages.valory.skills.abstract_round_abci.base import BaseTxPayload


@dataclass(frozen=True)
class LoadDatabasePayload(BaseTxPayload):
    """Represent a transaction payload for the LoadDatabaseRound."""

    persona: str
    heart_cooldown_hours: int
    summon_cooldown_seconds: int
    agent_details: str


@dataclass(frozen=True)
class CheckStakingPayload(BaseTxPayload):
    """Represent a transaction payload for the CheckStakingRound."""

    is_staking_kpi_met: Optional[bool]


@dataclass(frozen=True)
class PullMemesPayload(BaseTxPayload):
    """Represent a transaction payload for the PullMemesRound."""

    meme_coins: Optional[str] = None
    event: Optional[str] = None


@dataclass(frozen=True)
class CollectFeedbackPayload(BaseTxPayload):
    """Represent a transaction payload for the CollectFeedbackRound."""

    feedback: Optional[str]


@dataclass(frozen=True)
class EngageTwitterPayload(BaseTxPayload):
    """Represent a transaction payload for the EngageTwitterRound."""

    event: str
    mech_request: Optional[str]
    tx_submitter: str
    failed_mech: Optional[bool] = False


@dataclass(frozen=True)
class ActionDecisionPayload(
    BaseTxPayload
):  # pylint: disable=too-many-instance-attributes
    """Represent a transaction payload for the ActionDecisionRound."""

    event: str
    action: Optional[str]
    token_address: Optional[str]
    token_nonce: Optional[int]
    token_name: Optional[str]
    token_ticker: Optional[str]
    token_supply: Optional[int]
    amount: Optional[float]
    tweet: Optional[str]
    new_persona: Optional[str]
    timestamp: Optional[float] = 0


@dataclass(frozen=True)
class ActionPreparationPayload(BaseTxPayload):
    """Represent a transaction payload for the ActionPreparationRound."""

    tx_hash: Optional[str]
    tx_submitter: str


@dataclass(frozen=True)
class ActionTweetPayload(BaseTxPayload):
    """Represent a transaction payload for the ActionTweetRound."""

    event: str


@dataclass(frozen=True)
class CheckFundsPayload(BaseTxPayload):
    """Represent a transaction payload for the CheckFundsRound."""

    event: str
    check_funds_count: int


@dataclass(frozen=True)
class PostTxDecisionMakingPayload(BaseTxPayload):
    """Represent a transaction payload for the PostTxDecisionMakingRound."""

    event: str


@dataclass(frozen=True)
class CallCheckpointPayload(BaseTxPayload):
    """A transaction payload for the checkpoint call."""

    tx_submitter: str
    tx_hash: Optional[str]


@dataclass(frozen=True)
class MechPayload(BaseTxPayload):
    """Represent a transaction payload for Mech-related rounds.

    Used for PostMechRequestRound, FailedMechRequestRound, and FailedMechResponseRound.
    """

    mech_for_twitter: bool
    failed_mech: Optional[bool] = False


@dataclass(frozen=True)
class TransactionLoopCheckPayload(BaseTxPayload):
    """A transaction payload for the checkpoint call."""

    counter: int
