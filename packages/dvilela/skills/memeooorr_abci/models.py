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

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from aea.skills.base import SkillContext

from packages.dvilela.skills.memeooorr_abci.rounds import MemeooorrAbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.agent_db_abci.models import (
    AgentDBClient as BaseAgentDBClient,
)
from packages.valory.skills.agent_db_abci.models import (
    AgentsFunDatabase as BaseAgentsFunDatabase,
)
from packages.valory.skills.mech_interact_abci.models import MechParams


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MemeooorrAbciApp

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Init"""
        super().__init__(*args, skill_context=skill_context, **kwargs)
        self.twitter_username: Optional[str] = None
        self.twitter_id: Optional[str] = None

        self.req_to_callback: Dict[str, Tuple[Callable, Dict[str, Any]]] = {}
        self.sufficient_funds_for_x402_payments: Optional[bool] = None


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool
AgentDBClient = BaseAgentDBClient
AgentsFunDatabase = BaseAgentsFunDatabase


class RandomnessApi(ApiSpecs):
    """A model that wraps ApiSpecs for randomness api specifications."""


@dataclass(frozen=True)
class AlternativeModelForTweets:  # pylint: disable=too-many-instance-attributes
    """The configuration for the alternative LLM models."""

    use: bool
    url: str
    api_key: str | None
    model: str
    max_tokens: int
    top_p: int
    top_k: int
    presence_penalty: int
    frequency_penalty: int
    temperature: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlternativeModelForTweets":
        """Create an instance from a dictionary."""
        api_key = data["api_key"]
        # Treat empty, whitespace-only strings, or placeholder string as None
        if api_key is not None and (
            api_key == ""
            or (
                isinstance(api_key, str) and (api_key.isspace() or api_key == "${str:}")
            )
        ):
            api_key = None

        return cls(
            use=api_key is not None,
            url=data["url"],
            api_key=api_key,
            model=data["model"],
            max_tokens=data["max_tokens"],
            top_p=data["top_p"],
            top_k=data["top_k"],
            presence_penalty=data["presence_penalty"],
            frequency_penalty=data["frequency_penalty"],
            temperature=data["temperature"],
        )


class Params(MechParams):  # pylint: disable=too-many-instance-attributes
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.service_endpoint = self._ensure("service_endpoint", kwargs, str)
        self.minimum_gas_balance = self._ensure("minimum_gas_balance", kwargs, float)
        self.min_feedback_replies = self._ensure("min_feedback_replies", kwargs, int)
        self.meme_factory_address_base = self._ensure(
            "meme_factory_address_base", kwargs, str
        )
        self.meme_factory_address_celo = self._ensure(
            "meme_factory_address_celo", kwargs, str
        )
        self.olas_token_address_base = self._ensure(
            "olas_token_address_base", kwargs, str
        )
        self.olas_token_address_celo = self._ensure(
            "olas_token_address_celo", kwargs, str
        )
        self.service_registry_address_base = self._ensure(
            "service_registry_address_base", kwargs, str
        )
        self.service_registry_address_celo = self._ensure(
            "service_registry_address_celo", kwargs, str
        )
        self.persona = self._ensure("persona", kwargs, str)
        self.home_chain_id = self._ensure("home_chain_id", kwargs, str)

        self.meme_factory_deployment_block_base = self._ensure(
            "meme_factory_deployment_block_base", kwargs, int
        )
        self.meme_factory_deployment_block_celo = self._ensure(
            "meme_factory_deployment_block_celo", kwargs, int
        )
        self.meme_subgraph_url = self._ensure("meme_subgraph_url", kwargs, str)
        self.skip_engagement = self._ensure("skip_engagement", kwargs, bool)

        self.min_summon_amount_base = self._ensure(
            "min_summon_amount_base", kwargs, float
        )
        self.max_summon_amount_base = self._ensure(
            "max_summon_amount_base", kwargs, float
        )
        self.max_heart_amount_base = self._ensure(
            "max_heart_amount_base", kwargs, float
        )

        self.min_summon_amount_celo = self._ensure(
            "min_summon_amount_celo", kwargs, float
        )
        self.max_summon_amount_celo = self._ensure(
            "max_summon_amount_celo", kwargs, float
        )

        self.max_heart_amount_celo = self._ensure(
            "max_heart_amount_celo", kwargs, float
        )

        self.staking_token_contract_address: str = self._ensure(
            "staking_token_contract_address", kwargs, str
        )
        self.activity_checker_contract_address: str = self._ensure(
            "activity_checker_contract_address", kwargs, str
        )
        self.fireworks_api_key: str | None = kwargs.get("fireworks_api_key", None)
        alternative_model_kwargs = kwargs["alternative_model_for_tweets"]
        alternative_model_kwargs["api_key"] = self.fireworks_api_key
        self.alternative_model_for_tweets: AlternativeModelForTweets = (
            AlternativeModelForTweets.from_dict(alternative_model_kwargs)
        )
        self.tx_loop_breaker_count = self._ensure("tx_loop_breaker_count", kwargs, int)

        self.tools_for_mech: dict = self._ensure("tools_for_mech", kwargs, None)

        self.summon_cooldown_seconds = self._ensure(
            "summon_cooldown_seconds", kwargs, int
        )
        self.store_path = self._ensure("store_path", kwargs, str)
        self.heart_cooldown_hours = self._ensure("heart_cooldown_hours", kwargs, int)

        self.is_memecoin_logic_enabled = self._ensure(
            "is_memecoin_logic_enabled", kwargs, bool
        )
        self.genai_api_key: str = self._ensure("genai_api_key", kwargs, str)
        self.x402_payment_requirements: Dict[str, Any] = self._ensure(
            "x402_payment_requirements", kwargs, dict
        )
        self.lifi_quote_to_amount_url: str = self._ensure(
            "lifi_quote_to_amount_url", kwargs, str
        )
        self.base_ledger_rpc: str = self._ensure("base_ledger_rpc", kwargs, str)
        self.use_x402: bool = self._ensure("use_x402", kwargs, bool)

        super().__init__(*args, **kwargs)
