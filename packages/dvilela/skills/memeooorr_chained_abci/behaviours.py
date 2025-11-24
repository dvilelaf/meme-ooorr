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

"""This package contains round behaviours of MemeooorrChainedSkillAbci."""

from typing import Set, Type

from packages.dvilela.skills.memeooorr_abci.behaviours import MemeooorrRoundBehaviour
from packages.dvilela.skills.memeooorr_chained_abci.composition import (
    MemeooorrChainedSkillAbciApp,
)
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.agent_performance_summary_abci.behaviours import (
    AgentPerformanceSummaryRoundBehaviour,
)
from packages.valory.skills.mech_interact_abci.behaviours.round_behaviour import (
    MechInteractRoundBehaviour,
)
from packages.valory.skills.registration_abci.behaviours import (
    AgentRegistrationRoundBehaviour,
    RegistrationStartupBehaviour,
)
from packages.valory.skills.reset_pause_abci.behaviours import (
    ResetPauseABCIConsensusBehaviour,
)
from packages.valory.skills.termination_abci.behaviours import (
    BackgroundBehaviour,
    TerminationAbciBehaviours,
)
from packages.valory.skills.transaction_settlement_abci.behaviours import (
    TransactionSettlementRoundBehaviour,
)


class MemeooorrChainedConsensusBehaviour(AbstractRoundBehaviour):
    """Class to define the behaviours this AbciApp has."""

    initial_behaviour_cls = RegistrationStartupBehaviour
    abci_app_cls = MemeooorrChainedSkillAbciApp
    behaviours: Set[Type[BaseBehaviour]] = {
        *AgentRegistrationRoundBehaviour.behaviours,
        *AgentPerformanceSummaryRoundBehaviour.behaviours,
        *ResetPauseABCIConsensusBehaviour.behaviours,
        *MemeooorrRoundBehaviour.behaviours,
        *TerminationAbciBehaviours.behaviours,
        *TransactionSettlementRoundBehaviour.behaviours,
        *MechInteractRoundBehaviour.behaviours,
    }
    background_behaviours_cls = {BackgroundBehaviour}
