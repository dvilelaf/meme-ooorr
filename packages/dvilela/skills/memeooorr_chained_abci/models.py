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

"""This module contains the shared state for the abci skill of MemeooorrChainedSkillAbciApp."""

from typing import Any

from aea.skills.base import SkillContext

from packages.dvilela.skills.memeooorr_abci.models import (
    AgentDBClient as BaseAgentDBClient,
)
from packages.dvilela.skills.memeooorr_abci.models import (
    AgentsFunDatabase as BaseAgentsFunDatabase,
)
from packages.dvilela.skills.memeooorr_abci.models import Params as MemeooorrParams
from packages.dvilela.skills.memeooorr_abci.models import (
    RandomnessApi as MemeooorrRandomnessApi,
)
from packages.dvilela.skills.memeooorr_abci.rounds import Event as MemeooorrEvent
from packages.dvilela.skills.memeooorr_chained_abci.composition import (
    MemeooorrChainedSkillAbciApp,
)
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.agent_performance_summary_abci.models import (
    AgentPerformanceSummaryParams,
)
from packages.valory.skills.agent_performance_summary_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.mech_interact_abci.models import (
    MechResponseSpecs as BaseMechResponseSpecs,
)
from packages.valory.skills.mech_interact_abci.rounds import Event as MechInteractEvent
from packages.valory.skills.reset_pause_abci.rounds import Event as ResetPauseEvent
from packages.valory.skills.termination_abci.models import TerminationParams


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool
RandomnessApi = MemeooorrRandomnessApi
MechResponseSpecs = BaseMechResponseSpecs
AgentDBClient = BaseAgentDBClient
AgentsFunDatabase = BaseAgentsFunDatabase

MARGIN = 5
MULTIPLIER = 10
MULTIPLIER_MECH = 20


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MemeooorrChainedSkillAbciApp  # type: ignore[assignment]

    def __init__(self, *args: Any, skill_context: SkillContext, **kwargs: Any) -> None:
        """Init"""
        super().__init__(*args, skill_context=skill_context, **kwargs)
        self.env_var_status: dict = {"needs_update": False, "env_vars": {}}

    def setup(self) -> None:
        """Set up."""
        super().setup()

        MemeooorrChainedSkillAbciApp.event_to_timeout[
            ResetPauseEvent.ROUND_TIMEOUT
        ] = self.context.params.round_timeout_seconds

        MemeooorrChainedSkillAbciApp.event_to_timeout[
            ResetPauseEvent.RESET_AND_PAUSE_TIMEOUT
        ] = (self.context.params.reset_pause_duration + MARGIN)

        MemeooorrChainedSkillAbciApp.event_to_timeout[MemeooorrEvent.ROUND_TIMEOUT] = (
            self.context.params.round_timeout_seconds * MULTIPLIER
        )

        # adding time for the mech interaction
        MemeooorrChainedSkillAbciApp.event_to_timeout[
            MechInteractEvent.ROUND_TIMEOUT
        ] = (
            self.context.params.round_timeout_seconds * MULTIPLIER_MECH
        )  # need to introduce a parameter for this


class Params(
    MemeooorrParams, TerminationParams, AgentPerformanceSummaryParams
):  # pylint: disable=too-many-ancestors
    """A model to represent params for multiple abci apps."""
