#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
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

"""Test the AgentDBClient class."""


import os
from datetime import datetime, timezone

import dotenv
import requests
from eth_account import Account
from eth_account.messages import encode_defunct


dotenv.load_dotenv(override=True)


# https://axatbhardwaj.notion.site/MirrorDB-Agent-and-Attribute-Data-Flow-1eac8d38bc0b80edae04ff1017d80f58


class AgentDBClient:
    """AgentDBClient"""

    def __init__(self, base_url, eth_address, private_key):
        """Constructor"""
        self.base_url = base_url.rstrip("/")
        self.eth_address = eth_address
        self.private_key = private_key
        agent_data = self.get_agent_by_address(self.eth_address)
        if agent_data and "agent_id" in agent_data:
            self.agent_id = agent_data["agent_id"]
        else:
            self.agent_id = None

    def _sign_request(self, endpoint):
        """Generate authentication"""
        if self.agent_id is None:
            raise Exception(
                "AgentDBClient: agent_id is not set. "
                "Cannot sign request. Ensure agent exists and client.agent_id is populated."
            )
        timestamp = int(datetime.now(timezone.utc).timestamp())
        message_to_sign = f"timestamp:{timestamp},endpoint:{endpoint}"
        signed_message = Account.sign_message(
            encode_defunct(text=message_to_sign), private_key=self.private_key
        )

        auth_data = {
            "agent_id": self.agent_id,
            "signature": signed_message.signature.hex(),
            "message": message_to_sign,
        }
        return auth_data

    def _request(self, method, endpoint, json_payload=None, params=None):
        """Make the request"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        response = requests.request(
            method, url, headers=headers, json=json_payload, params=params
        )
        if response.status_code in [200, 201]:
            return response.json()
        if response.status_code == 404:
            return None
        raise Exception(f"Request failed: {response.status_code} - {response.text}")

    # Agent Type Methods
    def get_agent_type(self, type_name):
        """Get agent type by name"""
        endpoint = f"/api/agent-types/name/{type_name}"
        return self._request("GET", endpoint)

    def create_agent_type(self, type_name, description):
        """Create agent type"""
        # OpenAPI for POST /api/agent-types/ does not specify 'auth' in body.
        # test_endpoints.py sends auth in params for this. If auth is required
        # and expected in params, this method would need to build auth_object
        # and pass it to self._request(..., params=auth_object).
        # For now, keeping it as is (no auth explicitly sent by this client method).
        endpoint = "/api/agent-types/"
        payload = {"type_name": type_name, "description": description}
        return self._request("POST", endpoint, json_payload=payload)

    # Agent Registry Methods
    def get_agent_by_address(self, eth_address):
        """Get agent by Ethereum address"""
        endpoint = f"/api/agent-registry/address/{eth_address}"
        return self._request("GET", endpoint)

    def create_agent(self, agent_name, type_id, eth_address):
        """Create agent"""
        endpoint = "/api/agent-registry/"
        payload = {
            "agent_name": agent_name,
            "type_id": type_id,
            "eth_address": eth_address,
        }
        return self._request("POST", endpoint, payload)

    # Attribute Definition Methods
    def get_attribute_definition(self, attr_name):
        """Get attribute definition by name"""
        endpoint = f"/api/attributes/name/{attr_name}"
        return self._request("GET", endpoint)

    def create_attribute_definition(
        self, type_id, attr_name, data_type, is_required=False, default_value=None
    ):
        """Create attribute definition"""
        # OpenAPI schema Body_create_attribute_definition_api_agent_types__type_id__attributes__post
        # requires 'attr_def' and 'auth' in the body.
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        auth_object = self._sign_request(endpoint)

        attr_def_payload = {
            "type_id": type_id,  # Required by AttributeDefinitionCreate schema
            "attr_name": attr_name,
            "data_type": data_type,
            "is_required": is_required,  # Schema uses 'is_required'
        }
        if default_value is not None:
            attr_def_payload["default_value"] = default_value

        full_payload = {"attr_def": attr_def_payload, "auth": auth_object}
        return self._request("POST", endpoint, json_payload=full_payload)

    # Attribute Instance Methods
    def get_attribute_instance(self, agent_id, attr_def_id):
        """Get attribute instance by agent ID and attribute definition ID"""
        endpoint = f"/api/agents/{agent_id}/attributes/{attr_def_id}/"
        return self._request("GET", endpoint)

    def create_attribute_instance(
        self, agent_id, attr_def_id, value, value_type="string"
    ):
        """Create attribute instance"""
        # OpenAPI schema Body_create_agent_attribute_api_agents__agent_id__attributes__post
        # requires 'agent_attr' and 'auth' in the body.
        endpoint = f"/api/agents/{agent_id}/attributes/"
        auth_object = self._sign_request(endpoint)

        agent_attr_payload = {
            "agent_id": agent_id,  # Required by AgentAttributeCreate
            "attr_def_id": attr_def_id,  # Required by AgentAttributeCreate
        }
        agent_attr_payload[f"{value_type}_value"] = value
        # Other value types (integer_value, etc.) are optional in AgentAttributeCreate

        full_payload = {"agent_attr": agent_attr_payload, "auth": auth_object}
        return self._request("POST", endpoint, json_payload=full_payload)

    def update_attribute_instance(
        self,
        attribute_id,
        agent_id_for_body,
        attr_def_id_for_body,
        value,
        value_type="string",
    ):
        """Update attribute instance"""
        # requires 'agent_attr' (AgentAttributeUpdate) and 'auth' in the body.
        # AgentAttributeUpdate requires 'agent_id' and 'attr_def_id' in its payload.
        endpoint = f"/api/agent-attributes/{attribute_id}"
        auth_object = self._sign_request(endpoint)

        agent_attr_payload = {
            "agent_id": agent_id_for_body,  # Required by AgentAttributeUpdate
            "attr_def_id": attr_def_id_for_body,  # Required by AgentAttributeUpdate
        }
        agent_attr_payload[f"{value_type}_value"] = value

        full_payload = {"agent_attr": agent_attr_payload, "auth": auth_object}
        return self._request("PUT", endpoint, json_payload=full_payload)

    def get_attribute_definitions_for_type(self, type_id, skip=0, limit=100):
        """Get all attribute definitions for a specific agent type ID."""
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        query_params = {"skip": skip, "limit": limit}
        # Per OpenAPI, GET /api/agent-types/{type_id}/attributes/ does not show auth.
        return self._request("GET", endpoint, json_payload=None, params=query_params)


def display_attribute_definitions(definitions, agent_type_name, type_id):
    """Displays the fetched attribute definitions or relevant messages."""
    if definitions is not None:
        if definitions:  # Check if the list is not empty
            print("\nFound attribute definitions:")
            for i, attr_def in enumerate(definitions):
                print(
                    f"  {i+1}. Name: {attr_def.get('attr_name')}, "
                    f"Type: {attr_def.get('data_type')}, "
                    f"Required: {attr_def.get('is_required')}, "
                    f"ID: {attr_def.get('attr_def_id')}, "
                    f"Default: {attr_def.get('default_value')}"
                )
        else:
            print(
                f"No attribute definitions found for agent type '{agent_type_name}' (ID: {type_id})."
            )
    else:
        print(
            f"Failed to fetch attribute definitions for agent type '{agent_type_name}' (ID: {type_id}). Response was None."
        )


def check_agent_type_and_list_attributes(client, agent_type_name_to_check):
    """Checks for an agent type and lists its attribute definitions if found."""
    print(
        f"\n=== Checking for Agent Type '{agent_type_name_to_check}' and its Attribute Definitions ==="
    )

    agent_type = client.get_agent_type(agent_type_name_to_check)

    if not agent_type:
        print(f"Agent type '{agent_type_name_to_check}' not found in the DB.")
        return

    if "type_id" not in agent_type:
        print(
            f"Agent type '{agent_type_name_to_check}' was found, but it's missing a 'type_id'. "
            f"Cannot fetch attributes. Data: {agent_type}"
        )
        return

    print(f"Agent type '{agent_type_name_to_check}' found: {agent_type}")
    type_id = agent_type["type_id"]
    print(f"\nFetching attribute definitions for type ID: {type_id}...")

    attribute_definitions = client.get_attribute_definitions_for_type(type_id)
    display_attribute_definitions(
        attribute_definitions, agent_type_name_to_check, type_id
    )


if __name__ == "__main__":
    # Initialize the client
    client = AgentDBClient(
        base_url="https://afmdb.autonolas.tech",
        eth_address=os.getenv("AGENT_ADDRESS"),
        private_key=os.getenv("AGENT_PRIVATE_KEY"),
    )

    check_agent_type_and_list_attributes(client, "memeooorr")

    print(
        "\n\n=== Other operations (agent creation, specific attribute management) are skipped. ==="
    )
