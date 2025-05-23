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

# pylint: disable=unused-variable,too-many-arguments,too-many-instance-attributes


import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

import dotenv
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from pydantic import BaseModel
from rich.align import Align
from rich.console import Console
from rich.table import Table


dotenv.load_dotenv(override=True)

MEMEOOORR = "memeooorr"


# https://axatbhardwaj.notion.site/MirrorDB-Agent-and-Attribute-Data-Flow-1eac8d38bc0b80edae04ff1017d80f58
# https://afmdb.autonolas.tech/docs#/default/read_attribute_definitions_by_type_api_agent_types__type_id__attributes__get


class AgentType(BaseModel):
    """AgentType"""

    type_id: int
    type_name: str
    description: str


class AgentInstance(BaseModel):
    """AgentInstance"""

    agent_id: int
    type_id: int
    agent_name: str
    eth_address: str
    created_at: datetime


class AttributeDefinition(BaseModel):
    """AttributeDefinition"""

    attr_def_id: int
    type_id: int
    attr_name: str
    data_type: str
    is_required: bool
    default_value: Any


class AttributeInstance(BaseModel):
    """AttributeInstance"""

    attribute_id: int
    attr_def_id: int
    agent_id: int
    last_updated: datetime
    string_value: str | None
    integer_value: int | None
    float_value: float | None
    boolean_value: bool | None
    date_value: datetime | None
    json_value: Any | None


class AgentsFunAgentType(BaseModel):
    """AgentsFunAgentType"""

    agent_type: AgentType
    attribute_definitions: List[AttributeDefinition]


