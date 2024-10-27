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
    skip_next_tweet: bool


@dataclass(frozen=True)
class PostTweetPayload(BaseTxPayload):
    """Represent a transaction payload for the PostTweetRound."""

    tweet: Optional[str]


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