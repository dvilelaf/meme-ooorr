# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2025 Valory AG
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


"""This module contains the handlers for the 'agent_performance_summary' skill."""

from typing import cast
from urllib.parse import urlparse

from packages.dvilela.skills.memeooorr_abci.dialogues import HttpDialogue
from packages.dvilela.skills.memeooorr_abci.handlers import (
    HttpHandler as BaseHttpHandler,
)
from packages.dvilela.skills.memeooorr_abci.handlers import HttpMethod
from packages.valory.protocols.http.message import HttpMessage
from packages.valory.skills.abstract_round_abci.handlers import ABCIRoundHandler
from packages.valory.skills.abstract_round_abci.handlers import (
    ContractApiHandler as BaseContractApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    IpfsHandler as BaseIpfsHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    LedgerApiHandler as BaseLedgerApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    SigningHandler as BaseSigningHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    TendermintHandler as BaseTendermintHandler,
)
from packages.valory.skills.agent_performance_summary_abci.models import SharedState


AgentPerformanceSummaryABCIHandler = ABCIRoundHandler
SigningHandler = BaseSigningHandler
LedgerApiHandler = BaseLedgerApiHandler
ContractApiHandler = BaseContractApiHandler
TendermintHandler = BaseTendermintHandler
IpfsHandler = BaseIpfsHandler


class HttpHandler(BaseHttpHandler):
    """This implements the echo handler."""

    def setup(self) -> None:
        """Implement the setup."""

        super().setup()
        config_uri_base_hostname = urlparse(
            self.context.params.service_endpoint
        ).hostname

        ip_regex = r"(\d{1,3}\.){3}\d{1,3}"

        # Route regexes
        hostname_regex = rf".*({config_uri_base_hostname}|{ip_regex}|localhost)(:\d+)?"
        self.handler_url_regex = (  # pylint: disable=attribute-defined-outside-init
            rf"{hostname_regex}\/.*"
        )

        route_regexes = {
            "performance_summary_url": rf"{hostname_regex}\/performance-summary",
        }

        # Routes
        self.routes = {  # pylint: disable=attribute-defined-outside-init
            **self.routes,  # persisting routes from base class
            (HttpMethod.GET.value, HttpMethod.HEAD.value): [
                (
                    route_regexes["performance_summary_url"],
                    self._get_performance_summary,
                ),
                *(self.routes.get((HttpMethod.GET.value, HttpMethod.HEAD.value)) or []),
            ],
        }

    @property
    def shared_state(self) -> SharedState:
        """Get the parameters."""
        return cast(SharedState, self.context.state)

    def _get_performance_summary(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Get the agent performance summary."""

        performance_summary = self.shared_state.read_existing_performance_summary()

        self._send_ok_response(http_msg, http_dialogue, performance_summary.to_json())