class AgentDBClient:
    """AgentDBClient"""

    def __init__(self, base_url, eth_address, private_key):
        """Constructor"""
        self.base_url = base_url.rstrip("/")
        self.eth_address = eth_address
        self.private_key = private_key
        self.agent = self.get_agent_instance_by_address(self.eth_address)
        self.agent_type = (
            self.get_agent_type_by_type_id(self.agent.type_id) if self.agent else None
        )

    def _sign_request(self, endpoint):
        """Generate authentication"""

        if self.agent is None:
            self.agent = self.get_agent_instance_by_address(self.eth_address)

        timestamp = int(datetime.now(timezone.utc).timestamp())
        message_to_sign = f"timestamp:{timestamp},endpoint:{endpoint}"
        signed_message = Account.sign_message(  # pylint: disable=no-value-for-parameter
            encode_defunct(text=message_to_sign), private_key=self.private_key
        )

        auth_data = {
            "agent_id": self.agent.agent_id,
            "signature": signed_message.signature.hex(),
            "message": message_to_sign,
        }
        return auth_data

    def _request(
        self, method, endpoint, payload=None, params=None, auth=False, nested_auth=True
    ):
        """Make the request"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if auth:
            payload = payload or {}
            if nested_auth:
                payload["auth"] = self._sign_request(endpoint)
            else:
                payload = payload | self._sign_request(endpoint)
        response = requests.request(
            method, url, headers=headers, json=payload, params=params
        )
        if response.status_code in [200, 201]:
            return response.json()
        if response.status_code == 404:
            return None
        raise Exception(f"Request failed: {response.status_code} - {response.text}")

    # Agent Type Methods

    def create_agent_type(self, type_name, description) -> Optional[AgentType]:
        """Create agent type"""
        endpoint = "/api/agent-types/"
        payload = {"type_name": type_name, "description": description}
        result = self._request("POST", endpoint, payload)
        return AgentType.model_validate(result) if result else None

    def get_agent_type_by_type_id(self, type_id) -> Optional[AgentType]:
        """Get agent by type"""
        endpoint = f"/api/agent-types/{type_id}/"
        result = self._request("GET", endpoint)
        return AgentType.model_validate(result) if result else None

    def get_agent_type_by_type_name(self, type_name) -> Optional[AgentType]:
        """Get agent by type"""
        endpoint = f"/api/agent-types/name/{type_name}/"
        result = self._request("GET", endpoint)
        return AgentType.model_validate(result) if result else None

    def delete_agent_type(self, agent_type: AgentType):
        """Delete agent type"""
        endpoint = f"/api/agent-types/{agent_type.type_id}/"
        result = self._request("DELETE", endpoint, auth=True, nested_auth=True)
        return AgentType.model_validate(result) if result else None

    # Agent Instance Methods

    def create_agent_instance(
        self, agent_name: str, agent_type: AgentType, eth_address: str
    ) -> Optional[AgentInstance]:
        """Create agent instance"""
        endpoint = "/api/agent-registry/"
        payload = {
            "agent_name": agent_name,
            "type_id": agent_type.type_id,
            "eth_address": eth_address,
        }
        result = self._request("POST", endpoint, payload)
        return AgentInstance.model_validate(result) if result else None

    def get_agent_instance_by_address(self, eth_address) -> Optional[AgentInstance]:
        """Get agent by Ethereum address"""
        endpoint = f"/api/agent-registry/address/{eth_address}"
        result = self._request("GET", endpoint)
        return AgentInstance.model_validate(result) if result else None

    def get_agent_instances_by_type_id(self, type_id) -> List[AgentInstance]:
        """Get agent instances by type"""
        endpoint = f"/api/agent-types/{type_id}/agents/"
        params = {
            "skip": 0,
            "limit": 100,
        }
        result = self._request(method="GET", endpoint=endpoint, params=params)
        return (
            [AgentInstance.model_validate(agent) for agent in result] if result else []
        )

    def delete_agent_instance(self, agent_instance: AgentInstance):
        """Delete agent instance"""
        endpoint = f"/api/agent-registry/{agent_instance.agent_id}/"
        result = self._request("DELETE", endpoint, auth=True, nested_auth=False)
        return AgentInstance.model_validate(result) if result else None

    # Attribute Definition Methods

    def create_attribute_definition(
        self,
        agent_type: AgentType,
        attr_name: str,
        data_type: str,
        default_value: str,
        is_required: bool = False,
    ):
        """Create attribute definition"""
        endpoint = f"/api/agent-types/{agent_type.type_id}/attributes/"
        payload = {
            "type_id": agent_type.type_id,
            "attr_name": attr_name,
            "data_type": data_type,
            "default_value": default_value,
            "is_required": is_required,
        }
        result = self._request("POST", endpoint, {"attr_def": payload}, auth=True)
        return AttributeDefinition.model_validate(result) if result else None

    def get_attribute_definition_by_name(
        self, attr_name: str
    ) -> Optional[AttributeDefinition]:
        """Get attribute definition by name"""
        endpoint = f"/api/attributes/name/{attr_name}"
        result = self._request("GET", endpoint)
        return AttributeDefinition.model_validate(result) if result else None

    def get_attribute_definition_by_id(
        self, attr_id: int
    ) -> Optional[AttributeDefinition]:
        """Get attribute definition by id"""
        endpoint = f"/api/attributes/{attr_id}"
        result = self._request("GET", endpoint)
        return AttributeDefinition.model_validate(result) if result else None

    def get_attribute_definitions_by_agent_type(self, agent_type: AgentType):
        """Get attributes by agent type"""
        endpoint = f"/api/agent-types/{agent_type.type_id}/attributes/"
        result = self._request("GET", endpoint)
        return (
            [AttributeDefinition.model_validate(attr) for attr in result]
            if result
            else []
        )

    def delete_attribute_definition(self, attr_def: AttributeDefinition):
        """Delete attribute definition"""
        endpoint = f"/api/attributes/{attr_def.attr_def_id}/"
        result = self._request("DELETE", endpoint, auth=True, nested_auth=True)
        return AttributeDefinition.model_validate(result) if result else None

    # Attribute Instance Methods

    def create_attribute_instance(
        self,
        agent_instance: AgentInstance,
        attribute_def: AttributeDefinition,
        value: Any,
        value_type="string",
    ) -> Optional[AttributeInstance]:
        """Create attribute instance"""
        endpoint = f"/api/agents/{agent_instance.agent_id}/attributes/"
        payload = {
            "agent_id": agent_instance.agent_id,
            "attr_def_id": attribute_def.attr_def_id,
            f"{value_type}_value": value,
        }
        result = self._request("POST", endpoint, {"agent_attr": payload}, auth=True)
        return AttributeInstance.model_validate(result) if result else None

    def get_attribute_instance(
        self, agent_instance: AgentInstance, attr_def: AttributeDefinition
    ) -> Optional[AttributeInstance]:
        """Get attribute instance by agent ID and attribute definition ID"""
        endpoint = (
            f"/api/agents/{agent_instance.agent_id}/attributes/{attr_def.attr_def_id}/"
        )
        result = self._request("GET", endpoint)
        return AttributeInstance.model_validate(result) if result else None

    def update_attribute_instance(
        self,
        agent_instance: AgentInstance,
        attribute_def: AttributeDefinition,
        attribute_instance: AttributeInstance,
        value: Any,
        value_type="string",
    ) -> Optional[AttributeInstance]:
        """Update attribute instance"""
        endpoint = f"/api/agent-attributes/{attribute_instance.attribute_id}"
        payload = {f"{value_type}_value": value}
        payload = {
            "agent_id": agent_instance.agent_id,
            "attr_def_id": attribute_def.attr_def_id,
            f"{value_type}_value": value,
        }
        result = self._request("PUT", endpoint, {"agent_attr": payload}, auth=True)
        return AttributeInstance.model_validate(result) if result else None

    def delete_attribute_instance(
        self, attribute_instance: AttributeInstance
    ) -> Optional[AttributeInstance]:
        """Delete attribute instance"""
        endpoint = f"/api/agent-attributes/{attribute_instance.attribute_id}"
        result = self._request("DELETE", endpoint, auth=True, nested_auth=True)
        return AttributeInstance.model_validate(result) if result else None

    # Get all attributes of an agent instance

    def get_all_agent_instance_attributes_raw(self, agent_instance: AgentInstance):
        """Get all attributes of an agent by agent ID"""
        endpoint = f"/api/agents/{agent_instance.agent_id}/attributes/"
        payload = {
            "agent_id": agent_instance.agent_id,
        }
        return self._request("GET", endpoint, {"agent_attr": payload}, auth=True)

    def parse_attribute_instance(self, attribute_instance: AttributeInstance):
        """Parse attribute instance"""
        attribute_definition = self.get_attribute_definition_by_id(
            attribute_instance.attr_def_id
        )
        data_type = attribute_definition.data_type
        attr_value = getattr(attribute_instance, f"{data_type}_value", None)

        if data_type == "date":
            attr_value = datetime.fromisoformat(attr_value).astimezone(timezone.utc)
        elif data_type == "json":
            pass
        elif data_type == "string":
            attr_value = str(attr_value)
        elif data_type == "integer":
            attr_value = int(attr_value)
        elif data_type == "float":
            attr_value = float(attr_value)
        elif data_type == "boolean":
            attr_value = bool(attr_value)

        parsed_attribute_instance = {
            "attr_name": attribute_definition.attr_name,
            "attr_value": attr_value,
        }
        return parsed_attribute_instance

    def get_all_agent_instance_attributes_parsed(self, agent_instance: AgentInstance):
        """Get all attributes of an agent by agent ID"""
        attribute_instances = self.get_all_agent_instance_attributes_raw(agent_instance)
        parsed_attributes = [
            self.parse_attribute_instance(AttributeInstance(**attr))
            for attr in attribute_instances
        ]
        return parsed_attributes


class TwitterAction(BaseModel):
    """TwitterAction"""

    action: str
    timestamp: datetime

    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON"""
        return {
            "action": self.action,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "details": self.model_dump_json(exclude={"action", "timestamp"}),
        }


