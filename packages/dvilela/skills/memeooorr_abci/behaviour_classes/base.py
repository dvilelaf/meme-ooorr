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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from aea.protocols.base import Message
from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.kv_store.connection import (
    PUBLIC_ID as KV_STORE_CONNECTION_PUBLIC_ID,
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
from packages.valory.skills.abstract_round_abci.models import Requests
from packages.valory.skills.agent_db_abci.behaviours import AgentDBBehaviour


BASE_CHAIN_ID = "base"
CELO_CHAIN_ID = "celo"
HTTP_OK = 200
MEMEOOORR_DESCRIPTION_PATTERN = r".*Memeooorr @(\w+)$"
IPFS_ENDPOINT = "https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
MAX_TWEET_CHARS = 280
AGENT_TYPE_NAME = "memeooorr"
LIST_COUNT_TO_KEEP = 20
HOUR_TO_SECONDS = 3600


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


class MemeooorrBaseBehaviour(
    AgentDBBehaviour, ABC
):  # pylint: disable=too-many-ancestors,too-many-public-methods
    """Base behaviour for the memeooorr_abci skill.

    This class provides common functionalities and properties used by other behaviours
    in the Memeooorr ABCI skill.
    """

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

        # Create the request message for Tweepy
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWEEPY_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"method": method, "kwargs": kwargs}),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response_envelope = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        if response_envelope.performative != SrrMessage.Performative.RESPONSE:
            self.context.logger.error(
                f"Unexpected performative from Tweepy connection: {response_envelope.performative}"
            )
            return None

        response_payload_dict = json.loads(response_envelope.payload)  # type: ignore
        actual_tweepy_result = response_payload_dict.get("response")

        if isinstance(actual_tweepy_result, dict) and "error" in actual_tweepy_result:
            error_str = actual_tweepy_result["error"]
            self.context.logger.error(f"Error from Tweepy connection: {error_str}")

            # Check for indicators of different error types
            needs_update = False
            if "Forbidden" in error_str or "403" in error_str:
                self.context.logger.error(
                    f"A Tweepy Forbidden error occurred: {error_str}"
                )
                needs_update = True
            elif "credentials" in error_str.lower():
                self.context.logger.error(
                    f"A Tweepy error occurred due to incomplete credentials: {error_str}"
                )
                needs_update = True

            if needs_update:
                self.context.state.env_var_status["needs_update"] = True
                self.context.state.env_var_status["env_vars"][
                    "TWEEPY_CONSUMER_API_KEY"
                ] = error_str
                self.context.state.env_var_status["env_vars"][
                    "TWEEPY_CONSUMER_API_KEY_SECRET"
                ] = error_str
                self.context.state.env_var_status["env_vars"][
                    "TWEEPY_ACCESS_TOKEN"
                ] = error_str
                self.context.state.env_var_status["env_vars"][
                    "TWEEPY_ACCESS_TOKEN_SECRET"
                ] = error_str
                self.context.state.env_var_status["env_vars"][
                    "TWEEPY_BEARER_TOKEN"
                ] = error_str

        return actual_tweepy_result

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

    def _get_configurable_param(
        self,
        param_name: str,
        initial_param_name: str,
        param_type: type = str,
    ) -> Generator[None, None, Any]:
        """
        Generic helper to get a configurable parameter from synchronized data, DB, or config.

        :param param_name: The name of the parameter in the DB.
        :param initial_param_name: The name of the initial parameter in the DB.
        :param type: The type to cast the parameter value to.
        :return: The resolved parameter value.
        """

        # Never read synchronized data, always read from db
        config_value = getattr(self.params, param_name)

        # Try getting from DB
        db_data = yield from self.read_kv(keys=(param_name, initial_param_name))
        if not db_data:
            self.context.logger.error(
                f"Error while loading the database for {param_name}. Falling back to the config."
            )
            return param_type(config_value)

        initial_db = db_data.get(initial_param_name, None)
        param_db = db_data.get(param_name, None)

        # If the initial value is not in the db, store it
        if initial_db is None:
            yield from self.write_kv({initial_param_name: config_value})
            initial_db = config_value

        # If the param is not in the db, store it
        if param_db is None:
            yield from self.write_kv({param_name: config_value})
            param_db = config_value

        # If the configured value does not match the initial value in the db,
        # the user has reconfigured it and we need to update it:
        if param_type(config_value) != param_type(initial_db):
            yield from self.write_kv(
                {param_name: config_value, initial_param_name: config_value}
            )
            initial_db = config_value
            param_db = config_value

        # At this point, the param in the db is the correct one
        return param_type(param_db)

    def get_persona(self) -> Generator[None, None, str]:
        """Get the agent persona"""
        return (
            yield from self._get_configurable_param(
                param_name="persona",
                initial_param_name="initial_persona",
                param_type=str,
            )
        )

    def get_heart_cooldown_hours(self) -> Generator[None, None, int]:
        """Get the cooldown hours for hearting"""
        return (
            yield from self._get_configurable_param(
                param_name="heart_cooldown_hours",
                initial_param_name="initial_heart_cooldown_hours",
                param_type=int,
            )
        )

    def get_summon_cooldown_seconds(self) -> Generator[None, None, int]:
        """Get the cooldown seconds for summoning"""
        return (
            yield from self._get_configurable_param(
                param_name="summon_cooldown_seconds",
                initial_param_name="initial_summon_cooldown_seconds",
                param_type=int,
            )
        )

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
        last_heart_timestamp = yield from self._read_json_from_kv(
            key="last_heart_timestamp", default_value=0
        )
        time_since_last_heart = now - datetime.fromtimestamp(
            float(last_heart_timestamp)
        )

        heart_cooldown_hours = yield from self.get_heart_cooldown_hours()

        if (
            not is_unleashed
            and meme_data.get("token_nonce", None) != 1
            and time_since_last_heart.total_seconds()
            > (heart_cooldown_hours * HOUR_TO_SECONDS)
        ):
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
            if handle == self.context.state.twitter_username:
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
            if handle == self.context.state.twitter_username:
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

    def init_own_twitter_details(self) -> Generator[None, None, None]:
        """Initialize own Twitter account details, preferring state, and only writing to DB if initialized."""

        db_agent = self.context.agents_fun_db.my_agent
        db_initialized = db_agent is not None  # safeguard

        # --- CASE 1: State already initialized ---
        if self.context.state.twitter_username and self.context.state.twitter_id:
            print("Using cached Twitter details from state.")

            if db_initialized:
                # If DB missing values, sync from state
                if not db_agent.twitter_username or not db_agent.twitter_user_id:
                    db_agent.twitter_username = self.context.state.twitter_username
                    db_agent.twitter_user_id = self.context.state.twitter_id
                    yield from db_agent.update_twitter_details()

            return  # Done, no external call

        # --- CASE 2: State missing, fetch from Twitter ---
        account_details = yield from self._call_tweepy(method="get_me")
        if not account_details:
            self.context.logger.error("Couldn't fetch own Twitter account details.")
            return

        # Update state
        self.context.state.twitter_username = account_details.get("username")
        self.context.state.twitter_id = account_details.get("user_id")
        self.context.state.twitter_display_name = account_details.get("display_name")

        print("Fetched Twitter details from API & updated state.")

        # --- CASE 3: DB not initialized → stop here ---
        if not db_initialized:
            print("DB not initialized — skipping DB update.")
            return

        # --- CASE 4: DB initialized, update it too ---
        db_agent.twitter_username = self.context.state.twitter_username
        db_agent.twitter_user_id = self.context.state.twitter_id

        yield from db_agent.update_twitter_details()

    def _store_agent_action(
        self, action_type: str, action_data: Any
    ) -> Generator[None, None, None]:
        """
        Stores an agent action (tool, tweet, or token) in the KV store.

        :param action_type: The type of action, e.g., "tool_action", "tweet_action".
        :param action_data: The dictionary containing the action data to store.
        """
        current_agent_actions = yield from self._read_json_from_kv("agent_actions", {})

        # Ensure all action types are initialized as lists
        for key in ["tool_action", "tweet_action", "token_action"]:
            current_agent_actions.setdefault(key, [])

        action_list = current_agent_actions.get(action_type)

        if not isinstance(action_list, list):
            self.context.logger.warning(
                f"Expected {action_type} to be a list, but found {type(action_list)}. Resetting to empty list."
            )
            action_list = []

        if isinstance(action_data, dict):
            action_data["timestamp"] = self.get_sync_timestamp()

        action_list.append(action_data)
        current_agent_actions[action_type] = action_list[-10:]

        yield from self._write_kv({"agent_actions": json.dumps(current_agent_actions)})

    def get_latest_agent_actions(
        self, action_type: str, limit: int = 5
    ) -> Generator[None, None, List[Any]]:
        """
        Retrieves the latest agent actions of a specific type from the KV store.

        :param action_type: The type of action to retrieve, e.g., "tool_action", "tweet_action".
        :param limit: The maximum number of actions to return.
        :return: A list of the latest actions.
        """
        agent_actions = yield from self._read_json_from_kv("agent_actions", {})
        action_list = agent_actions.get(action_type, [])

        if not isinstance(action_list, list):
            self.context.logger.warning(
                f"Expected {action_type} to be a list, but found {type(action_list)}. Resetting to empty list."
            )
            return []

        # Return the last 'limit' items
        return action_list[-limit:]

    def _read_json_from_kv(
        self, key: str, default_value: Any
    ) -> Generator[None, None, Any]:
        """Helper to get and parse stored JSON KV data."""
        data = yield from self._read_kv(keys=(key,))
        if not data or not data.get(key):
            self.context.logger.info(f"No {key} found in KV store, returning default.")
            return default_value
        try:
            return json.loads(data[key])
        except (json.JSONDecodeError, TypeError):
            self.context.logger.warning(
                f"Could not decode JSON for key {key}, returning default."
            )
            return default_value

    def _read_value_from_kv(
        self, key: str, default_value: Any
    ) -> Generator[None, None, Any]:
        """Helper to get and parse stored KV data."""
        data = yield from self._read_kv(keys=(key,))
        if not data or not data.get(key):
            self.context.logger.info(f"No {key} found in KV store, returning default.")
            return default_value

        return data[key]

    def _store_media_info_list(self, media_info: Dict) -> Generator[None, None, None]:
        """Store media info in the key-value store"""
        media_store_list = yield from self._read_media_info_list()
        media_store_list.append(media_info)

        # Enforce retention policy: keep only the latest 20 media files
        if len(media_store_list) > LIST_COUNT_TO_KEEP:
            num_to_remove = len(media_store_list) - LIST_COUNT_TO_KEEP
            old_media_entries = media_store_list[:num_to_remove]

            for entry in old_media_entries:
                file_path = entry.get("path")
                self._cleanup_temp_file(file_path, "old media file")

            media_store_list = media_store_list[num_to_remove:]

        yield from self._write_kv({"media-store-list": json.dumps(media_store_list)})

    def _read_media_info_list(self) -> Generator[None, None, List[Dict]]:
        """Read media info from the key-value store"""
        raw_list = yield from self._read_json_from_kv("media-store-list", [])

        if not isinstance(raw_list, list):
            self.context.logger.error(
                f"Expected media-store-list to be a list, but found {type(raw_list)}. Returning empty list."
            )
            return []

        return raw_list

    def _cleanup_temp_file(self, file_path: Optional[str], reason: str) -> None:
        """Attempt to remove a temporary file and log the outcome."""
        if file_path:
            path = Path(file_path)
            path.unlink()
            self.context.logger.info(f"Removed temporary file ({reason}): {file_path}")
        else:
            self.context.logger.warning(f"No file to remove ({reason})")
