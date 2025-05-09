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
        self.agent_id = self.get_agent_by_address(self.eth_address)["agent_id"]

    def _sign_request(self, endpoint):
        """Generate authentication"""
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

    def _request(self, method, endpoint, payload=None, params=None, auth=False):
        """Make the request"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if auth:
            payload = payload or {}
            payload["auth"] = self._sign_request(endpoint)
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
    def get_agent_by_address(self, eth_address):
        """Get agent by Ethereum address"""
        endpoint = f"/api/agent-registry/address/{eth_address}"
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
    def get_attribute_definition(self, attr_name):
        """Get attribute definition by name"""
        endpoint = f"/api/attributes/name/{attr_name}"
        return self._request("GET", endpoint)

    def create_attribute_definition(
        self, type_id, attr_name, data_type, is_required=False
    ):
        """Create attribute definition"""
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        payload = {
            "type_id": type_id,
            "attr_name": attr_name,
            "data_type": data_type,
            "is_required": is_required,
        }
        return self._request("POST", endpoint, {"attr_def": payload}, auth=True)

    def get_attributes_by_agent_type(self, type_id):
        """Get attributes by agent type"""
        endpoint = f"/api/agent-types/{type_id}/attributes/"
        return self._request("GET", endpoint)

    # Attribute Instance Methods
    def get_attribute_instance(self, agent_id, attr_def_id):
        """Get attribute instance by agent ID and attribute definition ID"""
        endpoint = f"/api/agents/{agent_id}/attributes/{attr_def_id}/"
        return self._request("GET", endpoint)

    def create_attribute_instance(
        self, agent_id, attr_def_id, value, value_type="string"
    ):
        """Create attribute instance"""
        endpoint = f"/api/agents/{agent_id}/attributes/"
        payload = {
            "agent_id": agent_id,
            "attr_def_id": attr_def_id,
            f"{value_type}_value": value,
        }
        return self._request("POST", endpoint, {"agent_attr": payload}, auth=True)

    def update_attribute_instance(
        self, agent_id, attr_def_id, attribute_id, value, value_type="string"
    ):
        """Update attribute instance"""
        endpoint = f"/api/agent-attributes/{attribute_id}"
        payload = {f"{value_type}_value": value}
        payload = {
            "agent_id": agent_id,
            "attr_def_id": attr_def_id,
            f"{value_type}_value": value,
        }
        return self._request("PUT", endpoint, {"agent_attr": payload}, auth=True)

    def get_all_attributes(self, agent_id):
        """Get all attributes of an agent by agent ID"""
        endpoint = f"/api/agents/{agent_id}/attributes/"
        payload = {
            "agent_id": agent_id,
        }
        return self._request("GET", endpoint, {"agent_attr": payload}, auth=True)


if __name__ == "__main__":
    # Initialize the client
    client = AgentDBClient(
        base_url="https://afmdb.autonolas.tech",
        eth_address=os.getenv("AGENT_ADDRESS"),
        private_key=os.getenv("AGENT_PRIVATE_KEY"),
    )

    # Ensure Agent Type exists
    agent_type = client.get_agent_type("memeooorr")
    print(f"agent_type = {agent_type}")
    if not agent_type:
        agent_type = client.create_agent_type("memeooorr", "Description of memeooorr")

    # Get agent type attributes
    attributes = client.get_attributes_by_agent_type(agent_type["type_id"])
    print(f"attributes = {attributes}")

    # Ensure Agent exists
    agent = client.get_agent_by_address(client.eth_address)
    print(f"agent = {agent}")
    if not agent:
        agent = client.create_agent(
            "AgentName", agent_type["type_id"], client.eth_address
        )

    # Ensure Attribute Definition exists
    attr_def = client.get_attribute_definition("twitter_username")
    print(f"attr_def = {attr_def}")
    if not attr_def:
        attr_def = client.create_attribute_definition(
            agent_type["type_id"], "twitter_username", "string", required=True
        )

    # Ensure Attribute Instance exists
    attr_instance = client.get_attribute_instance(
        agent["agent_id"], attr_def["attr_def_id"]
    )
    print(f"attr_instance = {attr_instance}")
    if not attr_instance:
        result = client.create_attribute_instance(
            agent_id=agent["agent_id"],
            attr_def_id=attr_def["attr_def_id"],
            value="user123",
        )
    else:
        client.update_attribute_instance(
            agent["agent_id"],
            attr_def["attr_def_id"],
            attr_instance["attribute_id"],
            "new_user123",
        )