class TwitterPost(TwitterAction):
    """TwitterPost"""

    action: Literal["post"] = "post"
    tweet_id: str
    text: str
    reply_to_tweet_id: Optional[str] = None

    @classmethod
    def from_nested_json(cls, data: Dict[str, Any]) -> "TwitterPost":
        """Convert nested JSON to TwitterPost"""
        if isinstance(data["details"], str):
            data["details"] = json.loads(data["details"])
        return cls(
            action=data["action"],
            timestamp=datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ).astimezone(timezone.utc),
            tweet_id=data["details"]["tweet_id"],
            text=data["details"]["text"],
            reply_to_tweet_id=data["details"].get("reply_to_tweet_id", None),
        )


class TwitterRewtweet(TwitterAction):
    """TwitterRewtweet"""

    action: Literal["retweet"] = "retweet"
    tweet_id: str

    @classmethod
    def from_nested_json(cls, data: Dict[str, Any]) -> "TwitterPost":
        """Convert nested JSON to TwitterPost"""
        if isinstance(data["details"], str):
            data["details"] = json.loads(data["details"])
        return cls(
            action=data["action"],
            timestamp=datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ).astimezone(timezone.utc),
            tweet_id=data["details"]["tweet_id"],
        )


class TwitterFollow(TwitterAction):
    """TwitterFollow"""

    action: Literal["follow"] = "follow"
    username: str

    @classmethod
    def from_nested_json(cls, data: Dict[str, Any]) -> "TwitterPost":
        """Convert nested JSON to TwitterPost"""
        if isinstance(data["details"], str):
            data["details"] = json.loads(data["details"])
        return cls(
            action=data["action"],
            timestamp=datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ).astimezone(timezone.utc),
            username=data["details"]["username"],
        )


