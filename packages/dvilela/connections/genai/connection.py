#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2024 David Vilela Freire
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

"""Genai connection."""

import importlib
import json
import pickle  # nosec
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, cast

import google.generativeai as genai  # type: ignore
from aea.configurations.base import PublicId
from aea.connections.base import BaseSyncConnection
from aea.mail.base import Envelope
from aea.protocols.base import Address, Message
from aea.protocols.dialogue.base import Dialogue
from google.api_core.exceptions import InternalServerError, ResourceExhausted

from packages.valory.protocols.srr.dialogues import SrrDialogue
from packages.valory.protocols.srr.dialogues import SrrDialogues as BaseSrrDialogues
from packages.valory.protocols.srr.message import SrrMessage


PUBLIC_ID = PublicId.from_str("dvilela/genai:0.1.0")

DEFAULT_TEMPERATURE = 2.0


class SrrDialogues(BaseSrrDialogues):
    """A class to keep track of SRR dialogues."""

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize dialogues.

        :param kwargs: keyword arguments
        """

        def role_from_first_message(  # pylint: disable=unused-argument
            message: Message, receiver_address: Address
        ) -> Dialogue.Role:
            """Infer the role of the agent from an incoming/outgoing first message

            :param message: an incoming/outgoing first message
            :param receiver_address: the address of the receiving agent
            :return: The role of the agent
            """
            return SrrDialogue.Role.CONNECTION

        BaseSrrDialogues.__init__(
            self,
            self_address=str(kwargs.pop("connection_id")),
            role_from_first_message=role_from_first_message,
            **kwargs,
        )


class GenaiConnection(BaseSyncConnection):
    """Proxy to the functionality of the Genai library."""

    MAX_WORKER_THREADS = 1

    connection_id = PUBLIC_ID

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        """
        Initialize the connection.

        The configuration must be specified if and only if the following
        parameters are None: connection_id, excluded_protocols or restricted_to_protocols.

        Possible arguments:
        - configuration: the connection configuration.
        - data_dir: directory where to put local files.
        - identity: the identity object held by the agent.
        - crypto_store: the crypto store for encrypted communication.
        - restricted_to_protocols: the set of protocols ids of the only supported protocols for this connection.
        - excluded_protocols: the set of protocols ids that we want to exclude for this connection.

        :param args: arguments passed to component base
        :param kwargs: keyword arguments passed to component base
        """
        super().__init__(*args, **kwargs)
        genai_api_key = self.configuration.config.get("genai_api_key")
        genai.configure(api_key=genai_api_key)
        self.last_call = datetime.now(timezone.utc)

        self.model = None
        self.chat = None

        self.dialogues = SrrDialogues(connection_id=PUBLIC_ID)

    def main(self) -> None:
        """
        Run synchronous code in background.

        SyncConnection `main()` usage:
        The idea of the `main` method in the sync connection
        is to provide for a way to actively generate messages by the connection via the `put_envelope` method.

        A simple example is the generation of a message every second:
        ```
        while self.is_connected:
            envelope = make_envelope_for_current_time()
            self.put_enevelope(envelope)
            time.sleep(1)
        ```
        In this case, the connection will generate a message every second
        regardless of envelopes sent to the connection by the agent.
        For instance, this way one can implement periodically polling some internet resources
        and generate envelopes for the agent if some updates are available.
        Another example is the case where there is some framework that runs blocking
        code and provides a callback on some internal event.
        This blocking code can be executed in the main function and new envelops
        can be created in the event callback.
        """

    def on_send(self, envelope: Envelope) -> None:
        """
        Send an envelope.

        :param envelope: the envelope to send.
        """
        srr_message = cast(SrrMessage, envelope.message)

        dialogue = self.dialogues.update(srr_message)

        if srr_message.performative != SrrMessage.Performative.REQUEST:
            self.logger.error(
                f"Performative `{srr_message.performative.value}` is not supported."
            )
            return

        payload, error = self._get_response(
            payload=json.loads(srr_message.payload),
        )

        response_message = cast(
            SrrMessage,
            dialogue.reply(  # type: ignore
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps(payload),
                error=error,
            ),
        )

        response_envelope = Envelope(
            to=envelope.sender,
            sender=envelope.to,
            message=response_message,
            context=envelope.context,
        )

        self.put_envelope(response_envelope)

    def _get_response(self, payload: dict) -> Tuple[Dict, bool]:
        """Get response from Genai."""

        # Check properties
        REQUIRED_PROPERTIES = ["method"]

        if not all(i in payload for i in REQUIRED_PROPERTIES):
            return {
                "error": f"Some parameter is missing from the request data: required={REQUIRED_PROPERTIES}, got={list(payload.keys())}"
            }, True

        # Check method
        AVAILABLE_METHODS = [
            "generate_content",
            "start_chat",
            "send_message",
        ]

        method_name = payload.get("method")

        if method_name not in AVAILABLE_METHODS:
            return {
                "error": f"Method {method_name} is not in the list of available methods {AVAILABLE_METHODS}"
            }, True

        method = getattr(self, method_name)

        # Check model
        AVAILABLE_MODELS = [
            "gemini-2.0-flash",
        ]

        model_name = payload.get("model", "gemini-2.0-flash")
        if model_name not in AVAILABLE_MODELS:
            return {
                "error": f"Model {model_name} is not an available model [{AVAILABLE_MODELS}]"
            }, True

        self.logger.info(f"Calling genai: {payload}")

        try:
            # Avoid calling more than 1 time every 5 seconds (API limit is 15 req/min for flash)
            while (datetime.now(timezone.utc) - self.last_call).total_seconds() < 5:
                time.sleep(1)

            response, error = method(**payload.get("kwargs", {}))

            self.logger.info(f"LLM response: {response.text}")
            self.last_call = datetime.now(timezone.utc)
        except Exception as e:
            return {"error": f"Exception while calling Genai:\n{e}"}, True

        return response, error  # type: ignore

    def on_connect(self) -> None:
        """
        Tear down the connection.

        Connection status set automatically.
        """

    def on_disconnect(self) -> None:
        """
        Tear down the connection.

        Connection status set automatically.
        """

    def generate_content(self, model_name, prompt, **kwargs) -> Tuple[Dict, bool]:
        """Generate content (one shot)"""

        model = genai.GenerativeModel(model_name)

        generation_config_kwargs = {
            "temperature": kwargs.get("temperature", DEFAULT_TEMPERATURE)
        }

        if "schema" in kwargs:
            schema = kwargs["schema"]
            schema_class = pickle.loads(bytes.fromhex(schema["class"]))  # nosec
            generation_config_kwargs["response_mime_type"] = "application/json"
            is_list = schema.get("is_list", False)
            if not is_list:
                generation_config_kwargs["response_schema"] = schema_class
            else:
                generation_config_kwargs["response_schema"] = list[schema_class]  # type: ignore

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                **generation_config_kwargs,
            ),
        )

        return {"response": response.text}, False

    def start_chat(self, model_name, tool_dict) -> Tuple[Dict, bool]:
        """Start a chat"""

        # Recreate callable functions from tool_dict
        tools = [
            getattr(importlib.import_module(module_name), function_name)
            for module_name, function_name in tool_dict.items()
        ]
        self.model = genai.GenerativeModel(model_name=model_name, tools=tools)
        self.chat = self.model.start_chat()
        return None, False

    def send_message(self, message) -> Tuple[Dict, bool]:
        """Send a message to the chat"""

        while True:
            try:
                response = self.chat.send_message(message)
                return {"response": response}, False
            except ResourceExhausted:
                print("Hit rate limit. Retrying...")
                time.sleep(10)
            except InternalServerError as e:
                print(f"InternalServerError: {e}. Retrying...")
                time.sleep(10)
