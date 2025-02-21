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

"""This package contains round behaviours of DecisionMakingAbciApp."""

import json
from abc import ABC
from typing import Any, Dict, Generator, Optional, Set, Type, cast, Tuple

from aea.protocols.base import Message

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.skills.decision_making_abci.models import (
    Params,
    SharedState,
    ToolOutput,
)
from packages.dvilela.skills.decision_making_abci.rounds import (
    DecisionMakingAbciApp,
    DecisionMakingPayload,
    DecisionMakingRound,
    Event,
    SynchronizedData,
    SystemEvent
)
from packages.valory.protocols.srr.dialogues import SrrDialogue, SrrDialogues
from packages.valory.protocols.srr.message import SrrMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.models import Requests


class DecisionMakingBaseBehaviour(
    BaseBehaviour, ABC
):  # pylint: disable=too-many-ancestors,too-many-public-methods
    """Base behaviour for the memeooorr_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
        """Return the params."""
        return cast(Params, super().params)

    @property
    def local_state(self) -> SharedState:
        """Return the state."""
        return cast(SharedState, self.context.state)

    def _do_connection_request(
        self,
        message: Message,
        dialogue: Message,
        timeout: Optional[float] = None,
    ) -> Generator[None, None, Message]:
        """Do a request and wait the response, asynchronously."""

        self.context.outbox.put_message(message=message)
        request_nonce = self._get_request_nonce_from_dialogue(dialogue)  # type: ignore
        cast(Requests, self.context.requests).request_id_to_callback[
            request_nonce
        ] = self.get_callback_request()
        response = yield from self.wait_for_message(timeout=timeout)
        return response

    def _call_genai(
        self,
        prompt: str,
        schema: Optional[Dict] = None,
        temperature: Optional[float] = None,
    ) -> Generator[None, None, Optional[str]]:
        """Send a request message from the skill context."""

        payload_data: Dict[str, Any] = {"prompt": prompt}

        if schema is not None:
            payload_data["schema"] = schema

        if temperature is not None:
            payload_data["temperature"] = temperature

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(GENAI_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(payload_data),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        return response_json["response"]  # type: ignore


class DecisionMakingBehaviour(
    DecisionMakingBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event, system_event = yield from self.get_next_event()

            payload = DecisionMakingPayload(
                sender=self.context.agent_address,
                event=event.value,
                system_event=system_event
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

    def get_next_event(self) -> Generator[None, None, Tuple[Event, tool_args]]:
        """Get the next event."""

        tool_output = self.synchronized_data.tool_output

        self.context.logger(f"Tool output: {tool_output}")

        # If tool output is null, this is the first time we are running the decision making
        if tool_output is None:
            event = yield from self.call_llm(self.params.system_prompt)
            return event

        # If the tool is done, we call the LLM
        if tool_output.status == ToolOutput.Status.DONE:
            event = yield from self.call_llm(tool_output.data)
            return event

        # If the tool has failed, we call the LLM
        if tool_output.status == ToolOutput.Status.FAILED:
            event = yield from self.call_llm(tool_output.data)
            return event

        # If the tool is in progress, we return the current event
        if tool_output.status == ToolOutput.Status.IN_PROGRESS:
            # If we have just settled a transaction, we re-enter the tool
            if self.synchronized_data.final_tx_hash is not None:
                event = self.get_event_for_target_round(tool_output.reentry_point)
                return event

            # The tool has a request
            if tool_output.request == ToolOutput.Request.SETTLE:
                return Event.SETTLE

    def get_event_for_target_round(self, target_round) -> Optional[Event]:
        """Get the corresponding event for a given target round."""
        tfun = self.round_sequence.abci_app.transition_function
        for event, round_ in tfun[self.matching_round].items():
            if round_ == target_round:
                return event
        return None

    def call_llm(self, prompt) -> Generator[None, None, Event]:
        """Call the LLM"""
        self.context.logger.info("Calling the LLM")

        llm_response = yield from self._call_genai(
            prompt=prompt,
            schema=build_llm_response_schema(),
        )
        self.context.logger.info(f"LLM response: {llm_response}")


class DecisionMakingRoundBehaviour(AbstractRoundBehaviour):
    """DecisionMakingRoundBehaviour"""

    initial_behaviour_cls = DecisionMakingBehaviour
    abci_app_cls = DecisionMakingAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        DecisionMakingBehaviour,
    ]