class TwitterLike(TwitterAction):
    """TwitterLike"""

    action: Literal["like"] = "like"
    tweet_id: str

    @classmethod
    def from_nested_json(cls, data: Dict[str, Any]) -> "TwitterPost":
        """Convert nested JSON to TwitterPost"""
        if isinstance(data["details"], str):
            data["details"] = json.loads(data["details"])
        return cls(
            action=data["action"],
            timestamp=datetime.fromisoformat(
                data["timestamp"].replace("Z", "+00:00")
            ).astimezone(timezone.utc),
            tweet_id=data["details"]["tweet_id"],
        )


class AgentsFunAgent:
    """AgentsFunAgent"""

    action_to_class: Dict[str, Any] = {
        "post": TwitterPost,
        "retweet": TwitterRewtweet,
        "follow": TwitterFollow,
        "like": TwitterLike,
    }

    def __init__(self, client: AgentDBClient, agent_instance: AgentInstance):
        """Constructor"""
        self.client = client
        self.agent_instance = agent_instance
        self.twitter_username: str = None
        self.twitter_user_id: str = None
        self.posts: List[TwitterPost] = []
        self.likes: List[TwitterLike] = []
        self.retweets: List[TwitterRewtweet] = []
        self.follows: List[TwitterFollow] = []
        self.loaded = False

    @classmethod
    def register(cls, agent_name: str, client: AgentDBClient):
        """Register agent"""
        agent_instance = client.create_agent_instance(
            agent_name=agent_name,
            agent_type=client.get_agent_type_by_type_name(MEMEOOORR),
            eth_address=client.eth_address,
        )

        return cls(client, agent_instance)

    def delete(self):
        """Delete agent instance"""
        self.client.delete_agent_instance(self.agent_instance)

    def load(self):
        """Load agent data"""
        attributes = self.client.get_all_agent_instance_attributes_parsed(
            self.agent_instance
        )

        interactions = []
        for attr in attributes:
            if attr["attr_name"] == "twitter_username":
                self.twitter_username = attr["attr_value"]
            elif attr["attr_name"] == "twitter_user_id":
                self.twitter_user_id = attr["attr_value"]
            elif attr["attr_name"] == "twitter_interactions":
                action_class = self.action_to_class.get(
                    attr["attr_value"]["action"], None
                )
                if not action_class:
                    raise ValueError(
                        f"Unknown Twitter action: {attr['attr_value']['action']}"
                    )
                interactions.append(
                    action_class.from_nested_json(data=attr["attr_value"])
                )

        # Separate the interactions into different lists and sort by timestamp
        interactions.sort(key=lambda x: x.timestamp)
        self.posts = [
            interaction
            for interaction in interactions
            if isinstance(interaction, TwitterPost)
        ]
        self.retweets = [
            interaction
            for interaction in interactions
            if isinstance(interaction, TwitterRewtweet)
        ]
        self.likes = [
            interaction
            for interaction in interactions
            if isinstance(interaction, TwitterLike)
        ]
        self.follows = [
            interaction
            for interaction in interactions
            if isinstance(interaction, TwitterFollow)
        ]
        self.loaded = True

    def add_interaction(self, interaction: TwitterAction):
        """Add interaction to agent"""

        # Check if the interaction is valid
        action_class = self.action_to_class.get(interaction.action, None)
        if not action_class:
            raise ValueError(f"Unknown Twitter action: {interaction.action}")

        # Create attribute instance
        attr_def = self.client.get_attribute_definition_by_name("twitter_interactions")
        if not attr_def:
            raise ValueError("Attribute definition not found")

        # Create or update attribute instance
        attr_instance = self.client.create_attribute_instance(
            agent_instance=self.agent_instance,
            attribute_def=attr_def,
            value=interaction.to_json(),
            value_type="json",
        )
        return attr_instance

    def __str__(self) -> str:
        if not self.loaded:
            self.load()

        title = f"@{self.twitter_username}"
        table = Table(title=title, show_lines=True)
        table.add_column("Type", style="cyan", no_wrap=True, justify="center")
        table.add_column("Timestamp", style="magenta", justify="center")
        table.add_column("Details", style="yellow", justify="center")

        interactions = self.likes + self.retweets + self.posts + self.follows
        interactions.sort(key=lambda x: x.timestamp)

        for interaction in interactions:
            table.add_row(
                interaction.action,
                interaction.timestamp.strftime("%Y-%m-%d %H:%M"),
                interaction.model_dump_json(exclude={"action", "timestamp"}),
            )

        console = Console()
        with console.capture() as capture:
            console.print(Align.center(table))

        return capture.get()


