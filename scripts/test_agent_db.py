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
# https://afmdb.autonolas.tech/docs#/default/read_attribute_definitions_by_type_api_agent_types__type_id__attributes__get


class AgentDBClient:
    """AgentDBClient"""

    def __init__(self, base_url, eth_address, private_key):
        """Constructor"""
        self.base_url = base_url.rstrip("/")
        self.eth_address = eth_address
        self.private_key = private_key
        self.agent_id = None  # Initialize to None
        initial_agent_data = self.get_agent_by_address(self.eth_address)
        if initial_agent_data:
            self.agent_id = initial_agent_data["agent_id"]

    def _sign_request(self, endpoint):
        """Generate authentication"""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        message_to_sign = f"timestamp:{timestamp},endpoint:{endpoint}"
        signed_message = Account.sign_message(  # pylint: disable=no-value-for-parameter
            signable_message=encode_defunct(text=message_to_sign),
            private_key=self.private_key,
        )

        auth_data = {
            "agent_id": self.agent_id,
            "signature": signed_message.signature.hex(),
            "message": message_to_sign,
        }
        return auth_data

    def _request(self, method, endpoint, payload=None, params=None):
        """Make the request"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        # Auth is now handled by the caller by embedding it in the payload
        response = requests.request(
            method, url, headers=headers, json=payload, params=params
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
        endpoint = "/api/agent-types/"
        payload = {"type_name": type_name, "description": description}
        return self._request("POST", endpoint, payload)

    # Agent Registry Methods
    def get_agent_by_address(self, eth_addr):
        """Get agent by Ethereum address"""
        endpoint = f"/api/agent-registry/address/{eth_addr}"
        return self._request("GET", endpoint)

    def get_agent_by_type(self, type_id):
        """Get agent by type"""
        endpoint = f"/api/agent-types/{type_id}/agents/"
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
    def get_attribute_definition(self, attribute_name):
        """Get attribute definition by name"""
        endpoint = f"/api/attributes/name/{attribute_name}"
        return self._request("GET", endpoint)

    def create_attribute_definition(
        self, type_id, attribute_name, data_type, is_required=False
    ):
        """Create attribute definition"""
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        payload = {
            "type_id": type_id,
            "attr_name": attribute_name,
            "data_type": data_type,
            "is_required": is_required,
        }
        attr_payload = {"attr_def": payload}
        attr_payload["auth"] = self._sign_request(endpoint)
        return self._request("POST", endpoint, attr_payload)

    def get_attributes_by_agent_type(self, type_id):
        """Get attributes by agent type"""
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        return self._request("GET", endpoint)

    # Attribute Instance Methods
    def get_attribute_instance(self, agent_id, attribute_def_id):
        """Get attribute instance by agent ID and attribute definition ID"""
        endpoint = f"/api/agents/{agent_id}/attributes/{attribute_def_id}/"
        return self._request("GET", endpoint)

    def create_attribute_instance(self, agent_id, attribute_def_id, value_details):
        """Create attribute instance"""
        endpoint = f"/api/agents/{agent_id}/attributes/"
        payload = {
            "agent_id": agent_id,
            "attr_def_id": attribute_def_id,
            f"{value_details['type']}_value": value_details["value"],
        }
        agent_attr_payload = {"agent_attr": payload}
        agent_attr_payload["auth"] = self._sign_request(endpoint)
        return self._request("POST", endpoint, agent_attr_payload)

    def update_attribute_instance(
        self, agent_id, attribute_def_id, attribute_id, value_details
    ):
        """Update attribute instance"""
        endpoint = f"/api/agent-attributes/{attribute_id}"
        payload = {
            "agent_id": agent_id,
            "attr_def_id": attribute_def_id,
            f"{value_details['type']}_value": value_details["value"],
        }
        agent_attr_payload = {"agent_attr": payload}
        agent_attr_payload["auth"] = self._sign_request(endpoint)
        return self._request("PUT", endpoint, agent_attr_payload)

    def get_all_attributes(self, agent_id):
        """Get all attributes of an agent by agent ID"""
        endpoint = f"/api/agents/{agent_id}/attributes/"
        # This method seems to require auth based on its call pattern below,
        # although the original code passed params. Let's assume it needs auth.
        payload = {
            "agent_id": agent_id,
            "auth": self._sign_request(endpoint),  # Add auth here
        }
        # Pass None for payload in _request as it's now part of params conceptually or endpoint path
        # Actually, the API might expect agent_id in the body even for GET with auth?
        # Let's stick to sending it in the body along with auth, mimicking other auth'd calls.
        # The original code had a bug here, passing params={...} instead of json={...} for a GET potentially.
        # Let's assume GET with body is needed for auth. If not, this needs adjustment.
        return self._request("GET", endpoint, payload=payload)  # Pass payload


if __name__ == "__main__":
    # Initialize the client

    client = AgentDBClient(
        base_url=os.getenv("MIRROR_DB_BASE_URL") or "https://afmdb.autonolas.tech/",
        eth_address=os.getenv("AGENT_ADDRESS"),
        private_key=os.getenv("AGENT_PRIVATE_KEY"),
    )

    print(f"Eth address from script: {client.eth_address}")
    print(f"Initial client.agent_id (after __init__): {client.agent_id}")

    # Ensure Agent Type exists
    agent_type_name = "memeooorr"
    agent_type_description = "Agent type for memeooorr service"
    agent_type = client.get_agent_type(agent_type_name)
    print(f"Fetched agent_type '{agent_type_name}': {agent_type}")
    if not agent_type:
        print(f"Agent type '{agent_type_name}' not found. Creating...")
        agent_type = client.create_agent_type(agent_type_name, agent_type_description)
        print(f"Created agent_type: {agent_type}")

    if not agent_type or "type_id" not in agent_type:
        raise Exception(
            f"Failed to get or create agent type '{agent_type_name}'. Response: {agent_type}"
        )
    agent_type_id = agent_type["type_id"]
    print(f"Using agent_type_id: {agent_type_id}")

    # Get agent type attributes (optional, for info)
    # attributes = client.get_attributes_by_agent_type(agent_type_id)
    # print(f"Attributes for type_id {agent_type_id}: {attributes}")

    # Ensure Agent exists and client.agent_id is correctly set
    agent_data = client.get_agent_by_address(client.eth_address)
    print(f"Fetched agent_data for address {client.eth_address}: {agent_data}")

    if not agent_data:
        print(f"Agent not found for address {client.eth_address}. Creating agent...")
        agent_name_to_create = f"memeooorr_agent_{client.eth_address[:6]}"
        agent_data = client.create_agent(
            agent_name_to_create, agent_type_id, client.eth_address
        )
        print(f"Created agent_data: {agent_data}")

    if not agent_data or "agent_id" not in agent_data:
        raise Exception(
            f"Failed to get or create agent for address {client.eth_address}. Response: {agent_data}"
        )

    # IMPORTANT: Update client.agent_id with the definitive agent_id
    client.agent_id = agent_data["agent_id"]
    print(f"Client agent_id successfully set to: {client.agent_id}")

    # Ensure Attribute Definition exists
    # Note: This operation requires authentication, so client.agent_id must be set.
    if client.agent_id is None:
        raise Exception(
            "Cannot proceed: client.agent_id is not set. Agent might not have been found or created correctly."
        )

    attr_name = "twitter_username"
    attr_def = client.get_attribute_definition(attr_name)  # This does not require auth
    print(f"Fetched attribute_definition '{attr_name}': {attr_def}")

    if not attr_def:
        print(f"Attribute definition '{attr_name}' not found. Creating...")
        # The create_attribute_definition method itself needs auth
        attr_def = client.create_attribute_definition(
            type_id=agent_type_id,
            attribute_name=attr_name,
            data_type="string",
            is_required=True,  # Corrected parameter name
        )
        print(f"Created attribute_definition: {attr_def}")

    if not attr_def or "attr_def_id" not in attr_def:
        raise Exception(
            f"Failed to get or create attribute definition '{attr_name}'. Response: {attr_def}"
        )
    attr_def_id = attr_def["attr_def_id"]
    print(f"Using attr_def_id: {attr_def_id}")

    # Ensure Attribute Instance exists
    # This operation also requires authentication.
    attr_instance_value = "test_twitter_user_123"  # Example value

    # get_attribute_instance does not require auth by default per its definition in the class
    attr_instance = client.get_attribute_instance(client.agent_id, attr_def_id)
    print(
        f"Fetched attribute_instance for agent_id {client.agent_id}, attr_def_id {attr_def_id}: {attr_instance}"
    )

    if (
        not attr_instance
    ):  # Assuming get_attribute_instance returns None if not found, or an empty list.
        # If it returns an object with no 'attribute_id', that's a different case.
        # The API seems to return a single object or 404 -> None.
        print(
            f"Attribute instance not found. Creating for agent_id {client.agent_id}..."
        )
        # create_attribute_instance requires auth
        created_instance = client.create_attribute_instance(
            agent_id=client.agent_id,
            attribute_def_id=attr_def_id,
            value_details={"value": attr_instance_value, "type": "string"},
        )
        print(f"Created attribute_instance: {created_instance}")
    else:
        # Ensure attr_instance is a dictionary and has 'attribute_id'
        if not isinstance(attr_instance, dict) or "attribute_id" not in attr_instance:
            # This might happen if the API returns an empty list or unexpected format.
            print(
                "Warning: attr_instance is not in the expected format or lacks 'attribute_id'. Got:",
                attr_instance,
            )
            print("Attempting to create a new instance instead of updating.")
            created_instance = client.create_attribute_instance(
                agent_id=client.agent_id,
                attribute_def_id=attr_def_id,
                value_details={"value": attr_instance_value, "type": "string"},
            )
            print(f"Created attribute_instance (fallback): {created_instance}")

        else:
            print(
                f"Attribute instance found (ID: {attr_instance['attribute_id']}). Updating..."
            )
            # update_attribute_instance requires auth
            updated_instance = client.update_attribute_instance(
                agent_id=client.agent_id,
                attribute_def_id=attr_def_id,
                attribute_id=attr_instance["attribute_id"],
                value_details={"value": attr_instance_value, "type": "string"},
            )
            print(f"Updated attribute_instance: {updated_instance}")

    print("\nAll operations completed.")
