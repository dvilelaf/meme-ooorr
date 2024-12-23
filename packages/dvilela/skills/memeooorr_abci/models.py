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

"""This module contains the shared state for the abci skill of MemeooorrAbciApp."""

from typing import Any

from packages.dvilela.skills.memeooorr_abci.rounds import MemeooorrAbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MemeooorrAbciApp


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool


class RandomnessApi(ApiSpecs):
    """A model that wraps ApiSpecs for randomness api specifications."""


class Params(BaseParams):  # pylint: disable=too-many-instance-attributes
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.service_endpoint = self._ensure("service_endpoint", kwargs, str)
        self.minimum_gas_balance = self._ensure("minimum_gas_balance", kwargs, float)
        self.min_feedback_replies = self._ensure("min_feedback_replies", kwargs, int)
        self.meme_factory_address = self._ensure("meme_factory_address", kwargs, str)
        self.olas_token_address = self._ensure("olas_token_address", kwargs, str)
        self.service_registry_address_base = self._ensure(
            "service_registry_address_base", kwargs, str
        )
        self.service_registry_address_celo = self._ensure(
            "service_registry_address_celo", kwargs, str
        )
        self.persona = self._ensure("persona", kwargs, str)
        self.feedback_period_min_hours = self._ensure(
            "feedback_period_min_hours", kwargs, int
        )
        self.feedback_period_max_hours = self._ensure(
            "feedback_period_max_hours", kwargs, int
        )
        self.home_chain_id = self._ensure("home_chain_id", kwargs, str)
        self.twitter_username = self._ensure("twitter_username", kwargs, str)
        self.tools_to_description = self._ensure("tools_to_description", kwargs, dict)

        super().__init__(*args, **kwargs)