class AgentsFunDatabase:
    """AgentsFunDatabase"""

    def __init__(self, client: AgentDBClient):
        """Constructor"""
        self.client = client
        self.agent_type = client.get_agent_type_by_type_name(MEMEOOORR)
        self.agents = []

    def load(self):
        """Load data"""
        agent_instances = self.client.get_agent_instances_by_type_id(
            self.agent_type.type_id
        )
        for agent_instance in agent_instances:
            self.agents.append(AgentsFunAgent(self.client, agent_instance))
            self.agents[-1].load()

    def get_tweet_likes_number(self, tweet_id) -> int:
        """Get all tweet likes"""
        tweet_likes = 0
        for agent in self.agents:
            if not agent.loaded:
                agent.load()
            for like in agent.likes:
                if like.tweet_id == tweet_id:
                    tweet_likes += 1
                    break
        return tweet_likes

    def get_tweet_retweets_number(self, tweet_id) -> int:
        """Get all tweet retweets"""
        tweet_retweets = 0
        for agent in self.agents:
            if not agent.loaded:
                agent.load()
            for retweet in agent.retweets:
                if retweet.tweet_id == tweet_id:
                    tweet_retweets += 1
                    break
        return tweet_retweets

    def get_tweet_replies(self, tweet_id) -> List[TwitterPost]:
        """Get all tweet replies"""
        tweet_replies = []
        for agent in self.agents:
            if not agent.loaded:
                agent.load()
            for post in agent.posts:
                if post.reply_to_tweet_id == tweet_id:
                    tweet_replies.append(post)
                    break
        return tweet_replies

    def get_tweet_feedback(self, tweet_id) -> Dict[str, Any]:
        """Get all tweet feedback"""
        tweet_feedback = {
            "likes": self.get_tweet_likes_number(tweet_id),
            "retweets": self.get_tweet_retweets_number(tweet_id),
            "replies": self.get_tweet_replies(tweet_id),
        }
        return tweet_feedback

    def get_active_agents(self) -> List[AgentsFunAgent]:
        """Get all active agents"""
        active_agents = []
        for agent in self.agents:
            if not agent.loaded:
                agent.load()

            # An agent is active if it has posted in the last 7 days
            if not agent.posts:
                continue

            if agent.posts[-1].timestamp < datetime.now(timezone.utc) - timedelta(
                days=7
            ):
                continue

            active_agents.append(agent)
        return active_agents

    def __str__(self) -> str:
        table = Table(title="Agents.fun agent_db", show_lines=True)
        table.add_column("Agent ID", style="green", justify="center")
        table.add_column("Twitter name", style="cyan", no_wrap=True, justify="center")
        table.add_column("Twitter id", style="magenta", justify="center")
        table.add_column("Agent address", style="yellow", justify="center")

        for agent in self.agents:
            if not agent.loaded:
                agent.load()
            table.add_row(
                str(agent.agent_instance.agent_id),
                agent.twitter_username,
                agent.twitter_user_id,
                str(agent.agent_instance.eth_address),
            )

        console = Console()
        with console.capture() as capture:
            console.print(Align.center(table))

        return capture.get()


