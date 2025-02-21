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

"""This module contains the shared state for the abci skill of DecisionMakingAbciApp."""


from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from packages.dvilela.skills.decision_making_abci.rounds import DecisionMakingAbciApp
from packages.dvilela.skills.decision_making_abci.prompts import DEFAULT_SYSTEM_PROMPT
from packages.valory.skills.abstract_round_abci.models import BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = DecisionMakingAbciApp


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool


class Params(BaseParams):  # pylint: disable=too-many-instance-attributes
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.system_prompt = kwargs.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        super().__init__(*args, **kwargs)


@dataclass
class ToolOutput:
    """ToolOutput"""

    class Status(Enum):
        """Status"""

        DONE = "done"
        FAILED = "failed"
        IN_PROGRESS = "in_progress"

    class Request(Enum):
        """Request"""

        SETTLE = "settle"
        MECH = "mech"

    tool_name: str
    status: Status
    request: Request
    reentry_point: Optional[str]
    data: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary."""
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "request": self.request.value,
            "reentry_point": self.reentry_point,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolOutput":
        """Create an instance from a dictionary."""
        return cls(
            tool_name=data["tool_name"],
            status=cls.Status(data["status"]),
            request=cls.Request(data["request"]),
            reentry_point=data["reentry_point"],
            data=data["data"],
        )

    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"ToolOutput(tool_name={self.tool_name}, status={self.status}, request={self.request}, reentry_point={self.reentry_point}, data={self.data})"
