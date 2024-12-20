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
    latest_tweet: Optional[str]


@dataclass(frozen=True)
class PostTweetPayload(BaseTxPayload):
    """Represent a transaction payload for the PostTweetRound."""

    latest_tweet: Optional[str]
    feedback_period_max_hours_delta: int = 0


@dataclass(frozen=True)
class CollectFeedbackPayload(BaseTxPayload):
    """Represent a transaction payload for the CollectFeedbackRound."""

    feedback: Optional[str]


@dataclass(frozen=True)
class AnalizeFeedbackPayload(BaseTxPayload):
    """Represent a transaction payload for the AnalizeFeedbackRound."""

    analysis: Optional[str]


@dataclass(frozen=True)
class CheckFundsPayload(BaseTxPayload):
    """Represent a transaction payload for the CheckFundsRound."""

    event: str


@dataclass(frozen=True)
class DeploymentPayload(BaseTxPayload):
    """Represent a transaction payload for the DeploymentRound."""

    tx_hash: Optional[str]
    tx_flag: Optional[str]
    token_nonce: Optional[int] = None


@dataclass(frozen=True)
class PullMemesPayload(BaseTxPayload):
    """Represent a transaction payload for the PullMemesRound."""

    meme_coins: Optional[str]


@dataclass(frozen=True)
class ActionDecisionPayload(BaseTxPayload):
    """Represent a transaction payload for the ActionDecisionRound."""

    event: str
    token_nonce: Optional[int]
    token_address: Optional[str]
    action: Optional[str]
    amount: Optional[float]
    tweet: Optional[str]


@dataclass(frozen=True)
class ActionPreparationPayload(BaseTxPayload):
    """Represent a transaction payload for the ActionPreparationRound."""

    tx_hash: Optional[str]
    tx_flag: Optional[str]


@dataclass(frozen=True)
class ActionTweetPayload(BaseTxPayload):
    """Represent a transaction payload for the ActionTweetRound."""

    event: str


@dataclass(frozen=True)
class TransactionMultiplexerPayload(BaseTxPayload):
    """Represent a transaction payload for the TransactionMultiplexerRound."""

    event: str


@dataclass(frozen=True)
class EngagePayload(BaseTxPayload):
    """Represent a transaction payload for the EngageRound."""

    event: str