def basic_example(client: AgentDBClient):
    """Example usage of the AgentDBClient class."""

    # Read or create agent type
    memeooorr_type = client.get_agent_type_by_type_name(MEMEOOORR)
    print(f"memeooorr_type = {memeooorr_type}")

    if not memeooorr_type:
        agent_type = client.create_agent_type(
            type_name=MEMEOOORR, description="Description of memeooorr"
        )

    # Read or create agent instance
    memeooorr_instance = client.get_agent_instance_by_address(client.eth_address)
    print(f"agent_instance = {memeooorr_instance}")

    if not memeooorr_instance:
        agent_instance = client.create_agent_instance(
            agent_name="Terminator",
            agent_type=memeooorr_type,
            eth_address=client.eth_address,
        )
        print(f"memeooorr_instance = {memeooorr_instance}")

    # Read or create atttribute definition
    twitter_username_attr_def = client.get_attribute_definition_by_name(
        "twitter_username"
    )
    print(f"twitter_username_attr_def = {twitter_username_attr_def}")

    if not twitter_username_attr_def:
        twitter_username_attr_def = client.create_attribute_definition(
            agent_type=memeooorr_type,
            attr_name="twitter_username",
            data_type="string",
            default_value="",
            is_required=True,
        )
        print(f"twitter_username_attr_def = {twitter_username_attr_def}")

    # Get agent type attributes
    memeooorr_attrs = client.get_attribute_definitions_by_agent_type(memeooorr_type)
    print(f"memeooorr_attrs = {memeooorr_attrs}")

    # Ensure Attribute Instance exists
    twitter_username_attr_instance = client.get_attribute_instance(
        memeooorr_instance, twitter_username_attr_def
    )
    print(f"twitter_username_attr_instance = {twitter_username_attr_instance}")

    # Create or update attribute instance
    if not twitter_username_attr_instance:
        twitter_username_instance = client.create_attribute_instance(
            agent_instance=memeooorr_instance,
            attribute_def=twitter_username_attr_def,
            value="user123",
        )
        print(f"twitter_username_instance = {twitter_username_instance}")
    else:
        client.update_attribute_instance(
            agent_instance=memeooorr_instance,
            attribute_def=twitter_username_attr_def,
            attribute_instance=twitter_username_attr_instance,
            value="new_terminator",
        )
        print(f"Updated twitter_username_instance = {twitter_username_attr_instance}")

    # Get all attributes of an agent
    all_attributes = client.get_all_agent_instance_attributes_parsed(memeooorr_instance)
    print(f"all_attributes = {all_attributes}")


