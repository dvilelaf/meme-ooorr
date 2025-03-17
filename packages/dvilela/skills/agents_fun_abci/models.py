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

"""This module contains the shared state for the abci skill of AgentsFunChainedSkillAbciApp."""

from typing import Any

from aea.skills.base import SkillContext

from packages.dvilela.skills.agents_fun_abci.composition import (
    AgentsFunChainedSkillAbciApp,
)
from packages.dvilela.skills.decision_making_abci.models import (
    Params as DecisionMakingParams,
)
from packages.dvilela.skills.decision_making_abci.models import (
    RandomnessApi as DecisionMakingRandomnessApi,
)
from packages.dvilela.skills.decision_making_abci.rounds import (
    Event as DecisionMakingEvent,
)
from packages.dvilela.skills.engage_twitter_abci.models import (
    Params as EngageTwitterParams,
)
from packages.dvilela.skills.engage_twitter_abci.rounds import (
    Event as EngageTwitterEvent,
)
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.reset_pause_abci.rounds import Event as ResetPauseEvent
from packages.valory.skills.termination_abci.models import TerminationParams


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool
RandomnessApi = DecisionMakingRandomnessApi

MARGIN = 5
MULTIPLIER = 100


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = AgentsFunChainedSkillAbciApp

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Init"""
        super().__init__(*args, skill_context=skill_context, **kwargs)
        self.env_var_status: dict = {"needs_update": False, "env_vars": {}}

    def setup(self) -> None:
        """Set up."""
        super().setup()

        AgentsFunChainedSkillAbciApp.event_to_timeout[
            ResetPauseEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds

        AgentsFunChainedSkillAbciApp.event_to_timeout[
            ResetPauseEvent.RESET_AND_PAUSE_TIMEOUT
        ] = (self.context.params.reset_pause_duration + MARGIN)

        AgentsFunChainedSkillAbciApp.event_to_timeout[
            DecisionMakingEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds

        AgentsFunChainedSkillAbciApp.event_to_timeout[
            EngageTwitterEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds


class Params(  # pylint: disable=too-many-ancestors
    DecisionMakingParams,
    EngageTwitterParams,
    TerminationParams,
):
    """A model to represent params for multiple abci apps."""
