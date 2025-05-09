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

"""This package contains round behaviours of MemeooorrAbciApp."""

import json
import re
from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import (
    Any,
    ClassVar,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from aea.protocols.base import Message
from aea.skills.base import SkillContext
from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.kv_store.connection import (
    PUBLIC_ID as KV_STORE_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.mirror_db.connection import (
    PUBLIC_ID as MIRRORDB_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.tweepy.connection import (
    PUBLIC_ID as TWEEPY_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
from packages.dvilela.contracts.service_registry.contract import ServiceRegistryContract
from packages.dvilela.protocols.kv_store.dialogues import (
    KvStoreDialogue,
    KvStoreDialogues,
)
from packages.dvilela.protocols.kv_store.message import KvStoreMessage
from packages.dvilela.skills.memeooorr_abci.models import Params, SharedState
from packages.dvilela.skills.memeooorr_abci.rounds import SynchronizedData
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.protocols.srr.dialogues import SrrDialogue, SrrDialogues
from packages.valory.protocols.srr.message import SrrMessage
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.abstract_round_abci.models import Requests


BASE_CHAIN_ID = "base"
CELO_CHAIN_ID = "celo"
HTTP_OK = 200
MEMEOOORR_DESCRIPTION_PATTERN = r"^Memeooorr @(\w+)$"
IPFS_ENDPOINT = "https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
MAX_TWEET_CHARS = 280
AGENT_TYPE_NAME = "memeooorr"


TOKENS_QUERY = """
query Tokens($limit: Int, $after: String) {
  memeTokens(limit: $limit, after: $after, orderBy: "summonTime", orderDirection: "asc") {
    items {
      blockNumber
      chain
      heartCount
      id
      isUnleashed
      isPurged
      liquidity
      lpPairAddress
      owner
      timestamp
      memeNonce
      summonTime
      unleashTime
      memeToken
      name
      symbol
      hearters
    }
  }
}
"""

PACKAGE_QUERY = """
query getPackages($package_type: String!) {
    units(where: {packageType: $package_type}) {
        id,
        packageType,
        publicId,
        packageHash,
        tokenId,
        metadataHash,
        description,
        owner,
        image
    }
}
"""


def is_tweet_valid(tweet: str) -> bool:
    """Checks a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"] <= MAX_TWEET_CHARS


@dataclass
class AttributeDefinitionParams:
    """Parameters for creating an attribute definition."""

    attr_def_name: str
    agent_type_id: int
    agent_id: int
    data_type: str
    is_required: bool
    default_value: str


class MirrorDBHelper:  # pylint: disable=too-many-locals
    """Helper class to encapsulate MirrorDB interactions."""

    _HTTP_METHOD_TO_CONNECTION_METHOD: ClassVar[Dict[str, str]] = {
        "GET": "read_",
        "POST": "create_",
        "PUT": "update_",
        "DELETE": "delete_",
    }

    def __init__(self, behaviour: "MemeooorrBaseBehaviour") -> None:
        """Initialize the MirrorDB helper."""
        self.behaviour = behaviour

    @property
    def context(self) -> SkillContext:
        """Get the behaviour context."""
        return self.behaviour.context

    @property
    def params(self) -> Params:
        """Return the params."""
        return self.behaviour.params

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return self.behaviour.synchronized_data

    # --- Core MirrorDB Interaction Methods ---

    def _get_mirrordb_connection_method(self, http_method: str) -> Optional[str]:
        """Map HTTP method to MirrorDB connection method."""
        connection_method = self._HTTP_METHOD_TO_CONNECTION_METHOD.get(
            http_method.upper()
        )
        if not connection_method:
            self.context.logger.error(
                f"Unsupported HTTP method for MirrorDB call: {http_method}"
            )
            return None
        return connection_method

    @staticmethod
    def _build_mirrordb_request_payload(
        connection_method: str, endpoint: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Build the payload for the MirrorDB SRR request."""
        connection_kwargs = {
            "endpoint": endpoint,
            **kwargs,  # Pass through data, auth, etc.
        }
        return {"method": connection_method, "kwargs": connection_kwargs}

    def _send_mirrordb_request(
        self, payload: Dict[str, Any]
    ) -> Generator[None, None, Message]:
        """Send the SRR request to the MirrorDB connection."""
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(MIRRORDB_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(payload),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        # Assuming self.behaviour exists and has do_connection_request
        response = yield from self.behaviour.do_connection_request(
            srr_message, srr_dialogue  # type: ignore
        )
        return response

    def _parse_mirrordb_response(
        self, response_message: Message
    ) -> Optional[Dict[str, Any]]:
        """Parse the JSON response from MirrorDB."""
        try:
            # Check if response_message is None before accessing payload
            self.context.logger.info(
                f"Response message in _parse_mirrordb_response: {response_message}"
            )
            if response_message is None:
                self.context.logger.error(
                    "Received None response message from MirrorDB."
                )
                return None
            return json.loads(response_message.payload)  # type: ignore
        except json.JSONDecodeError as e:
            self.context.logger.error(
                f"Failed to decode JSON response from MirrorDB: {e}. Payload: {getattr(response_message, 'payload', 'N/A')}"
            )
            return None
        except AttributeError:
            self.context.logger.error(
                f"Response message object lacks 'payload' attribute: {response_message}"
            )
            return None

    def _handle_mirrordb_error(
        self,
        error_message: Any,
        http_method: str,
        endpoint: str,
        connection_method: str,
    ) -> None:
        """Log MirrorDB errors, distinguishing 404s."""
        is_404 = isinstance(error_message, str) and "Status 404" in error_message
        log_prefix = f"MirrorDB call ({http_method} {endpoint} -> {connection_method})"
        if is_404:
            self.context.logger.info(
                f"{log_prefix}: Resource not found (Expected 404)."
            )
        else:
            self.context.logger.error(f"{log_prefix} failed: {error_message}")

    def _log_mirrordb_exception(
        self,
        exception: Exception,
        http_method: str,
        endpoint: str,
        connection_method: Optional[str],
    ) -> None:
        """Log exceptions during MirrorDB call."""
        log_method = connection_method or "unknown connection method"
        self.context.logger.error(
            f"Exception while calling MirrorDB ({http_method} {endpoint} -> {log_method}): {exception}"
        )

    def call_mirrordb(
        self, http_method: str, endpoint: str, **kwargs: Any
    ) -> Generator[None, None, Any]:
        """Send a request message to the MirrorDB connection."""
        connection_method = self._get_mirrordb_connection_method(http_method)
        if not connection_method:
            return None

        payload = MirrorDBHelper._build_mirrordb_request_payload(
            connection_method, endpoint, **kwargs
        )

        try:
            response_message = yield from self._send_mirrordb_request(payload)
            response_json = self._parse_mirrordb_response(response_message)

            if response_json is None:
                # Error logged in _parse_mirrordb_response
                return None

            if "error" in response_json:
                self._handle_mirrordb_error(
                    response_json["error"], http_method, endpoint, connection_method
                )
                return None

            return response_json.get("response")

        except Exception as e:  # pylint: disable=broad-except
            self._log_mirrordb_exception(e, http_method, endpoint, connection_method)
            return None

    def sign_mirrordb_request(
        self, endpoint: str, agent_id: int
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Signs a MirrorDB request based on timestamp and endpoint."""
        try:
            # Ensure agent_id is not None before proceeding
            if agent_id is None:
                self.context.logger.error("Cannot sign request: agent_id is None.")
                return None

            # Generate timestamp and prepare message to sign
            timestamp = int(datetime.utcnow().timestamp())
            message_to_sign = f"timestamp:{timestamp},endpoint:{endpoint}"

            # Use AEA framework signing
            signature_hex = yield from self.behaviour.get_signature(
                message_to_sign.encode("utf-8")
            )
            if not signature_hex:
                self.context.logger.error(
                    f"Failed to get signature for message: {message_to_sign}"
                )
                return None

            # Prepare authentication data
            auth_data = {
                "agent_id": agent_id,
                "signature": signature_hex,
                "message": message_to_sign,
            }
            self.context.logger.debug(f"Generated auth data for endpoint {endpoint}")
            return auth_data
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception during MirrorDB request signing for {endpoint}: {e}"
            )
            return None

    # --- Registration and Checks ---

    def _create_or_get_agent_type(
        self, agent_type_name: str
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Create or get the agent type.

        Args:
            agent_type_name: The name of the agent type

        Returns:
            Optional[Dict[str, Any]]: The agent type data if successful, None otherwise
        """
        agent_type_response = yield from self.call_mirrordb(
            "GET", endpoint=f"/api/agent-types/name/{agent_type_name}"
        )

        if agent_type_response is None:
            self.context.logger.info(
                f"Agent type {agent_type_name!r} not found. Creating..."
            )
            agent_type_create_data = {
                "type_name": agent_type_name,
                "description": "Agent type for Memeooorr skill",
            }
            agent_type_response = yield from self.call_mirrordb(
                "POST", endpoint="/api/agent-types/", data=agent_type_create_data
            )
            if agent_type_response is None:
                self.context.logger.error(
                    f"Failed to create agent type {agent_type_name!r}. Aborting registration."
                )
                return None
            self.context.logger.info(f"Created agent type: {agent_type_response}")

        return agent_type_response

    def _attempt_create_agent_registry(
        self, agent_registry_data: Dict[str, Any]
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Attempt to create an agent registry entry via POST."""
        self.context.logger.info(
            f"Attempting to create agent registry entry for address {self.context.agent_address}..."
        )
        agent_registry_response = yield from self.call_mirrordb(
            "POST",
            endpoint="/api/agent-registry/",
            data=agent_registry_data,
        )

        if agent_registry_response is None:
            self.context.logger.info(
                "Agent registry creation POST failed (potentially address already exists)."
            )
            return None

        if "agent_id" not in agent_registry_response:
            self.context.logger.error(
                "Agent registry creation response missing 'agent_id'. This is unexpected."
            )
            return None

        self.context.logger.info(
            f"Agent registry entry created successfully: {agent_registry_response}"
        )
        return agent_registry_response

    def _attempt_fetch_agent_registry_by_address(
        self,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Attempt to fetch an existing agent registry entry via GET by address."""
        fetch_endpoint = f"/api/agent-registry/address/{self.context.agent_address}"
        self.context.logger.info(
            f"Attempting to fetch existing entry for address {self.context.agent_address} from {fetch_endpoint}..."
        )
        existing_agent_response = yield from self.call_mirrordb(
            "GET", endpoint=fetch_endpoint
        )

        if existing_agent_response is None:
            # call_mirrordb logs 404 or other errors
            self.context.logger.error(
                f"Failed to fetch agent registry entry from {fetch_endpoint}."
            )
            return None

        if "agent_id" not in existing_agent_response:
            self.context.logger.error(
                f"Fetched existing agent registry entry from {fetch_endpoint} is missing 'agent_id'."
            )
            return None

        self.context.logger.info(
            f"Successfully fetched existing agent registry entry: {existing_agent_response}"
        )
        return existing_agent_response

    def _create_agent_registry_entry(
        self, agent_type_id: int
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Create or get an agent registry entry.

        First attempts to create the entry. If creation fails (e.g., address exists),
        it attempts to fetch the existing entry by address.

        Args:
            agent_type_id: The ID of the agent type

        Returns:
            Optional[Dict[str, Any]]: The registry entry data if successful, None otherwise
        """
        agent_registry_data = {
            "agent_name": f"{self.synchronized_data.safe_contract_address}_{datetime.utcnow().isoformat()}",
            "type_id": agent_type_id,
            "eth_address": self.context.agent_address,
        }

        # Attempt to create the agent registry entry
        agent_registry_response = yield from self._attempt_create_agent_registry(
            agent_registry_data
        )

        # If creation was successful, return the response
        if agent_registry_response is not None:
            return agent_registry_response

        # If creation failed (returned None), attempt to fetch the existing entry
        self.context.logger.info(
            "Creation failed, attempting to fetch existing entry by address."
        )
        existing_agent_response = (
            yield from self._attempt_fetch_agent_registry_by_address()
        )

        # If fetching failed, log the final error and return None
        if existing_agent_response is None:
            self.context.logger.error(
                f"Failed to create OR fetch agent registry entry for address {self.context.agent_address}."
            )
            return None

        # Return the fetched existing entry
        return existing_agent_response

    def _create_or_get_attribute_definition(
        self,
        params: AttributeDefinitionParams,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Create or get an attribute definition.

        Args:
            params: The parameters for creating/getting the attribute definition

        Returns:
            Optional[Dict[str, Any]]: The attribute definition data if successful, None otherwise
        """
        attr_def_response = yield from self.call_mirrordb(
            "GET", endpoint=f"/api/attributes/name/{params.attr_def_name}"
        )

        if attr_def_response is None:
            self.context.logger.info(
                f"Attribute definition {params.attr_def_name!r} not found. Creating..."
            )
            attr_def_payload = {
                "type_id": params.agent_type_id,
                "attr_name": params.attr_def_name,
                "data_type": params.data_type,
                "is_required": params.is_required,
                "default_value": params.default_value,
            }
            attr_def_endpoint = f"/api/agent-types/{params.agent_type_id}/attributes/"
            auth_data = yield from self.sign_mirrordb_request(
                attr_def_endpoint, params.agent_id
            )
            if auth_data is None:
                self.context.logger.error(
                    f"Failed to sign attribute definition creation request for {params.attr_def_name!r}. Aborting."
                )
                return None

            request_body = {
                "attr_def": attr_def_payload,
                "auth": auth_data,
            }
            attr_def_response = yield from self.call_mirrordb(
                "POST",
                endpoint=attr_def_endpoint,
                data=request_body,
            )
            if attr_def_response is None:
                self.context.logger.error(
                    f"Failed to create attribute definition {params.attr_def_name!r}."
                )

        return attr_def_response

    def _create_username_attribute_instance(
        self,
        agent_id: int,
        attr_def_id: int,
        username: str,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Create a username attribute instance.

        Args:
            agent_id: The ID of the agent
            attr_def_id: The ID of the attribute definition
            username: The username value

        Returns:
            Optional[Dict[str, Any]]: The attribute instance data if successful, None otherwise
        """
        attr_instance_payload = {
            "agent_id": agent_id,
            "attr_def_id": attr_def_id,
            "string_value": username,
            "integer_value": None,
            "float_value": None,
            "boolean_value": None,
            "date_value": None,
            "json_value": None,
        }
        attr_instance_endpoint = f"/api/agents/{agent_id}/attributes/"
        auth_data = yield from self.sign_mirrordb_request(
            attr_instance_endpoint, agent_id
        )
        if auth_data is None:
            self.context.logger.error(
                "Failed to sign attribute instance creation request for username."
            )
            return None

        request_body = {
            "agent_attr": attr_instance_payload,
            "auth": auth_data,
        }
        return (
            yield from self.call_mirrordb(
                "POST",
                endpoint=attr_instance_endpoint,
                data=request_body,
            )
        )

    def _get_validated_twitter_user_details(
        self,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Fetches and validates required Twitter user details."""
        twitter_user_data = yield from self.behaviour.get_twitter_user_data()
        if not twitter_user_data:
            self.context.logger.error(
                "Failed to get Twitter user data. Registration cannot proceed."
            )
            return None

        user_id = twitter_user_data.get("id")
        username = twitter_user_data.get("screen_name")
        name = twitter_user_data.get("name")

        if not all([user_id, username, name]):
            self.context.logger.error(
                f"Missing required Twitter data: id={user_id}, username={username}, name={name}. Registration cannot proceed."
            )
            return None

        return {
            "twitter_user_id": user_id,
            "twitter_username": username,
            "twitter_name": name,
        }

    def _ensure_attribute_definition_and_update_config(
        self,
        config_data: Dict[str, Any],
        params: AttributeDefinitionParams,
        config_key: str,
    ) -> Generator[None, None, Optional[int]]:
        """
        Ensures an attribute definition exists (or creates it) and updates the config dict.

        Args:
            config_data: The configuration dictionary being built.
            params: Parameters for the attribute definition.
            config_key: The key in config_data to store the attr_def_id.

        Returns:
            The attribute definition ID if successful, None otherwise.
        """
        attr_def_response = yield from self._create_or_get_attribute_definition(
            params=params
        )

        if attr_def_response and "attr_def_id" in attr_def_response:
            attr_def_id = attr_def_response["attr_def_id"]
            self.context.logger.info(
                f"Using attribute definition {params.attr_def_name!r} with attr_def_id: {attr_def_id}"
            )
            config_data[config_key] = attr_def_id
            return attr_def_id

        # Code below this line was previously inside the 'else' block
        self.context.logger.error(
            f"Could not find or create attribute definition {params.attr_def_name!r}. Response: {attr_def_response}"
        )
        # Set the config key to None to indicate failure for this specific attribute
        config_data[config_key] = None
        return None

    def _get_existing_username_attribute(
        self, agent_id: int, username_attr_def_id: int
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Fetches the existing username attribute instance from MirrorDB."""
        get_endpoint = f"/api/agents/{agent_id}/attributes/{username_attr_def_id}/"
        self.context.logger.info(
            f"Checking existing username attribute for agent {agent_id} via GET {get_endpoint}"
        )
        existing_attribute = yield from self.call_mirrordb("GET", endpoint=get_endpoint)
        # call_mirrordb handles logging for 404 or other errors
        return existing_attribute

    def _update_username_attribute_instance(
        self,
        agent_id: int,
        attribute_id: int,
        username_attr_def_id: int,
        current_twitter_username: str,
    ) -> Generator[None, None, bool]:
        """Updates an existing username attribute instance via PUT request."""
        update_endpoint = f"/api/agent-attributes/{attribute_id}"
        # Include all required fields in the payload for the PUT request
        update_payload = {
            "agent_id": agent_id,
            "attr_def_id": username_attr_def_id,
            "string_value": current_twitter_username,
            # Explicitly set others to None or their existing values if needed,
            # assuming the Pydantic model handles partial updates correctly if others are omitted.
            # Based on the 422 error, agent_id and attr_def_id seem required.
            # Let's keep it minimal first and only add what the error mentioned.
        }
        auth_data_update = yield from self.sign_mirrordb_request(
            update_endpoint, agent_id
        )

        if not auth_data_update:
            self.context.logger.error(
                f"Failed to sign username attribute update request for agent {agent_id} (attribute {attribute_id})."
            )
            return False

        request_body_update = {
            "agent_attr": update_payload,
            "auth": auth_data_update,
        }
        update_response = yield from self.call_mirrordb(
            "PUT",
            endpoint=update_endpoint,
            data=request_body_update,
        )
        if update_response:
            self.context.logger.info(
                f"Successfully updated username attribute for agent {agent_id} (attribute {attribute_id})."
            )
            return True

        # Log includes MirrorDB API error if available
        self.context.logger.error(
            f"Failed to update username attribute for agent {agent_id} (attribute {attribute_id})."
        )
        return False

    def _create_username_attribute_instance_via_post(
        self, agent_id: int, username_attr_def_id: int, current_twitter_username: str
    ) -> Generator[None, None, bool]:
        """Creates a new username attribute instance via POST request."""
        create_endpoint = f"/api/agents/{agent_id}/attributes/"
        create_payload = {
            "agent_id": agent_id,
            "attr_def_id": username_attr_def_id,
            "string_value": current_twitter_username,
            "integer_value": None,
            "float_value": None,
            "boolean_value": None,
            "date_value": None,
            "json_value": None,
        }
        auth_data_create = yield from self.sign_mirrordb_request(
            create_endpoint, agent_id
        )

        if not auth_data_create:
            self.context.logger.error(
                f"Failed to sign username attribute creation request for agent {agent_id}."
            )
            return False

        request_body_create = {
            "agent_attr": create_payload,
            "auth": auth_data_create,
        }
        create_response = yield from self.call_mirrordb(
            "POST",
            endpoint=create_endpoint,
            data=request_body_create,
        )
        if create_response:
            self.context.logger.info(
                f"Successfully created username attribute for agent {agent_id}."
            )
            return True
        self.context.logger.error(
            f"Failed to create username attribute for agent {agent_id}."
        )
        return False

    def _check_and_update_username_attribute(  # pylint: disable=too-many-return-statements
        self,
        agent_id: int,
        username_attr_def_id: int,
        current_twitter_username: str,
    ) -> Generator[None, None, None]:
        """Checks the stored username attribute and updates it if necessary, or creates it if missing."""

        if not current_twitter_username:
            self.context.logger.error(
                "Cannot check/update username attribute: Current Twitter username is missing."
            )
            return

        existing_attribute = yield from self._get_existing_username_attribute(
            agent_id, username_attr_def_id
        )

        if existing_attribute and isinstance(existing_attribute, dict):
            # Attribute exists, check if update is needed
            stored_username = existing_attribute.get("string_value")
            attribute_id = existing_attribute.get("attribute_id")

            if not attribute_id:
                self.context.logger.error(
                    f"Existing username attribute for agent {agent_id} is missing 'attribute_id'. Cannot update."
                )
                return  # Cannot proceed without attribute_id

            if stored_username == current_twitter_username:
                self.context.logger.info(
                    f"Stored username attribute for agent {agent_id} matches current. No update needed."
                )
                return  # No action needed

            # Update required
            self.context.logger.warning(
                f"Stored username {stored_username} differs from current {current_twitter_username}. Updating..."
            )
            # Pass username_attr_def_id to the update method
            yield from self._update_username_attribute_instance(
                agent_id, attribute_id, username_attr_def_id, current_twitter_username
            )

        else:
            # Attribute does not exist (or GET failed), create it.
            self.context.logger.info(
                f"Username attribute not found for agent {agent_id}. Attempting to create..."
            )
            yield from self._create_username_attribute_instance_via_post(
                agent_id, username_attr_def_id, current_twitter_username
            )

    def register_with_mirror_db(
        self,
    ) -> Generator[None, None, None]:
        """Register the agent with the MirrorDB service and save the configuration."""
        try:
            # 1. Get and Validate Twitter User Data (current session)
            twitter_details = yield from self._get_validated_twitter_user_details()
            if not twitter_details:
                return  # Error logged in helper

            # 2. Get or Create Agent Type
            agent_type_name = AGENT_TYPE_NAME
            agent_type_response = yield from self._create_or_get_agent_type(
                agent_type_name
            )
            if not agent_type_response or "type_id" not in agent_type_response:
                self.context.logger.error(
                    f"Could not find or create agent type {agent_type_name!r}. Response: {agent_type_response}. Registration aborted."
                )
                return
            agent_type_id = agent_type_response["type_id"]
            self.context.logger.info(
                f"Using agent type {agent_type_name!r} with type_id: {agent_type_id}"
            )

            # 3. Create or Get Agent Registry Entry
            agent_registry_response = yield from self._create_agent_registry_entry(
                agent_type_id
            )
            if not agent_registry_response or "agent_id" not in agent_registry_response:
                self.context.logger.error(
                    "Failed to obtain agent registry entry (create or fetch). Registration aborted."
                )
                return
            agent_id = agent_registry_response["agent_id"]
            stored_eth_address = agent_registry_response.get("eth_address", "N/A")
            self.context.logger.info(
                f"Using agent_id: {agent_id} (associated with address: {stored_eth_address})"
            )

            # 4. Initialize Config Data (including current username)
            config_data = {
                "agent_id": agent_id,
                "twitter_user_id": twitter_details["twitter_user_id"],
                "twitter_username": twitter_details[
                    "twitter_username"
                ],  # Store current username
                "agent_type_id": agent_type_id,
                "twitter_interactions_attr_def_id": None,
                "twitter_username_attr_def_id": None,
            }

            # 5. Ensure Username Attribute Definition exists AND Get ID
            username_params = AttributeDefinitionParams(
                attr_def_name="twitter_username",
                agent_type_id=agent_type_id,
                agent_id=agent_id,
                data_type="string",
                is_required=True,
                default_value="",
            )
            username_attr_def_id = (
                yield from self._ensure_attribute_definition_and_update_config(
                    config_data, username_params, "twitter_username_attr_def_id"
                )
            )

            # 6. Check/Update/Create Username Attribute Instance (using the ID from step 5)
            # Pass the *current* username from the live session for update/creation
            if username_attr_def_id is not None:
                yield from self._check_and_update_username_attribute(
                    agent_id=agent_id,
                    username_attr_def_id=username_attr_def_id,
                    current_twitter_username=twitter_details[
                        "twitter_username"
                    ],  # Use live username
                )
            else:
                self.context.logger.error(
                    "Skipping username attribute instance check/update because username attribute definition failed."
                )

            # 7. Ensure Interactions Attribute Definition exists AND Get ID
            interaction_params = AttributeDefinitionParams(
                attr_def_name="twitter_interactions",
                agent_type_id=agent_type_id,
                agent_id=agent_id,
                data_type="json",
                is_required=False,
                default_value="{}",
            )
            yield from self._ensure_attribute_definition_and_update_config(
                config_data,
                interaction_params,
                "twitter_interactions_attr_def_id",
            )

            # 8. Save Final Configuration (including username) to KV Store
            self.context.logger.info(
                f"Saving final consolidated MirrorDB config data: {config_data}"
            )
            yield from self.behaviour.write_kv(
                {"mirrod_db_config": json.dumps(config_data)}
            )
            self.context.logger.info("MirrorDB registration/update process completed.")

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Unexpected exception during MirrorDB registration/update: {e}",
                exc_info=True,
            )

    def _parse_and_validate_config(
        self, mirror_db_config_data: Any
    ) -> Optional[Dict[str, Any]]:
        """Parses config data (str or dict) into dict and performs basic validation."""
        if isinstance(mirror_db_config_data, str):
            try:
                mirror_db_config_data = json.loads(mirror_db_config_data)
            except json.JSONDecodeError:
                self.context.logger.error(
                    f"Failed to parse mirror_db_config JSON: {mirror_db_config_data}"
                )
                return None

        if not isinstance(mirror_db_config_data, dict):
            self.context.logger.error(
                f"mirror_db_config_data is not a dictionary after parsing: {type(mirror_db_config_data)}"
            )
            return None

        # Basic validation: Check for essential keys needed later
        required_keys = [
            "agent_id",
            "twitter_user_id",
            "twitter_username_attr_def_id",
            "twitter_username",  # Add username to required keys
        ]
        missing_keys = [
            key for key in required_keys if key not in mirror_db_config_data
        ]
        if missing_keys:
            self.context.logger.error(
                f"MirrorDB config is missing required keys: {missing_keys}. Config: {mirror_db_config_data}"
            )
            return None

        # Validate types (at least for IDs)
        try:
            int(mirror_db_config_data["agent_id"])
            # twitter_user_id is string, twitter_username is string
            int(mirror_db_config_data["twitter_username_attr_def_id"])
        except (ValueError, TypeError, KeyError):
            self.context.logger.error(
                f"Invalid type for required IDs in MirrorDB config: {mirror_db_config_data}"
            )
            return None

        return mirror_db_config_data

    def _get_current_twitter_user_id_from_cookie(
        self,
    ) -> Generator[None, None, Optional[str]]:
        """Gets and potentially parses the current Twitter User ID from cookies."""
        try:
            raw_id = (
                yield from self.behaviour.get_twitter_user_id_from_cookie()
            )  # Use the base behaviour's method

            if raw_id and isinstance(raw_id, str) and "u=" in raw_id:
                # Assuming format might include "u=" prefix
                parsed_id = raw_id.split("u=")[-1]
                if parsed_id.isdigit():
                    return parsed_id

                self.context.logger.error(
                    f"Parsed Twitter User ID is not numeric: {parsed_id} (from raw: {raw_id})"
                )
                return None
            if raw_id and isinstance(raw_id, str) and raw_id.isdigit():
                # Assuming it might just be the number directly
                return raw_id

            # If raw_id is not None but doesn't match expected formats
            self.context.logger.error(
                f"Unexpected format or type for Twitter User ID from cookie: {raw_id} ({type(raw_id)}) "
            )
            return None

        except ValueError as e:
            # _get_twitter_user_id_from_cookie raises ValueError on API error
            self.context.logger.error(
                f"Error getting Twitter User ID from cookie via behaviour: {e}"
            )
            return None

    def _ensure_mirror_db_config(self) -> Generator[None, None, Optional[str]]:
        """Reads MirrorDB config from KV, registers if missing, and returns raw config."""
        key = "mirrod_db_config"
        config_read = yield from self.behaviour.read_kv(keys=(key,))
        config_raw = config_read.get(key) if config_read else None

        if config_raw is None:
            self.context.logger.info(
                "No MirrorDB config found. Attempting registration..."
            )
            yield from self.register_with_mirror_db()  # Handles getting live data & saving
            config_read = yield from self.behaviour.read_kv(keys=(key,))
            config_raw = config_read.get(key) if config_read else None
            if config_raw is None:
                self.context.logger.error(
                    "MirrorDB config still missing after registration attempt."
                )
                return None

        return config_raw

    def _handle_twitter_id_mismatch(  # pylint: disable=too-many-arguments
        self,
        config_data: Dict[str, Any],
        agent_id: int,
        username_attr_def_id: int,
        stored_twitter_user_id: str,
        current_twitter_user_id: str,
    ) -> Generator[None, None, Tuple[Dict[str, Any], bool]]:
        """Handles the logic when stored and current Twitter User IDs don't match."""
        self.context.logger.warning(
            f"ID MISMATCH: Stored ID ({stored_twitter_user_id}) vs Cookie ID ({current_twitter_user_id}). Updating..."
        )
        needs_kv_update = True  # Always need to update KV in this case

        # Get full new details (username and confirmed ID)
        new_twitter_details = yield from self._get_validated_twitter_user_details()
        if not new_twitter_details:
            self.context.logger.error(
                "Failed to get new Twitter details after ID mismatch. Cannot update. Returning existing config."
            )
            return (
                config_data,
                False,
            )  # Return original config, indicate no update occurred for saving

        current_username = new_twitter_details["twitter_username"]
        confirmed_current_user_id = str(new_twitter_details["twitter_user_id"])

        # Sanity check IDs
        if confirmed_current_user_id != current_twitter_user_id:
            self.context.logger.error(
                f"CRITICAL ID MISMATCH: Cookie ({current_twitter_user_id}) vs Details ({confirmed_current_user_id}). Aborting update. Returning existing config."
            )
            return (
                config_data,
                False,
            )  # Return original config, indicate no update occurred for saving

        # Update MirrorDB attribute with the new username
        self.context.logger.info(
            f"Updating MirrorDB username attribute for agent {agent_id} to {current_username}."
        )
        # Use _check_and_update which handles both update and creation if needed
        yield from self._check_and_update_username_attribute(
            agent_id=agent_id,
            username_attr_def_id=username_attr_def_id,
            current_twitter_username=current_username,  # Use new username
        )

        # Update config dict locally with new ID and Username
        updated_config = config_data.copy()
        updated_config["twitter_user_id"] = confirmed_current_user_id
        updated_config["twitter_username"] = current_username
        self.context.logger.info(
            f"Locally updated config data with new ID {confirmed_current_user_id} and username {current_username}."
        )

        return updated_config, needs_kv_update

    def _handle_twitter_username_check(
        self,
        config_data: Dict[str, Any],
        agent_id: int,
        username_attr_def_id: int,
        stored_username_from_config: str,
    ) -> Generator[None, None, Tuple[Dict[str, Any], bool]]:
        """Handles username checks when Twitter IDs match."""
        needs_kv_update = False
        updated_config = config_data.copy()  # Work on a copy

        self.context.logger.info(
            "Stored Twitter User ID matches current cookie ID. Verifying username..."
        )

        # Get current live username to compare against config and DB
        current_twitter_details = yield from self._get_validated_twitter_user_details()
        if not current_twitter_details:
            self.context.logger.warning(
                "Could not get current Twitter details for username check. Skipping update checks, returning existing config."
            )
            # Proceed with existing config, maybe issue is temporary
            return updated_config, False

        current_username = current_twitter_details["twitter_username"]

        # Compare config username vs current live username
        if stored_username_from_config != current_username:
            self.context.logger.warning(
                f"USERNAME MISMATCH (Config vs Live): Stored {stored_username_from_config} vs Live {current_username}. Updating local config dict."
            )
            updated_config[
                "twitter_username"
            ] = current_username  # Update local config dict
            needs_kv_update = True  # Mark KV for update

        # Compare MirrorDB attribute vs current live username (check_and_update handles this)
        # We call this regardless of the config check result to ensure DB is synced with live data
        self.context.logger.info(
            "Verifying MirrorDB username attribute against live session..."
        )
        # Note: _check_and_update logs its own success/failure messages
        yield from self._check_and_update_username_attribute(
            agent_id=agent_id,
            username_attr_def_id=username_attr_def_id,
            current_twitter_username=current_username,  # Ensure using live username
        )

        return updated_config, needs_kv_update

    def _sync_twitter_details_in_config(
        self, config_data: Dict[str, Any]
    ) -> Generator[None, None, Tuple[Dict[str, Any], bool]]:
        """
        Synchronizes Twitter user ID and username between stored config/DB and live data.

        Returns the potentially updated config dictionary and a boolean indicating if KV needs saving.
        Raises exceptions from underlying calls on critical failures.
        """
        needs_kv_update = False
        updated_config = config_data  # Start with original validated config

        # Extract data needed for checks
        try:
            stored_twitter_user_id = str(config_data["twitter_user_id"])
            stored_username_from_config = config_data["twitter_username"]
            agent_id = int(config_data["agent_id"])
            username_attr_def_id = int(config_data["twitter_username_attr_def_id"])
        except (KeyError, ValueError, TypeError) as e:
            self.context.logger.error(
                f"Error extracting required fields from config: {e}. Config: {config_data}"
            )
            raise  # Re-raise as this indicates a problem with the validated config

        # Get current Twitter User ID from cookie
        current_twitter_user_id = (
            yield from self._get_current_twitter_user_id_from_cookie()
        )
        if current_twitter_user_id is None:
            self.context.logger.warning(
                "Could not get current Twitter User ID from cookie. Skipping mismatch check. Returning original config."
            )
            return config_data, False  # Return original config, no update needed

        # --- ID Check ---
        if current_twitter_user_id != stored_twitter_user_id:
            (
                updated_config,
                needs_kv_update,
            ) = yield from self._handle_twitter_id_mismatch(
                config_data=updated_config,  # Pass current config state
                agent_id=agent_id,
                username_attr_def_id=username_attr_def_id,
                stored_twitter_user_id=stored_twitter_user_id,
                current_twitter_user_id=current_twitter_user_id,
            )
        else:
            # --- Username Check (only if IDs matched) ---
            (
                updated_config,
                needs_kv_update,
            ) = yield from self._handle_twitter_username_check(
                config_data=updated_config,  # Pass current config state
                agent_id=agent_id,
                username_attr_def_id=username_attr_def_id,
                stored_username_from_config=stored_username_from_config,
            )

        return updated_config, needs_kv_update

    def _save_updated_config(
        self, config_data: Dict[str, Any]
    ) -> Generator[None, None, None]:
        """Saves the updated config data to the KV store."""
        self.context.logger.info("Saving updated MirrorDB config to KV store...")
        success = yield from self.behaviour.write_kv(
            {"mirrod_db_config": json.dumps(config_data)}
        )
        if success:
            self.context.logger.info("Successfully saved updated config to KV store.")
        else:
            self.context.logger.error("Failed to save updated config to KV store.")
            # Note: The calling function will still return the updated dict,
            # but persistence failed. This logs the error.

    def mirror_db_registration_check(
        self,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """
        Checks MirrorDB registration, performs registration if needed

        and verifies/updates Twitter user details based on current cookies/API.
        Returns the validated (and potentially updated) config dictionary, or None on failure.
        """
        # 1. Get raw config, register if needed
        config_raw = yield from self._ensure_mirror_db_config()
        if config_raw is None:
            # Error logged in _ensure_mirror_db_config
            return None

        # 2. Parse and validate config
        config_data = self._parse_and_validate_config(config_raw)
        if config_data is None:
            # Error logged in _parse_and_validate_config
            return None

        # 3. Sync Twitter details (ID/Username) with live data and update if needed
        try:
            (
                updated_config,
                config_was_updated,
            ) = yield from self._sync_twitter_details_in_config(
                config_data  # Pass the validated config
            )
            # 4. Save config to KV store if it was updated
            if config_was_updated:
                yield from self._save_updated_config(updated_config)

            return updated_config  # Return the final config data (potentially updated)

        except (  # pylint: disable=broad-except
            ValueError,
            TypeError,
            KeyError,
            Exception,
        ) as e:
            # Catch errors specifically from _sync_twitter_details_in_config or its callees
            self.context.logger.error(
                f"Caught exception during Twitter ID/Username synchronization: {e}. Config: {config_data}",
                exc_info=True,
            )
            # Return the originally validated config data, as the sync process failed
            return config_data

    # --- Interaction Recording ---

    def _get_post_interaction_details(
        self, kwargs: Dict[str, Any], response_json: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get interaction details for a 'post' action."""
        details: Dict[str, Any] = {}
        try:
            tweet_text = kwargs.get("tweets", [{}])[0].get("text")
            tweepy_response_list = response_json.get("response")
            tweepy_tweet_id = (
                tweepy_response_list[0]
                if isinstance(tweepy_response_list, list)
                and len(tweepy_response_list) > 0
                else None
            )

            if not tweet_text or not tweepy_tweet_id:
                self.context.logger.error(
                    f"Missing tweet text or ID from Tweepy response/kwargs for post: {kwargs}, {response_json}"
                )
                return None

            details["tweet_id"] = str(tweepy_tweet_id)
            details["text"] = tweet_text
            return details
        except (IndexError, KeyError, TypeError) as e:
            self.context.logger.error(
                f"Error processing Tweepy 'post' data for MirrorDB attribute: {e}"
            )
            return None

    def _get_like_retweet_interaction_details(
        self, method: str, kwargs: Dict[str, Any]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Get interaction action and details for 'like' or 'retweet' actions."""
        target_tweet_id = kwargs.get("tweet_id")
        if not target_tweet_id:
            self.context.logger.error(
                f"Missing tweet_id in kwargs for {method}: {kwargs}"
            )
            return None
        action = method.split("_")[0]  # "like" or "retweet"
        details = {"tweet_id": str(target_tweet_id)}
        return action, details

    def _get_follow_interaction_details(
        self, kwargs: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get interaction details for a 'follow' action."""
        target_user_id = kwargs.get("user_id")
        if not target_user_id:
            self.context.logger.error(f"Missing user_id in kwargs for follow: {kwargs}")
            return None
        return {"user_id": str(target_user_id)}

    def _get_interaction_details(
        self, method: str, kwargs: Dict[str, Any], response_json: Dict[str, Any]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Determine the interaction action and details based on the Tweepy method."""
        interaction_action: Optional[str] = None
        interaction_details: Optional[Dict[str, Any]] = None

        if method == "post":
            interaction_action = "post"
            interaction_details = self._get_post_interaction_details(
                kwargs, response_json
            )

        elif method in ["like_tweet", "retweet"]:
            result = self._get_like_retweet_interaction_details(method, kwargs)
            if result is None:
                return None
            interaction_action, interaction_details = result

        elif method == "follow_user":
            interaction_action = "follow"
            interaction_details = self._get_follow_interaction_details(kwargs)
            if interaction_details is None:
                return None

        if interaction_action is None:
            # This case should ideally not be reached if recordable_methods check passed,
            # but handle defensively.
            self.context.logger.warning(
                f"Could not determine interaction action for method {method!r} despite being recordable."
            )
            return None

        # If interaction_details is None at this point (e.g., from _get_post_interaction_details failing),
        # we should return None as the interaction couldn't be fully determined.
        if interaction_details is None:
            self.context.logger.error(
                f"Failed to get interaction details for method {method!r}"
            )  # Add more specific logging
            return None

        return interaction_action, interaction_details

    def _get_interaction_attr_def_id(self) -> Generator[None, None, Optional[int]]:
        """Retrieve and validate the twitter_interactions_attr_def_id from KV store."""
        # Read the main MirrorDB config object first
        kv_data_full = yield from self.behaviour.read_kv(keys=("mirrod_db_config",))

        if not kv_data_full or "mirrod_db_config" not in kv_data_full:
            self.context.logger.error(
                "Missing 'mirrod_db_config' in KV Store. Cannot retrieve interaction attr_def_id."
            )
            return None

        mirrod_db_config_str = kv_data_full["mirrod_db_config"]
        if not mirrod_db_config_str:
            self.context.logger.error(
                "'mirrod_db_config' is empty in KV Store. Cannot retrieve interaction attr_def_id."
            )
            return None

        try:
            config_dict = json.loads(mirrod_db_config_str)
        except json.JSONDecodeError:
            self.context.logger.error(
                f"Failed to parse 'mirrod_db_config' JSON: {mirrod_db_config_str}. Cannot retrieve interaction attr_def_id."
            )
            return None

        attr_def_id_str = config_dict.get("twitter_interactions_attr_def_id")

        if attr_def_id_str is None:
            self.context.logger.error(
                "Missing 'twitter_interactions_attr_def_id' within 'mirrod_db_config' in KV Store. Cannot record interaction."
            )
            return None

        try:
            return int(attr_def_id_str)
        except (ValueError, TypeError):
            self.context.logger.error(
                f"Invalid 'twitter_interactions_attr_def_id' format in KV Store: {attr_def_id_str}. Cannot record interaction."
            )
            return None

    @staticmethod
    def _construct_interaction_payload(
        agent_id: int,
        attr_def_id: int,
        interaction_action: str,
        interaction_details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct the payload for the MirrorDB agent attribute."""
        json_value = {
            "action": interaction_action,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "details": interaction_details,
        }
        return {
            "agent_id": agent_id,
            "attr_def_id": attr_def_id,
            "string_value": None,
            "integer_value": None,
            "float_value": None,
            "boolean_value": None,
            "date_value": None,
            "json_value": json_value,
        }

    def _send_interaction_to_mirrordb(
        self,
        agent_id: int,
        mirrordb_data: Dict[str, Any],
        method: str,  # Added method for logging context
    ) -> Generator[None, None, None]:
        """Sign and send the interaction data to MirrorDB."""
        mirrordb_method = "POST"
        mirrordb_endpoint = f"/api/agents/{agent_id}/attributes/"

        auth_data = yield from self.sign_mirrordb_request(mirrordb_endpoint, agent_id)
        if auth_data is None:
            self.context.logger.error(
                f"Failed to generate signature for {mirrordb_method} {mirrordb_endpoint}. Aborting interaction recording for method {method}."
            )
            return

        self.context.logger.info(
            f"Recording interaction via MirrorDB: {mirrordb_method} {mirrordb_endpoint} Data: {mirrordb_data} Auth: {auth_data is not None}"
        )
        try:
            request_body = {"agent_attr": mirrordb_data, "auth": auth_data}
            mirrordb_response = yield from self.call_mirrordb(
                mirrordb_method,
                endpoint=mirrordb_endpoint,
                data=request_body,
            )
            if mirrordb_response is None:
                self.context.logger.warning(
                    f"MirrorDB interaction recording for method {method} might have failed (returned None)."
                )
            else:
                self.context.logger.info(
                    f"Successfully recorded interaction for method {method}. Response: {mirrordb_response}"
                )
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception during MirrorDB interaction recording for method {method}: {e}"
            )

    def record_interaction(
        self,
        method: str,
        kwargs: Dict[str, Any],
        response_json: Dict[str, Any],
        mirror_db_config_data: Dict[str, Any],
    ) -> Generator[None, None, None]:
        """Record Tweepy interaction in MirrorDB."""
        # Check if the method is one we need to record
        recordable_methods = {"post", "like_tweet", "retweet", "follow_user"}
        if method not in recordable_methods or mirror_db_config_data is None:
            return  # Only record specific actions if config exists

        agent_id = mirror_db_config_data.get("agent_id")
        if not agent_id:
            self.context.logger.error("Missing agent_id in MirrorDB config.")
            return

        # Retrieve the stored Attribute Definition ID for twitter interactions from KV store
        attr_def_id = yield from self._get_interaction_attr_def_id()
        if attr_def_id is None:
            # Error logged in helper
            return

        # Get interaction details using the helper method
        interaction_data = self._get_interaction_details(method, kwargs, response_json)
        if interaction_data is None:
            # Error already logged in helper
            return

        interaction_action, interaction_details = interaction_data

        mirrordb_data = MirrorDBHelper._construct_interaction_payload(
            agent_id, attr_def_id, interaction_action, interaction_details
        )

        yield from self._send_interaction_to_mirrordb(agent_id, mirrordb_data, method)

    # --- Data Retrieval Helpers ---

    def _extract_required_ids_from_config(
        self, config: Dict[str, Any]
    ) -> Optional[Tuple[int, int, int]]:
        """Extracts and validates interaction, username, and agent type IDs from config."""
        # Check if config itself is valid first
        if not isinstance(config, dict):
            self.context.logger.error(
                f"Invalid config type provided for ID extraction: {type(config)}"
            )
            return None

        interactions_id_raw = config.get("twitter_interactions_attr_def_id")
        username_id_raw = config.get("twitter_username_attr_def_id")
        agent_type_id_raw = config.get("agent_type_id")

        # Ensure required keys exist and are not None
        if (
            interactions_id_raw is None
            or username_id_raw is None
            or agent_type_id_raw is None
        ):
            self.context.logger.error(
                f"Missing required IDs in mirrod_db_config: "
                f"interactions={interactions_id_raw}, username={username_id_raw}, type={agent_type_id_raw}. "
                f"Config: {config}"
            )
            return None

        try:
            interactions_id = int(cast(Union[str, int], interactions_id_raw))
            username_id = int(cast(Union[str, int], username_id_raw))
            agent_type_id = int(cast(Union[str, int], agent_type_id_raw))
            return interactions_id, username_id, agent_type_id
        except (ValueError, TypeError) as e:
            self.context.logger.error(
                f"Error converting required IDs to integers: {e}. Config: {config}"
            )
            return None

    def _fetch_all_interactions(
        self, agent_type_id: int, interactions_attr_def_id: int
    ) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Fetches all interaction attribute instances for a given type and definition."""
        endpoint = f"/api/agent-types/{agent_type_id}/attributes/{interactions_attr_def_id}/values"
        all_interactions = yield from self.call_mirrordb("GET", endpoint=endpoint)

        if all_interactions is None:
            self.context.logger.warning(
                f"Received None when fetching interaction attributes from {endpoint}."
            )
            return None  # Indicate fetch failure

        if not isinstance(all_interactions, list):
            self.context.logger.warning(
                f"Could not retrieve interaction attributes as a list from endpoint {endpoint}. Response type: {type(all_interactions)}"
            )
            return None  # Indicate unexpected type

        self.context.logger.info(
            f"Retrieved {len(all_interactions)} total interaction attributes from {endpoint}."
        )
        return all_interactions

    def _filter_recent_agent_ids(
        self, interactions: List[Dict[str, Any]], days: int
    ) -> Set[int]:
        """Filters interaction list to find agent IDs active within the last N days."""
        recent_agent_ids: Set[int] = set()
        if not interactions:  # Handle empty list explicitly
            return recent_agent_ids

        cutoff_time = datetime.utcnow() - timedelta(days=days)

        for interaction in interactions:
            try:
                json_value = interaction.get("json_value")
                if not isinstance(json_value, dict):
                    self.context.logger.debug(  # Less severe logging for skipping
                        f"Skipping interaction with non-dict json_value: {interaction.get('attribute_id')}"
                    )
                    continue

                timestamp_str = json_value.get("timestamp")
                if not timestamp_str or not isinstance(timestamp_str, str):
                    self.context.logger.debug(  # Less severe logging for skipping
                        f"Skipping interaction with missing or invalid timestamp: {interaction.get('attribute_id')}"
                    )
                    continue

                # Handle potential timezone info (e.g., Z for UTC) and parse
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1] + "+00:00"

                interaction_time = datetime.fromisoformat(timestamp_str)

                # Convert to offset-naive UTC for comparison
                if interaction_time.tzinfo:
                    interaction_time_utc = interaction_time.astimezone(
                        timezone.utc
                    ).replace(tzinfo=None)
                else:
                    # Assume UTC if no timezone info (adjust if assumption is wrong)
                    interaction_time_utc = interaction_time

                if interaction_time_utc >= cutoff_time:
                    agent_id = interaction.get("agent_id")
                    if agent_id is not None:
                        try:
                            recent_agent_ids.add(int(agent_id))
                        except (ValueError, TypeError):
                            self.context.logger.warning(
                                f"Invalid agent_id type found: {agent_id}. Skipping."
                            )
                    else:
                        self.context.logger.warning(
                            f"Interaction found with null agent_id: {interaction.get('attribute_id')}. Skipping."
                        )

            except (ValueError, TypeError, KeyError) as e:
                self.context.logger.warning(
                    f"Error processing interaction timestamp or structure: {interaction.get('attribute_id')}. Error: {e}. Skipping."
                )
                continue

        self.context.logger.info(
            f"Found {len(recent_agent_ids)} unique agents with interactions in the last {days} days."
        )
        return recent_agent_ids

    def _fetch_usernames_for_agents(
        self, agent_ids: Set[int], username_attr_def_id: int
    ) -> Generator[None, None, Dict[int, str]]:
        """Fetches usernames for a given set of agent IDs."""
        agent_usernames: Dict[int, str] = {}
        if not agent_ids:
            return agent_usernames

        for agent_id in agent_ids:
            try:
                endpoint = f"/api/agents/{agent_id}/attributes/{username_attr_def_id}/"
                username_attribute = yield from self.call_mirrordb(
                    "GET", endpoint=endpoint
                )

                if username_attribute and isinstance(username_attribute, dict):
                    username = username_attribute.get("string_value")
                    if username and isinstance(
                        username, str
                    ):  # Ensure it's a non-empty string
                        agent_usernames[agent_id] = username
                    elif not username:
                        self.context.logger.debug(  # Less severe logging
                            f"Username attribute for agent {agent_id} has missing or empty string_value."
                        )
                else:
                    self.context.logger.warning(
                        f"Could not retrieve valid username attribute for agent {agent_id} from {endpoint}. Response: {username_attribute}"
                    )

            except Exception as e:  # pylint: disable=broad-except
                self.context.logger.error(
                    f"Error retrieving username for agent {agent_id}: {e}"
                )
                # Continue to next agent_id

        return agent_usernames

    def _get_own_username_from_config(self, config: Dict[str, Any]) -> Optional[str]:
        """Gets the agent's own Twitter username from the validated config."""
        # Use the username stored in the config, which is kept synced with the live session
        own_username = config.get("twitter_username")
        if not own_username:
            # This should ideally not happen if config validation passed
            self.context.logger.warning(
                "Own Twitter username not found in validated MirrorDB config (`twitter_username`). Cannot exclude self."
            )
            return None
        return own_username

    # --- Main Data Retrieval Method ---

    def get_active_twitter_handles(  # pylint: disable=too-many-return-statements
        self, days: int = 7
    ) -> Generator[None, None, List[str]]:
        """Get Twitter handles of agents with interactions in the last N days using MirrorDB attributes."""
        self.context.logger.info(
            f"Fetching active Twitter handles (last {days} days)..."
        )
        handles: List[str] = []

        # 1. Perform Registration Check & Get Config
        # This ensures registration and syncs ID/username if needed
        config = yield from self.mirror_db_registration_check()
        if not config:  # Handles None or potentially invalid dict if check failed badly
            self.context.logger.error(
                "Aborting handle fetch: Failed to get valid & synced MirrorDB config via registration check."
            )
            return handles  # Early exit

        # 2. Extract and Validate Required IDs from the checked config
        ids = self._extract_required_ids_from_config(config)
        if not ids:
            # Error logged in helper
            self.context.logger.error(
                "Aborting handle fetch: Failed to extract required IDs from config."
            )
            return handles  # Early exit
        interactions_attr_def_id, username_attr_def_id, agent_type_id = ids
        self.context.logger.debug(
            f"Using IDs from config: interactions={interactions_attr_def_id}, "
            f"username={username_attr_def_id}, agent_type={agent_type_id}"
        )

        # 3. Fetch All Interactions
        all_interactions = yield from self._fetch_all_interactions(
            agent_type_id, interactions_attr_def_id
        )
        if all_interactions is None:
            self.context.logger.warning(
                # Changed message slightly as failure is now post-config check
                "Failed to fetch interaction attributes from MirrorDB. Cannot determine active handles."
            )
            return handles  # Return empty list, but config was likely ok

        # 4. Filter Agent IDs by Recent Activity
        recent_agent_ids = self._filter_recent_agent_ids(all_interactions, days)
        if not recent_agent_ids:
            self.context.logger.info("No agents found with recent interactions.")
            return handles  # Early exit

        # 5. Fetch Usernames for Recent Agents
        agent_usernames = yield from self._fetch_usernames_for_agents(
            recent_agent_ids, username_attr_def_id
        )
        if not agent_usernames:
            self.context.logger.warning(
                "Found recent agents but failed to fetch any corresponding usernames."
            )
            return handles  # Return empty list

        # 6. Get Own Username from Config to Exclude
        # Use the username from the validated config dictionary
        own_username = self._get_own_username_from_config(config)

        # 7. Filter and Collect Handles
        for username in agent_usernames.items():
            # Ensure own_username was successfully retrieved before comparing
            if own_username is not None and username[1] == own_username:
                self.context.logger.debug(f"Excluding own username: {username[1]}")
                continue  # Skip own handle
            handles.append(username[1])

        self.context.logger.info(
            f"Found {len(handles)} active handles (excluding self if username known): {handles}"
        )
        return handles


class MemeooorrBaseBehaviour(
    BaseBehaviour, ABC
):  # pylint: disable=too-many-ancestors,too-many-public-methods
    """Base behaviour for the memeooorr_abci skill.

    This class provides common functionalities and properties used by other behaviours
    in the Memeooorr ABCI skill.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the base behaviour."""
        super().__init__(**kwargs)
        self._mirrordb_helper_instance: Optional[MirrorDBHelper] = None

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

    @property
    def mirrordb_helper(self) -> MirrorDBHelper:
        """Get the MirrorDB helper instance."""
        if self._mirrordb_helper_instance is None:
            self._mirrordb_helper_instance = MirrorDBHelper(self)
        return self._mirrordb_helper_instance

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

    def do_connection_request(
        self,
        message: Message,
        dialogue: Message,
        timeout: Optional[float] = None,
    ) -> Generator[None, None, Message]:
        """
        Public wrapper for making a connection request and waiting for response.

        Args:
            message: The message to send
            dialogue: The dialogue context
            timeout: Optional timeout duration

        Returns:
            Message: The response message
        """
        return (yield from self._do_connection_request(message, dialogue, timeout))

    def _call_tweepy(  # pylint: disable=too-many-locals,too-many-statements
        self, method: str, **kwargs: Any
    ) -> Generator[None, None, Any]:
        """Send a request message to the Tweepy connection and handle MirrorDB interactions."""
        # Track this API call with our unified tracking function

        mirror_db_config_data = (
            yield from self._handle_mirror_db_interactions_pre_tweepy()
        )

        if mirror_db_config_data is None:
            self.context.logger.error(
                "MirrorDB config data is None after registration attempt. This is unexpected and indicates a potential issue with the registration process."
            )

        # Create the request message for Tweepy
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWEEPY_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"method": method, "kwargs": kwargs}),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        # Handle MirrorDB interaction if applicable
        yield from self._handle_mirrordb_interaction_post_tweepy(
            method, kwargs, response_json, mirror_db_config_data  # type: ignore
        )
        return response_json.get("response")

    def _handle_mirror_db_interactions_pre_tweepy(  # pylint: disable=too-many-return-statements,too-many-statements,too-many-locals
        self,
    ) -> Generator[None, None, Optional[Dict]]:
        """Handle MirrorDB interactions before calling Tweepy (registration check, username update)."""

        # Registration check for mirrorDB using the helper
        mirror_db_config_data = yield from self.mirrordb_helper.mirror_db_registration_check()  # type: ignore

        # The rest of this method deals with username updates based on cookies vs stored data
        # It needs access to Tweepy calls, KV store, and MirrorDB calls (via helper)
        if not isinstance(mirror_db_config_data, dict):
            self.context.logger.warning(
                "MirrorDB config data is not a dictionary after check, cannot proceed with username update logic."
            )
            return mirror_db_config_data  # Return whatever we got

        agent_id = mirror_db_config_data.get("agent_id")
        if agent_id is None:
            self.context.logger.error("agent_id is None in MirrorDB config data.")
            return mirror_db_config_data

        stored_twitter_user_id = mirror_db_config_data.get("twitter_user_id")
        if stored_twitter_user_id is None:
            self.context.logger.error(
                "Stored twitter_user_id is None in MirrorDB config data."
            )
            return mirror_db_config_data

        try:
            twitter_user_id_from_cookie = yield from self._get_twitter_user_id_from_cookie()  # type: ignore
            if twitter_user_id_from_cookie and "u=" in twitter_user_id_from_cookie:
                twitter_user_id_from_cookie = twitter_user_id_from_cookie.split("u=")[
                    -1
                ]
            else:
                self.context.logger.error(
                    f"Unexpected format for twitter_user_id_from_cookie: {twitter_user_id_from_cookie}"
                )
                return mirror_db_config_data  # Cannot compare if format is wrong

        except ValueError as e:
            self.context.logger.error(f"Error getting Twitter user ID from cookie: {e}")
            return mirror_db_config_data  # Return config, but cannot compare

        if (  # pylint: disable=too-many-nested-blocks
            twitter_user_id_from_cookie != stored_twitter_user_id
        ):
            self.context.logger.warning(
                f"Twitter user id from cookie ({twitter_user_id_from_cookie}) != Twitter ID stored ({stored_twitter_user_id})"
            )
            self.context.logger.info(
                "New Twitter account detected! Updating username attribute in MirrorDB."
            )
            # Update the config in KV store first
            # Make sure _update_mirror_db_config_with_new_twitter_user_id exists and works
            yield from self._update_mirror_db_config_with_new_twitter_user_id(
                new_twitter_user_id=twitter_user_id_from_cookie
            )
            # Update the stored twitter_user_id in the local dict for the rest of the logic
            mirror_db_config_data["twitter_user_id"] = twitter_user_id_from_cookie

            # Update the stored username attribute (Interface 2.0)
            try:
                # 1. Get the new username from Tweepy
                new_twitter_user_data = (
                    yield from self.get_twitter_user_data()
                )  # Re-fetch with current cookies
                new_twitter_username = (
                    new_twitter_user_data.get("screen_name")
                    if new_twitter_user_data
                    else None
                )

                if not new_twitter_username:
                    self.context.logger.error(
                        "Failed to get new Twitter username from Tweepy. Cannot update attribute."
                    )
                else:
                    self.context.logger.info(
                        f"New Twitter username detected: {new_twitter_username}"
                    )

                    # 2. Get the username attribute definition ID from config
                    username_attr_def_id = mirror_db_config_data.get(
                        "twitter_username_attr_def_id"
                    )

                    if not username_attr_def_id:
                        self.context.logger.error(
                            "Missing twitter_username_attr_def_id in MirrorDB config. Cannot update attribute."
                        )
                    else:
                        try:
                            # Ensure it's an integer
                            username_attr_def_id = int(username_attr_def_id)
                        except (ValueError, TypeError):
                            self.context.logger.error(
                                f"Invalid twitter_username_attr_def_id format in config: {username_attr_def_id}"
                            )
                            return mirror_db_config_data  # Abort update if ID format is wrong

                        # 3. Try to GET the existing attribute instance to find its specific attribute_id
                        get_endpoint = (
                            f"/api/agents/{agent_id}/attributes/{username_attr_def_id}/"
                        )
                        existing_attribute = (
                            yield from self.mirrordb_helper.call_mirrordb(
                                "GET", endpoint=get_endpoint
                            )
                        )

                        attribute_id_to_update = None
                        if (
                            existing_attribute
                            and isinstance(existing_attribute, dict)
                            and "attribute_id" in existing_attribute
                        ):
                            attribute_id_to_update = existing_attribute["attribute_id"]

                        if attribute_id_to_update:
                            self.context.logger.info(
                                f"Found existing username attribute instance (ID: {attribute_id_to_update}). Updating..."
                            )

                            # 4a. Prepare PUT request to update
                            update_endpoint = (
                                f"/api/agent-attributes/{attribute_id_to_update}"
                            )
                            update_payload = {"string_value": new_twitter_username}
                            auth_data_update = (
                                yield from self.mirrordb_helper.sign_mirrordb_request(
                                    update_endpoint, agent_id
                                )
                            )

                            if auth_data_update:
                                request_body_update = {
                                    "agent_attr": update_payload,
                                    "auth": auth_data_update,
                                }
                                update_response = (
                                    yield from self.mirrordb_helper.call_mirrordb(
                                        "PUT",
                                        endpoint=update_endpoint,
                                        data=request_body_update,
                                    )
                                )
                                if update_response:
                                    self.context.logger.info(
                                        f"Successfully updated username attribute for agent {agent_id} (attribute {attribute_id_to_update})."
                                    )
                                else:
                                    self.context.logger.error(
                                        f"Failed to update username attribute for agent {agent_id} (attribute {attribute_id_to_update})."
                                    )
                            else:
                                self.context.logger.error(
                                    f"Failed to sign username attribute update request for agent {agent_id}."
                                )
                        else:
                            self.context.logger.warning(
                                f"Could not find existing username attribute for agent {agent_id} via GET {get_endpoint} or it lacked an ID. Attempting to create it instead. Response: {existing_attribute}"
                            )
                            # 4b. If GET failed or attribute missing, try to POST (create) it
                            create_endpoint = f"/api/agents/{agent_id}/attributes/"
                            create_payload = {
                                "agent_id": agent_id,
                                "attr_def_id": username_attr_def_id,
                                "string_value": new_twitter_username,
                            }
                            auth_data_create = (
                                yield from self.mirrordb_helper.sign_mirrordb_request(
                                    create_endpoint, agent_id
                                )
                            )

                            if auth_data_create:
                                request_body_create = {
                                    "agent_attr": create_payload,
                                    "auth": auth_data_create,
                                }
                                create_response = (
                                    yield from self.mirrordb_helper.call_mirrordb(
                                        "POST",
                                        endpoint=create_endpoint,
                                        data=request_body_create,
                                    )
                                )
                                if create_response:
                                    self.context.logger.info(
                                        f"Successfully created username attribute for agent {agent_id} after update detection."
                                    )
                                else:
                                    self.context.logger.error(
                                        f"Failed to create username attribute for agent {agent_id} after update detection."
                                    )
                            else:
                                self.context.logger.error(
                                    f"Failed to sign username attribute creation request for agent {agent_id}."
                                )

            except (  # pylint: disable=broad-except
                ValueError,
                TypeError,
                KeyError,
                Exception,
            ) as e:
                self.context.logger.error(
                    f"Error during username attribute update process: {e}"
                )

        return mirror_db_config_data

    def _handle_mirrordb_interaction_post_tweepy(
        self,
        method: str,
        kwargs: Dict[str, Any],
        response_json: Dict[str, Any],
        mirror_db_config_data: Dict[str, Any],
    ) -> Generator[None, None, None]:
        """Handle MirrorDB interaction after Tweepy response by calling the helper."""
        # Delegate recording to the helper class
        yield from self.mirrordb_helper.record_interaction(
            method, kwargs, response_json, mirror_db_config_data
        )

    def _get_twitter_user_data(self) -> Generator[None, None, Dict[str, str]]:
        """Get the twitter user data using Tweepy."""

        TWEEPY_USERNAME = self.params.twitter_username
        if not TWEEPY_USERNAME:
            # Consider if this should try to fetch from MirrorDB attribute if param is missing
            self.context.logger.error(
                "TWEEPY_USERNAME environment variable not set in agent parameters"
            )

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWEEPY_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(
                {
                    "method": "get_user_by_screen_name",
                    "kwargs": {"screen_name": TWEEPY_USERNAME},
                }
            ),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore
        if "error" in response_json:
            raise ValueError(response_json["error"])

        twitter_user_data = response_json.get("response")
        if twitter_user_data is None:
            self.context.logger.error(
                "twitter_user_data is None, which is not expected."
            )

        self.context.logger.info(f"Got twitter_user_data: {twitter_user_data}")
        return twitter_user_data

    def get_twitter_user_data(self) -> Generator[None, None, Dict[str, str]]:
        """
        Public wrapper for getting Twitter user data.

        Returns:
            Dict[str, str]: Dictionary containing Twitter user data
        """
        return (yield from self._get_twitter_user_data())

    def _get_twitter_user_id_from_cookie(self) -> Generator[None, None, str]:
        """Get the Twitter user ID from the Tweepy connection."""
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWEEPY_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"method": "get_twitter_user_id", "kwargs": {}}),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore
        if "error" in response_json:
            raise ValueError(response_json["error"])

        twitter_user_id = response_json.get("response")
        if twitter_user_id is None:
            self.context.logger.error("twitter_user_id is None, which is not expected.")

        return twitter_user_id

    def get_twitter_user_id_from_cookie(self) -> Generator[None, None, str]:
        """
        Public wrapper for getting the Twitter user ID from the Tweepy connection.

        Returns:
            str: The Twitter user ID.
        """
        return (yield from self._get_twitter_user_id_from_cookie())

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
        response = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        return response_json["response"]  # type: ignore

    def _read_kv(
        self,
        keys: Tuple[str, ...],
    ) -> Generator[None, None, Optional[Dict]]:
        """Send a request message from the skill context."""
        self.context.logger.info(f"Reading keys from db: {keys}")
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.READ_REQUEST,
            keys=keys,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self.do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        if response.performative != KvStoreMessage.Performative.READ_RESPONSE:
            return None

        data = {key: response.data.get(key, None) for key in keys}  # type: ignore

        return data

    def _write_kv(
        self,
        data: Dict[str, str],
    ) -> Generator[None, None, bool]:
        """Send a request message from the skill context."""
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.CREATE_OR_UPDATE_REQUEST,
            data=data,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self.do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        if response is None:
            self.context.logger.error(
                "Received None response from KV Store connection during write."
            )
            return False
        self.context.logger.info(
            f"KV Store write response performative: {response.performative}"
        )
        return response.performative == KvStoreMessage.Performative.SUCCESS

    def read_kv(
        self,
        keys: Tuple[str, ...],
    ) -> Generator[None, None, Optional[Dict]]:
        """
        Public wrapper for reading from key-value store.

        Args:
            keys: Tuple of keys to read from the store.

        Returns:
            Optional[Dict]: The data read from the store, or None if unsuccessful.
        """
        return (yield from self._read_kv(keys=keys))

    def write_kv(
        self,
        data: Dict[str, str],
    ) -> Generator[None, None, bool]:
        """
        Public wrapper for writing to key-value store.

        Args:
            data: Dictionary of key-value pairs to write to the store.

        Returns:
            bool: True if write was successful, False otherwise.
        """
        return (yield from self._write_kv(data=data))

    def get_sync_timestamp(self) -> float:
        """Get the synchronized time from Tendermint's last block."""
        now = cast(
            SharedState, self.context.state
        ).round_sequence.last_round_transition_timestamp.timestamp()

        return now

    def get_sync_datetime(self) -> datetime:
        """Get the synchronized time from Tendermint's last block."""
        return datetime.fromtimestamp(self.get_sync_timestamp())

    def get_sync_time_str(self) -> str:
        """Get the synchronized time from Tendermint's last block."""
        return self.get_sync_datetime().strftime("%Y-%m-%d %H:%M:%S")

    def get_persona(self) -> Generator[None, None, str]:
        """Get the agent persona"""

        # If the persona is already in the synchronized data, return it
        if self.synchronized_data.persona:
            return self.synchronized_data.persona

        # If we reach this point, the agent has just started
        persona_config = self.params.persona

        # Try getting the persona from the db
        db_data = yield from self.read_kv(keys=("persona", "initial_persona"))

        if not db_data:
            self.context.logger.error(
                "Error while loading the database. Falling back to the config."
            )
            return persona_config

        # Load values from the config and database
        initial_persona_db = db_data.get("initial_persona", None)
        persona_db = db_data.get("persona", None)

        # If the initial persona is not in the db, we need to store it
        if initial_persona_db is None:
            yield from self.write_kv({"initial_persona": persona_config})
            initial_persona_db = persona_config

        # If the persona is not in the db, this is the first run
        if persona_db is None:
            yield from self.write_kv({"persona": persona_config})
            persona_db = persona_config

        # If the configured persona does not match the initial persona in the db,
        # the user has reconfigured it and we need to update it:
        if persona_config != initial_persona_db:
            yield from self.write_kv(
                {"persona": persona_config, "initial_persona": persona_config}
            )
            initial_persona_db = persona_config
            persona_db = persona_config

        # At this point, the db in the persona is the correct one
        return persona_db

    def get_native_balance(self) -> Generator[None, None, dict]:
        """Get the native balance"""

        # Safe
        self.context.logger.info(
            f"Getting native balance for the Safe {self.synchronized_data.safe_contract_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=self.get_chain_id(),
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            safe_balance = None
        else:
            safe_balance = cast(
                float, ledger_api_response.state.body["get_balance_result"]
            )
            safe_balance = safe_balance / 10**18  # from wei

        self.context.logger.info(f"Got Safe's native balance: {safe_balance}")

        # Agent
        self.context.logger.info(
            f"Getting native balance for the agent {self.context.agent_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.context.agent_address,
            chain_id=self.get_chain_id(),
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            agent_balance = None
        else:
            agent_balance = cast(
                float, ledger_api_response.state.body["get_balance_result"]
            )
            agent_balance = agent_balance / 10**18  # from wei

        self.context.logger.info(f"Got agent's native balance: {agent_balance}")

        return {"safe": safe_balance, "agent": agent_balance}

    def get_meme_available_actions(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        meme_data: Dict,
        burnable_amount: int,
        maga_launched: bool,
    ) -> Generator[None, None, List[str]]:
        """Get the available actions"""

        # Get the times
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        summon_time = datetime.fromtimestamp(meme_data["summon_time"])
        unleash_time = datetime.fromtimestamp(meme_data["unleash_time"])
        seconds_since_summon = (now - summon_time).total_seconds()
        seconds_since_unleash = (now - unleash_time).total_seconds()
        is_unleashed = meme_data.get("unleash_time", 0) != 0
        is_purged = meme_data.get("is_purged")
        is_hearted = (
            self.synchronized_data.safe_contract_address
            in meme_data.get("hearters", {}).keys()
        )
        token_nonce = meme_data.get("token_nonce")
        collectable_amount = yield from self.get_collectable_amount(
            cast(int, token_nonce)
        )
        is_collectable = collectable_amount > 0

        available_actions: List[str] = []

        # Heart
        if not is_unleashed and meme_data.get("token_nonce", None) != 1:
            available_actions.append("heart")

        # Unleash
        if (
            not is_unleashed
            and seconds_since_summon > 24 * 3600
            and meme_data.get("token_nonce", None) != 1
        ):
            available_actions.append("unleash")

        # Collect
        if (
            is_unleashed
            and seconds_since_unleash < 24 * 3600
            and is_hearted
            and is_collectable
        ):
            available_actions.append("collect")

        # Purge
        if is_unleashed and seconds_since_unleash > 24 * 3600 and not is_purged:
            available_actions.append("purge")

        # Burn
        if maga_launched and burnable_amount > 0:
            available_actions.append("burn")

        return available_actions

    def get_chain_id(self) -> str:
        """Get chain id"""
        if self.params.home_chain_id.lower() == BASE_CHAIN_ID:
            return BASE_CHAIN_ID

        if self.params.home_chain_id.lower() == CELO_CHAIN_ID:
            return CELO_CHAIN_ID

        return ""

    def get_native_ticker(self) -> str:
        """Get native ticker"""
        if self.params.home_chain_id.lower() == BASE_CHAIN_ID:
            return "ETH"

        if self.params.home_chain_id.lower() == CELO_CHAIN_ID:
            return "CELO"

        return ""

    def get_packages(self, package_type: str) -> Generator[None, None, Optional[Dict]]:
        """Gets minted packages from the Olas subgraph"""

        self.context.logger.info("Getting packages from Olas subgraph...")

        SUBGRAPH_URL = (
            "https://subgraph.staging.autonolas.tech/subgraphs/name/autonolas-base"
        )

        headers = {
            "Content-Type": "application/json",
        }

        data = {
            "query": PACKAGE_QUERY,
            "variables": {
                "package_type": package_type,
            },
        }

        # Get all existing agents from the subgraph
        self.context.logger.info("Getting agents from subgraph")
        response = yield from self.get_http_response(  # type: ignore
            method="POST",
            url=SUBGRAPH_URL,
            headers=headers,
            content=json.dumps(data).encode(),
        )

        if response.status_code != HTTP_OK:  # type: ignore
            self.context.logger.error(
                f"Error getting agents from subgraph: {response}"  # type: ignore
            )
            return None

        # Parse the response body
        response_body = json.loads(response.body)  # type: ignore

        # Check if 'data' key exists in the response
        if "data" not in response_body:
            self.context.logger.error(
                f"Expected 'data' key in response, but got: {response_body}"
            )
            return None

        return response_body["data"]

    def get_memeooorr_handles_from_subgraph(self) -> Generator[None, None, List[str]]:
        """Get Memeooorr service handles"""
        handles: List[str] = []
        services = yield from self.get_packages("service")
        if not services:
            return handles

        for service in services["units"]:
            match = re.match(MEMEOOORR_DESCRIPTION_PATTERN, service["description"])

            if not match:
                continue

            handle = match.group(1)

            # Exclude my own username
            if handle == self.params.twitter_username:
                continue

            handles.append(handle)

        self.context.logger.info(f"Got Twitter handles: {handles}")
        return handles

    def get_service_registry_address(self) -> str:
        """Get the service registry address"""
        return (
            self.params.service_registry_address_base
            if self.get_chain_id() == "base"
            else self.params.service_registry_address_celo
        )

    def get_olas_address(self) -> str:
        """Get the olas address"""
        return (
            self.params.olas_token_address_base
            if self.get_chain_id() == "base"
            else self.params.olas_token_address_celo
        )

    def get_meme_factory_address(self) -> str:
        """Get the meme factory address"""
        return (
            self.params.meme_factory_address_base
            if self.get_chain_id() == "base"
            else self.params.meme_factory_address_celo
        )

    def get_meme_factory_deployment_block(self) -> str:
        """Get the meme factory deployment block"""
        return (
            self.params.meme_factory_deployment_block_base
            if self.get_chain_id() == "base"
            else self.params.meme_factory_deployment_block_celo
        )

    def get_memeooorr_handles_from_chain(self) -> Generator[None, None, List[str]]:
        """Get Memeooorr service handles"""

        handles = []

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_service_registry_address(),
            contract_id=str(ServiceRegistryContract.contract_id),
            contract_callable="get_services_data",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the service data: {response_msg}")
            return []

        services_data = cast(dict, response_msg.state.body.get("services_data", None))

        for service_data in services_data:
            response = yield from self.get_http_response(  # type: ignore
                method="GET",
                url=IPFS_ENDPOINT.format(ipfs_hash=service_data["ipfs_hash"]),
            )

            if response.status_code != HTTP_OK:  # type: ignore
                self.context.logger.error(
                    f"Error getting data from IPFS endpoint: {response}"  # type: ignore
                )
                continue

            metadata = json.loads(response.body)
            match = re.match(MEMEOOORR_DESCRIPTION_PATTERN, metadata["description"])

            if not match:
                continue

            handle = match.group(1)

            # Exclude my own username
            if handle == self.params.twitter_username:
                continue

            handles.append(handle)

        self.context.logger.info(f"Got Twitter handles: {handles}")

        return handles

    def get_meme_coins(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""

        meme_coins: Optional[List] = self.synchronized_data.meme_coins

        if meme_coins:
            return meme_coins

        meme_coins = yield from self.get_meme_coins_from_subgraph()

        return meme_coins

    def get_meme_coins_from_subgraph(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""
        self.context.logger.info("Getting meme tokens from the subgraph")

        headers = {
            "Content-Type": "application/json",
        }

        query = {"query": TOKENS_QUERY, "variables": {"limit": 1000, "after": None}}

        response = yield from self.get_http_response(  # type: ignore
            method="POST",
            url=self.params.meme_subgraph_url,
            headers=headers,
            content=json.dumps(query).encode(),
        )

        if response.status_code != HTTP_OK:  # type: ignore
            self.context.logger.error(
                f"Error getting agents from subgraph: {response}"  # type: ignore
            )
            return []

        response_json = json.loads(response.body)
        tokens = [
            {
                "token_name": t["name"],
                "token_ticker": t["symbol"],
                "block_number": int(t["blockNumber"]),
                "chain": t["chain"],
                "token_address": t["memeToken"],
                "liquidity": int(t["liquidity"]),
                "heart_count": int(t["heartCount"]),
                "is_unleashed": t["isUnleashed"],
                "is_purged": t["isPurged"],
                "lp_pair_address": t["lpPairAddress"],
                "owner": t["owner"],
                "timestamp": t["timestamp"],
                "meme_nonce": int(t["memeNonce"]),
                "summon_time": int(t["summonTime"]),
                "unleash_time": int(t["unleashTime"]),
                "token_nonce": int(t["memeNonce"]),
                "hearters": t["hearters"],
            }
            for t in response_json["data"]["memeTokens"]["items"]
            if t["chain"] == self.get_chain_id()
            # to only include the updated factory contract address's token data
            and int(t["memeNonce"]) > 0
        ]

        burnable_amount = yield from self.get_burnable_amount()

        # We can only burn when the AG3NT token (nonce=1) has been unleashed
        maga_launched = False
        for token in tokens:
            if token["token_nonce"] == 1 and token.get("unleash_time", 0) != 0:
                maga_launched = True

        for token in tokens:
            available_actions = yield from self.get_meme_available_actions(
                token, burnable_amount, maga_launched
            )
            token["available_actions"] = available_actions

        return tokens

    def get_min_deploy_value(self) -> int:
        """Get min deploy value"""
        if self.get_chain_id() == "base":
            return int(0.01 * 1e18)

        if self.get_chain_id() == "celo":
            return 10

        # Should not happen
        return 0

    def get_tweets_from_db(self) -> Generator[None, None, List[Dict]]:
        """Get tweets"""
        db_data = yield from self.read_kv(keys=("tweets",))

        if db_data is None:
            tweets = []
        else:
            tweets = json.loads(db_data["tweets"] or "[]")

        return tweets

    def get_burnable_amount(self) -> Generator[None, None, int]:
        """Get burnable amount"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_burnable_amount",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the burnable amount: {response_msg}"
            )
            return 0

        burnable_amount = cast(int, response_msg.state.body.get("burnable_amount", 0))
        return burnable_amount

    def get_collectable_amount(self, token_nonce: int) -> Generator[None, None, int]:
        """Get collectable amount"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_collectable_amount",
            token_nonce=token_nonce,
            wallet_address=self.synchronized_data.safe_contract_address,
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the collectable amount: {response_msg}"
            )
            return 0

        collectable_amount = cast(
            int, response_msg.state.body.get("collectable_amount", 0)
        )
        self.context.logger.info(
            f"Collectable amount for token {token_nonce}: {collectable_amount}"
        )
        return collectable_amount

    def get_purged_memes_from_chain(self) -> Generator[None, None, List]:
        """Get purged memes"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_purge_data",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the purged tokens: {response_msg}"
            )
            return []

        purged_addresses = cast(
            list, response_msg.state.body.get("purged_addresses", [])
        )
        return purged_addresses

    def _update_mirror_db_config_with_new_twitter_user_id(
        self, new_twitter_user_id: str
    ) -> Generator[None, None, bool]:
        """Update the mirrod_db_config with the new twitter_user_id."""
        # Read the current configuration
        mirror_db_config_data = yield from self.read_kv(keys=("mirrod_db_config",))
        mirror_db_config_data = mirror_db_config_data.get("mirrod_db_config")  # type: ignore

        # Ensure mirror_db_config_data is parsed as JSON if it is a string
        if isinstance(mirror_db_config_data, str):
            mirror_db_config_data = json.loads(mirror_db_config_data)

        # Check if mirror_db_config_data is a dictionary
        if isinstance(mirror_db_config_data, dict):
            # Update the twitter_user_id
            mirror_db_config_data["twitter_user_id"] = new_twitter_user_id

            # Write the updated configuration back to the KV store
            success = yield from self.write_kv(
                {"mirrod_db_config": json.dumps(mirror_db_config_data)}
            )
            return success

        self.context.logger.error(
            "mirror_db_config_data is not a dictionary. failed to update new twitter_user_id."
        )
        return False

    def replace_tweet_with_alternative_model(
        self, prompt: str
    ) -> Generator[None, None, Optional[str]]:
        """Replaces a tweet with one generated by the alternative LLM model"""

        model_config = self.params.alternative_model_for_tweets
        self.context.logger.info(f"Alternative LLM model config: {model_config}")

        if not model_config.use:
            self.context.logger.info("Alternative LLM model is disabled")
            return None

        self.context.logger.info("Calling the alternative LLM model")

        payload = {
            "model": model_config.model,
            "max_tokens": model_config.max_tokens,
            "top_p": model_config.top_p,
            "top_k": model_config.top_k,
            "presence_penalty": model_config.presence_penalty,
            "frequency_penalty": model_config.frequency_penalty,
            "temperature": model_config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {model_config.api_key}",
        }

        # Make the HTTP request
        response = yield from self.get_http_response(
            method="POST",
            url=model_config.url,
            headers=headers,
            content=json.dumps(payload).encode(),
        )

        # Handle HTTP errors
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Error while pulling the price from Fireworks: {response}"
            )

        # Load the response
        api_data = json.loads(response.body)

        if "error" in api_data:
            self.context.logger.error(
                f"The alternative model returned an error: {api_data}"
            )
            return None

        try:
            tweet = api_data["choices"][0]["message"]["content"]
        except Exception:  # pylint: disable=broad-except
            self.context.logger.error(
                f"The alternative model response is not valid: {api_data}"
            )
            return None

        if not is_tweet_valid(tweet):
            self.context.logger.error("The alternative tweet is too long.")
            return None

        self.context.logger.info(f"Got new tweet from Fireworks API: {tweet}")

        return tweet