def init_memeooorr_db(client: AgentDBClient):
    """Initialize the memeooorr database"""

    # Read or create agent type
    memeooorr_type = client.get_agent_type_by_type_name(MEMEOOORR)

    if not memeooorr_type:
        print(f"Creating agent type {MEMEOOORR}")
        memeooorr_type = client.create_agent_type(
            type_name=MEMEOOORR, description="Description of memeooorr"
        )
    print(f"memeooorr_type = {memeooorr_type}")

    # Read or create agent instance (needed to sign)
    memeooorr_instance = client.get_agent_instance_by_address(client.eth_address)

    if not memeooorr_instance:
        print(f"Creating agent instance {client.eth_address}")
        memeooorr_instance = client.create_agent_instance(
            agent_name="Terminator",
            agent_type=memeooorr_type,
            eth_address=client.eth_address,
        )
    print(f"memeooorr_instance = {memeooorr_instance}")

    # Read or create attribute definitions
    memeooorr_attrs = client.get_attribute_definitions_by_agent_type(memeooorr_type)

    if not memeooorr_attrs:
        print("Creating agent type attributes")
        twitter_username_attr_def = client.create_attribute_definition(
            agent_type=memeooorr_type,
            attr_name="twitter_username",
            data_type="string",
            default_value="",
            is_required=True,
        )
        twitter_user_id_attr_def = client.create_attribute_definition(
            agent_type=memeooorr_type,
            attr_name="twitter_user_id",
            data_type="string",
            default_value="",
            is_required=True,
        )
        twitter_interactions_attr_def = client.create_attribute_definition(
            agent_type=memeooorr_type,
            attr_name="twitter_interactions",
            data_type="json",
            default_value="{}",
            is_required=False,
        )
        memeooorr_attrs = client.get_attribute_definitions_by_agent_type(memeooorr_type)
    else:
        (
            twitter_username_attr_def,
            twitter_user_id_attr_def,
            twitter_interactions_attr_def,
        ) = memeooorr_attrs

    print(f"memeooorr_attrs = {memeooorr_attrs}")

    # Create attribute instances
    twitter_username_attr_instance = client.get_attribute_instance(
        memeooorr_instance, twitter_username_attr_def
    )
    if not twitter_username_attr_instance:
        print("Creating twitter_username attribute instance")
        twitter_username_attr_instance = client.create_attribute_instance(
            agent_instance=memeooorr_instance,
            attribute_def=twitter_username_attr_def,
            value="0xTerminator",
        )
    print(f"twitter_username_attr_instance = {twitter_username_attr_instance}")

    twitter_user_id_attr_instance = client.get_attribute_instance(
        memeooorr_instance, twitter_user_id_attr_def
    )
    if not twitter_user_id_attr_instance:
        print("Creating twitter_user_id attribute instance")
        twitter_user_id_attr_instance = client.create_attribute_instance(
            agent_instance=memeooorr_instance,
            attribute_def=twitter_user_id_attr_def,
            value="1234567890",
        )
    print(f"twitter_user_id_attr_instance = {twitter_user_id_attr_instance}")

    # Load the database
    agents_fun_db = AgentsFunDatabase(client=client)
    agents_fun_db.load()

    # Add a post
    post = TwitterPost(
        timestamp=datetime.now(timezone.utc),
        tweet_id="1234567890",
        text="Hello, world!",
    )
    agents_fun_db.agents[0].add_interaction(post)

    # Add a retweet
    retweet = TwitterRewtweet(
        timestamp=datetime.now(timezone.utc),
        tweet_id="0987654321",
    )
    agents_fun_db.agents[0].add_interaction(retweet)

    # Add a like
    like = TwitterLike(
        timestamp=datetime.now(timezone.utc),
        tweet_id="1234567890",
    )
    agents_fun_db.agents[0].add_interaction(like)

    # Add a follow
    follow = TwitterFollow(
        timestamp=datetime.now(timezone.utc),
        username="another_user",
    )
    agents_fun_db.agents[0].add_interaction(follow)


def reset_agents_fun_db(client: AgentDBClient):
    """Reset the database"""

    agents_fun_db = AgentsFunDatabase(client=client)
    agents_fun_db.load()

    for agent in agents_fun_db.agents:
        # Delete attributes instances
        memeooorr_attrs = client.get_all_agent_instance_attributes_parsed(
            agent.agent_instance
        )
        for attr in memeooorr_attrs:
            print(f"Deleting agent attribute {attr.attr_def_id}")
            client.delete_attribute_instance(attr)

        # Delete agent instance
        print(f"Deleting agent instance {agent.agent_instance.agent_id}")
        client.delete_agent_instance(agent.agent_instance)

    # Delete attribute definitions
    memeooorr_attr_defs = client.get_attribute_definitions_by_agent_type(
        agents_fun_db.agent_type
    )
    for attr_def in memeooorr_attr_defs:
        print(f"Deleting attribute definition {attr_def.attr_def_id}")
        client.delete_attribute_definition(attr_def)

    # Delete agent type
    print(f"Deleting agent type {agents_fun_db.agent_type.type_id}")
    client.delete_agent_type(agents_fun_db.agent_type)


def memeooorr_example(client: AgentDBClient):
    """Example usage of the AgentDBClient class."""
    agents_fun_db = AgentsFunDatabase(client=client)
    agents_fun_db.load()

    print(agents_fun_db)
    for agent in agents_fun_db.agents:
        if agent.likes or agent.retweets or agent.posts or agent.follows:
            print(agent)


if __name__ == "__main__":
    # Initialize the client
    db_client = AgentDBClient(
        base_url=os.getenv("MIRROR_DB_BASE_URL"),
        eth_address=os.getenv("AGENT_ADDRESS"),
        private_key=os.getenv("AGENT_PRIVATE_KEY"),
    )

    # reset_agents_fun_db(db_client)
    # init_memeooorr_db(db_client)
    # basic_example(db_client)
    memeooorr_example(db_client)
