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

"""This module contains the handlers for the skill of MemeooorrAbciApp."""

import json
import mimetypes
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

import peewee
import requests
import yaml
from aea.configurations.data_types import PublicId
from aea.protocols.base import Message
from aea.protocols.dialogue.base import Dialogue
from aea_ledger_ethereum.ethereum import EthereumCrypto
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.protocols.kv_store.message import KvStoreMessage
from packages.dvilela.skills.memeooorr_abci.dialogues import (
    HttpDialogue,
    HttpDialogues,
    SrrDialogues,
)
from packages.dvilela.skills.memeooorr_abci.models import Params, SharedState
from packages.dvilela.skills.memeooorr_abci.prompts import (
    CHATUI_PROMPT,
    CHATUI_PROMPT_NO_MEMECOIN,
    build_updated_agent_config_schema,
    build_updated_agent_config_schema_no_memecoin,
)
from packages.dvilela.skills.memeooorr_abci.rounds import SynchronizedData
from packages.dvilela.skills.memeooorr_abci.rounds_info import ROUNDS_INFO
from packages.valory.connections.http_server.connection import (
    PUBLIC_ID as HTTP_SERVER_PUBLIC_ID,
)
from packages.valory.protocols.http.message import HttpMessage
from packages.valory.protocols.srr.message import SrrMessage
from packages.valory.skills.abstract_round_abci.handlers import (
    ABCIRoundHandler as BaseABCIRoundHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import AbstractResponseHandler
from packages.valory.skills.abstract_round_abci.handlers import (
    ContractApiHandler as BaseContractApiHandler,
)
from packages.valory.skills.abstract_round_abci.handlers import (
    HttpHandler as BaseHttpHandler,
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
from packages.valory.skills.funds_manager.behaviours import GET_FUNDS_STATUS_METHOD_NAME
from packages.valory.skills.funds_manager.models import FundRequirements


ABCIHandler = BaseABCIRoundHandler
SigningHandler = BaseSigningHandler
LedgerApiHandler = BaseLedgerApiHandler
ContractApiHandler = BaseContractApiHandler
TendermintHandler = BaseTendermintHandler
IpfsHandler = BaseIpfsHandler

AGENT_PROFILE_PATH = "agentsfun-ui-build"


OK_CODE = 200
NOT_FOUND_CODE = 404
TOO_EARLY_CODE = 425
TOO_MANY_REQUESTS_CODE = 429
INTERNAL_SERVER_ERROR_CODE = 500
BAD_REQUEST_CODE = 400
AVERAGE_PERIOD_SECONDS = 10


PROMPT_FIELD = "prompt"
LLM_MESSAGE_FIELD = "reasoning"

GENAI_API_KEY_NOT_SET_ERROR = "No API_KEY or ADC found."
GENAI_RATE_LIMIT_ERROR = "429"

BASE_CHAIN_NAME = "base"
BASE_CHAIN_ID = 8453


ETH_ADDRESS = "0x0000000000000000000000000000000000000000"
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
SLIPPAGE_FOR_SWAP = "0.003"  # 0.3%


def camel_to_snake(camel_str: str) -> str:
    """Converts from CamelCase to snake_case"""
    snake_str = re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str).lower()
    return snake_str


def load_fsm_spec() -> Dict:
    """Load the chained FSM spec"""
    with open(
        Path(__file__).parent.parent
        / "memeooorr_chained_abci"
        / "fsm_specification.yaml",
        "r",
        encoding="utf-8",
    ) as spec_file:
        return yaml.safe_load(spec_file)


def get_password_from_args() -> Optional[str]:
    """Extract password from command line arguments."""
    args = sys.argv
    try:
        password_index = args.index("--password")
        if password_index + 1 < len(args):
            return args[password_index + 1]
    except ValueError:
        pass

    for arg in args:
        if arg.startswith("--password="):
            return arg.split("=", 1)[1]

    return None


class SrrHandler(AbstractResponseHandler):
    """A class for handling SRR messages."""

    SUPPORTED_PROTOCOL: Optional[PublicId] = SrrMessage.protocol_id
    allowed_response_performatives = frozenset(
        {
            SrrMessage.Performative.REQUEST,
            SrrMessage.Performative.RESPONSE,
        }
    )

    def handle(self, message: Message) -> None:
        """
        React to an SRR message.

        :param message: the SrrMessage instance
        """
        self.context.logger.info(f"Received Srr message: {message}")
        srr_msg = cast(SrrMessage, message)

        if srr_msg.performative not in self.allowed_response_performatives:
            self.context.logger.warning(
                f"SRR performative not recognized: {srr_msg.performative}"
            )
            return

        nonce = srr_msg.dialogue_reference[
            0
        ]  # Assuming dialogue_reference is accessible
        callback, kwargs = self.context.state.req_to_callback.pop(nonce, (None, {}))

        if callback is None:
            super().handle(message)
        else:
            dialogue = self.context.srr_dialogues.update(srr_msg)
            callback(srr_msg, dialogue, **kwargs)


class KvStoreHandler(AbstractResponseHandler):
    """A class for handling KeyValue messages."""

    SUPPORTED_PROTOCOL: Optional[PublicId] = KvStoreMessage.protocol_id
    allowed_response_performatives = frozenset(
        {
            KvStoreMessage.Performative.READ_REQUEST,
            KvStoreMessage.Performative.CREATE_OR_UPDATE_REQUEST,
            KvStoreMessage.Performative.READ_RESPONSE,
            KvStoreMessage.Performative.SUCCESS,
            KvStoreMessage.Performative.ERROR,
        }
    )


class HttpMethod(Enum):
    """Http methods"""

    GET = "get"
    HEAD = "head"
    POST = "post"


# Create a DatabaseProxy instance at the module level
db = peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    """Base model for peewee"""

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta class for peewee"""

        database = db


class Store(BaseModel):
    """Database Store table"""

    key = peewee.CharField(unique=True)
    value = peewee.CharField()


class HttpHandler(BaseHttpHandler):
    """This implements the echo handler."""

    SUPPORTED_PROTOCOL = HttpMessage.protocol_id

    def setup(self) -> None:
        """Implement the setup."""

        # Only check funds if using X402
        if self.context.params.use_x402:
            self.shared_state.sufficient_funds_for_x402_payments = False
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self._ensure_sufficient_funds_for_x402_payments)
                executor.shutdown(wait=False)

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
            "health_url": rf"{hostname_regex}\/healthcheck",
            "agent_details_url": rf"{hostname_regex}\/agent-info",
            "x_activity_url": rf"{hostname_regex}\/x-activity",
            "meme_coins_url": rf"{hostname_regex}\/memecoin-activity",
            "media_url": rf"{hostname_regex}\/media",
            "process_prompt_url": rf"{hostname_regex}\/configure_strategies",
            "funds_status_url": rf"{hostname_regex}\/funds-status",
            "static_files_url": rf"{hostname_regex}\/(.*)",
            "features_url": rf"{hostname_regex}\/features",
        }

        # Routes
        self.routes = {  # pylint: disable=attribute-defined-outside-init
            (HttpMethod.POST.value,): [
                (route_regexes["process_prompt_url"], self._handle_post_process_prompt),
            ],
            (HttpMethod.GET.value, HttpMethod.HEAD.value): [
                (route_regexes["health_url"], self._handle_get_health),
                (route_regexes["agent_details_url"], self._handle_get_agent_details),
                (route_regexes["x_activity_url"], self._handle_get_recent_x_activity),
                (route_regexes["meme_coins_url"], self._handle_get_meme_coins),
                (route_regexes["media_url"], self._handle_get_media),
                (route_regexes["funds_status_url"], self._handle_get_funds_status),
                (route_regexes["features_url"], self._handle_get_features),
                (
                    route_regexes["static_files_url"],
                    self._handle_get_static_file,
                ),  # Always keep this last as its a catch-all
            ],
        }

        self.json_content_header = "Content-Type: application/json\n"  # pylint: disable=attribute-defined-outside-init
        self.html_content_header = "Content-Type: text/html\n"  # pylint: disable=attribute-defined-outside-init

        # Load round info for the healthcheck
        fsm = load_fsm_spec()

        self.rounds_info: Dict = (  # pylint: disable=attribute-defined-outside-init
            ROUNDS_INFO
        )
        for source_info, target_round in fsm["transition_func"].items():
            source_round, event = source_info[1:-1].split(", ")
            source_round = camel_to_snake(source_round)
            self.rounds_info[source_round]["transitions"] = {}  # type: ignore
            self.rounds_info[source_round]["transitions"][  # type: ignore
                event.lower()
            ] = camel_to_snake(target_round)
        # TODO : Modify it according to agents.fun it is currently from optimus
        self.agent_profile_path = (  # pylint: disable=attribute-defined-outside-init
            AGENT_PROFILE_PATH
        )

    @contextmanager
    def _db_connection_context(self) -> Generator:
        """A context manager for database connections."""
        self.db_connect()
        try:
            yield
        finally:
            self.db_disconnect()

    def db_connect(self) -> None:
        """Connect to the database."""

        store_path_prefix = self.context.params.store_path

        db_path = Path(store_path_prefix) / "memeooorr.db"  # nosec
        self.db = (  # pylint: disable=attribute-defined-outside-init
            peewee.SqliteDatabase(db_path)
        )
        db.initialize(self.db)  # Initialize the proxy with the concrete db instance
        self.db.connect()
        # We know the table is created by KvStoreConnection

    def db_disconnect(self) -> None:
        """Teardown the handler."""
        if hasattr(self, "db") and self.db and not self.db.is_closed():
            self.db.close()

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return SynchronizedData(
            db=self.context.state.round_sequence.latest_synchronized_data.db
        )

    @property
    def params(self) -> Params:
        """Get the params."""
        return self.context.params

    @property
    def is_memecoin_logic_enabled(self) -> bool:
        """Check if memecoin logic is enabled."""
        return self.params.is_memecoin_logic_enabled

    @property
    def shared_state(self) -> SharedState:
        """Get the parameters."""
        return cast(SharedState, self.context.state)

    @property
    def funds_status(self) -> FundRequirements:
        """Get the fund status."""
        return self.context.shared_state[GET_FUNDS_STATUS_METHOD_NAME]()

    def _get_handler(self, url: str, method: str) -> Tuple[Optional[Callable], Dict]:
        """Check if an url is meant to be handled in this handler

        We expect url to match the pattern {hostname}/.*,
        where hostname is allowed to be localhost, 127.0.0.1 or the service_endpoint's hostname.
        :param url: the url to check
        :param method: the method
        :returns: the handling method if the message is intended to be handled by this handler, None otherwise, and the regex captures
        """
        # Check base url
        if not re.match(self.handler_url_regex, url):
            self.context.logger.info(
                f"The url {url} does not match the HttpHandler's pattern: {self.handler_url_regex}"
            )
            return None, {}

        # Check if there is a route for this request
        for methods, routes in self.routes.items():
            if method not in methods:
                continue

            for route in routes:
                # Routes are tuples like (route_regex, handle_method)
                m = re.match(route[0], url)
                if m:
                    return route[1], m.groupdict()

        # No route found
        self.context.logger.info(
            f"The message [{method}] {url} is intended for the HttpHandler but did not match any valid pattern"
        )
        return self._handle_bad_request, {}

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to an envelope.

        :param message: the message
        """
        http_msg = cast(HttpMessage, message)

        # Check if this is a request sent from the http_server skill
        if (
            http_msg.performative != HttpMessage.Performative.REQUEST
            or message.sender != str(HTTP_SERVER_PUBLIC_ID.without_hash())
        ):
            super().handle(message)
            return

        # Check if this message is for this skill. If not, send to super()
        handler, kwargs = self._get_handler(http_msg.url, http_msg.method)
        if not handler:
            super().handle(message)
            return

        self.context.logger.info(
            f"Selected handler: {handler.__name__ if handler is not None else None}"
        )

        # Retrieve dialogues
        http_dialogues = cast(HttpDialogues, self.context.http_dialogues)
        http_dialogue = cast(HttpDialogue, http_dialogues.update(http_msg))

        # Invalid message
        if http_dialogue is None:
            self.context.logger.info(
                "Received invalid http message={}, unidentified dialogue.".format(
                    http_msg
                )
            )
            return

        # Handle message
        self.context.logger.info(
            "Received http request with method={}, url={} and body={!r}".format(
                http_msg.method,
                http_msg.url,
                http_msg.body,
            )
        )
        handler(http_msg, http_dialogue, **kwargs)

    def _handle_bad_request(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle a Http bad request.

        :param http_msg: the http message
        :param http_dialogue: the http dialogue
        """
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=BAD_REQUEST_CODE,
            status_text="Bad request",
            headers=http_msg.headers,
            body=json.dumps(body).encode("utf-8"),
        )

        # Send response
        self.context.logger.info(f"Responding with {BAD_REQUEST_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _handle_get_health(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """
        Handle a Http request of verb GET.

        :param http_msg: the http message
        :param http_dialogue: the http dialogue
        """
        seconds_since_last_transition = None
        is_tm_unhealthy = None
        is_transitioning_fast = None
        current_round = None
        rounds = None

        round_sequence = cast(SharedState, self.context.state).round_sequence

        if (
            round_sequence._last_round_transition_timestamp  # pylint: disable=protected-access
        ):
            is_tm_unhealthy = cast(
                SharedState, self.context.state
            ).round_sequence.block_stall_deadline_expired

            current_time = datetime.now().timestamp()
            seconds_since_last_transition = current_time - datetime.timestamp(
                round_sequence._last_round_transition_timestamp  # pylint: disable=protected-access
            )

            is_transitioning_fast = (
                not is_tm_unhealthy
                and seconds_since_last_transition
                < 2 * self.context.params.reset_pause_duration
            )

        if round_sequence._abci_app:  # pylint: disable=protected-access
            current_round = (
                round_sequence._abci_app.current_round.round_id  # pylint: disable=protected-access
            )
            rounds = [
                r.round_id
                for r in round_sequence._abci_app._previous_rounds[  # pylint: disable=protected-access
                    -25:
                ]
            ]
            rounds.append(current_round)

        data = {
            "seconds_since_last_transition": seconds_since_last_transition,
            "is_tm_healthy": not is_tm_unhealthy,
            "period": self.synchronized_data.period_count,
            "reset_pause_duration": self.context.params.reset_pause_duration,
            "rounds": rounds,
            "is_transitioning_fast": is_transitioning_fast,
            "rounds_info": self.rounds_info,
            "env_var_status": self.context.state.env_var_status,
        }

        self._send_ok_response(http_msg, http_dialogue, data)

    def _get_json_from_db(self, key: str, default: str = "{}") -> Union[Dict, List]:
        """Get a JSON value from the database."""
        record = Store.get_or_none(Store.key == key)
        value = record.value if record and record.value else default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            self.context.logger.warning(
                f"Could not decode JSON for key {key}, value: {value}"
            )
            return json.loads(default)

    @staticmethod
    def _get_value_from_db(key: str, default: Any = "") -> Any:
        """Get a value from the database."""
        record = Store.get_or_none(Store.key == key)
        value = record.value if record and record.value else default
        return value

    @staticmethod
    def _set_value_to_db(key: str, value: str) -> None:
        """Set a value in the database."""
        record = Store.get_or_none(Store.key == key)
        if not record:
            Store.create(key=key, value=value)
        else:
            record.value = value
            record.save()

    def _handle_get_agent_details(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a Http request of verb GET."""

        with self._db_connection_context():
            with self.db.atomic():
                agent_details = cast(
                    Dict, self._get_json_from_db("agent_details", "{}")
                )

        if not agent_details:
            self._send_ok_response(http_msg, http_dialogue, None)  # type: ignore
            return

        data = {
            "address": agent_details.get("safe_address"),
            "username": agent_details.get("twitter_username"),
            "name": agent_details.get("twitter_display_name"),
            "personaDescription": agent_details.get("persona"),
        }

        self._send_ok_response(http_msg, http_dialogue, data)

    def _handle_get_recent_x_activity(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a Http request of verb GET."""

        ipfs_gateway_url = self.context.params.ipfs_address

        with self._db_connection_context():
            with self.db.atomic():
                agent_actions = self._get_json_from_db("agent_actions", "{}")

        tweet_actions = agent_actions.get("tweet_action", [])  # type: ignore
        if not tweet_actions:
            self._send_ok_response(http_msg, http_dialogue, None)  # type: ignore
            return

        latest_tweet_action = tweet_actions[-1]

        action_data = latest_tweet_action.get("action_data", {})
        action_type = latest_tweet_action.get("action_type")

        # if the latest tweet actoin is follow then we fetch user_id as postId
        if action_type == "follow":
            postId = action_data.get("username")
        else:
            postId = action_data.get("tweet_id")

        activity = {
            "postId": postId,
            "type": action_type,
            "timestamp": latest_tweet_action.get("timestamp"),
            "text": action_data.get("text"),
        }

        if action_type == "tweet_with_media":
            activity["media"] = [
                f"{ipfs_gateway_url}{action_data.get('media_ipfs_hash', None)}"
            ]

        self._send_ok_response(http_msg, http_dialogue, activity)

    def _handle_get_meme_coins(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a Http request of verb GET."""
        activities = self._get_latest_token_activities()
        self._send_ok_response(http_msg, http_dialogue, activities)  # type: ignore

    def _get_latest_token_activities(self, limit: int = 1) -> Optional[List[Dict]]:
        """Get the latest token activities from the database."""
        with self._db_connection_context():
            with self.db.atomic():
                agent_actions = self._get_json_from_db("agent_actions", "{}")

        token_actions = agent_actions.get("token_action", [])  # type: ignore

        if not token_actions:
            return None

        activities = []  # type: ignore
        for token_action in reversed(token_actions):
            if len(activities) == limit:
                break

            tweet_id = token_action.get("tweet_id")
            if not tweet_id:
                continue

            token_address = token_action.get("token_address")
            activity = {
                "type": token_action.get("action"),
                "timestamp": token_action.get("timestamp"),
                "postId": tweet_id,
                "token": {
                    "address": token_address if token_address else None,
                    "nonce": token_action.get("token_nonce"),
                    "symbol": token_action.get("token_ticker"),
                },
            }
            activities.append(activity)

        if not activities:
            return None

        activities.reverse()
        return activities

    def _handle_get_media(  # pylint: disable=too-many-locals
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Fetch and process media data from the database."""
        ipfs_gateway_url = self.context.params.ipfs_address

        with self._db_connection_context():
            with self.db.atomic():
                media_list = self._get_json_from_db("media-store-list", "[]")
                if not media_list:
                    self._send_ok_response(http_msg, http_dialogue, None)  # type: ignore
                    return
                agent_actions = self._get_json_from_db("agent_actions", "{}")

        tweet_actions = agent_actions.get("tweet_action", [])  # type: ignore
        media_path_to_tweet_id = {}
        for tweet_action in tweet_actions:
            action_data = tweet_action.get("action_data", {})
            media_path = action_data.get("media_path")
            tweet_id = action_data.get("tweet_id")
            if media_path and tweet_id:
                media_path_to_tweet_id[media_path] = tweet_id

        processed_media_list = []
        for media_item in media_list:
            path = media_item.get("path")
            ipfs_hash = media_item.get("ipfs_hash")
            post_id = media_path_to_tweet_id.get(path)

            if post_id and ipfs_hash:
                media_item["postId"] = post_id
                media_item["path"] = f"{ipfs_gateway_url}{ipfs_hash}"
                media_item.pop("hash", None)
                media_item.pop("media_path", None)
                media_item.pop("ipfs_hash", None)
                processed_media_list.append(media_item)

        media_list[:] = processed_media_list

        self._send_ok_response(http_msg, http_dialogue, media_list)  # type: ignore

    def _handle_get_features(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """
        Handle a GET request to check if chat feature is enabled.

        :param http_msg: the HTTP message
        :param http_dialogue: the HTTP dialogue
        """
        # Check if using X402 or if GENAI_API_KEY is set
        use_x402 = getattr(self.context.params, "use_x402", False)

        if use_x402:
            # If using X402, chat is enabled without API key check
            is_chat_enabled = True
        else:
            # Otherwise, check if GENAI_API_KEY is set
            api_key = self.context.params.genai_api_key
            is_chat_enabled = (
                api_key is not None
                and isinstance(api_key, str)
                and api_key.strip() != ""
                and api_key != "${str:}"
                and api_key != '""'
            )

        data = {"isChatEnabled": is_chat_enabled}
        self._send_ok_response(http_msg, http_dialogue, data)

    def _handle_get_static_file(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a HTTP GET request for a static file.

        This handler also serves the `index.html` file for any path that does not
        correspond to an existing static file, which is a common pattern for
        Single Page Applications (SPAs).

        :param http_msg: the HTTP message
        :param http_dialogue: the HTTP dialogue
        """
        requested_path = urlparse(http_msg.url).path.lstrip("/")
        file_path = Path(Path(__file__).parent, self.agent_profile_path, requested_path)

        # Check if the requested path points to an existing file.
        if file_path.is_file():
            # If it's a file, serve it directly.
            with open(file_path, "rb") as file:
                file_content = file.read()

            # Determine the content type based on the file extension
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = "application/octet-stream"

            # Send the file content as a response
            self._send_ok_response(http_msg, http_dialogue, file_content, content_type)
            return

        #    and fall back to serving `index.html`.
        index_path = Path(Path(__file__).parent, self.agent_profile_path, "index.html")

        # Check if `index.html` exists before trying to serve it.
        if not index_path.is_file():
            # If `index.html` is missing, the application is misconfigured.
            self._send_not_found_response(http_msg, http_dialogue)
            return

        # Serve the `index.html` file.
        with open(index_path, "r", encoding="utf-8") as file:
            index_html = file.read()
        self._send_ok_response(http_msg, http_dialogue, index_html, "text/html")

    def _send_message(
        self,
        message: Message,
        dialogue: Dialogue,
        callback: Callable,
        callback_kwargs: Optional[Dict] = None,
    ) -> None:
        """
        Send a message and set up a callback for the response.

        :param message: the Message to send
        :param dialogue: the Dialogue context
        :param callback: the callback function upon response
        :param callback_kwargs: optional kwargs for the callback
        """
        self.context.outbox.put_message(message=message)
        nonce = dialogue.dialogue_label.dialogue_reference[0]
        self.context.state.req_to_callback[nonce] = (callback, callback_kwargs or {})

    def _get_prompt_and_schema(
        self,
        user_prompt: str,
    ) -> Tuple[str, dict]:
        if self.is_memecoin_logic_enabled:
            with self._db_connection_context():
                with self.db.atomic():
                    current_persona = self._get_value_from_db("persona", "")

                    current_heart_cooldown_hours = self._get_value_from_db(
                        "heart_cooldown_hours", None
                    )
                    current_summon_cooldown_seconds = self._get_value_from_db(
                        "summon_cooldown_seconds", None
                    )

            prompt = CHATUI_PROMPT.format(
                user_prompt=user_prompt,
                current_persona=current_persona,
                current_heart_cooldown_hours=current_heart_cooldown_hours,
                current_summon_cooldown_seconds=current_summon_cooldown_seconds,
            )

            prompt_schema = build_updated_agent_config_schema()

            return prompt, prompt_schema

        with self._db_connection_context():
            with self.db.atomic():
                current_persona = self._get_value_from_db("persona", "")

        prompt = CHATUI_PROMPT_NO_MEMECOIN.format(
            user_prompt=user_prompt,
            current_persona=current_persona,
        )
        prompt_schema = build_updated_agent_config_schema_no_memecoin()

        return prompt, prompt_schema

    def _handle_post_process_prompt(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """
        Handle POST requests to process user prompts.

        :param http_msg: the HttpMessage instance
        :param http_dialogue: the HttpDialogue instance
        """

        self.context.logger.info("Handling chatui prompt")

        if self.context.params.use_x402:
            sufficient_funds_for_x402_payments = getattr(
                self.shared_state, "sufficient_funds_for_x402_payments", False
            )
            if not sufficient_funds_for_x402_payments:
                self._send_too_early_response(
                    http_msg,
                    http_dialogue,
                    {"error": "System initializing. Please wait for some time."},
                )
                return

        # Parse incoming data
        data = json.loads(http_msg.body.decode("utf-8"))
        user_prompt = data.get(PROMPT_FIELD, "")

        if not user_prompt:
            self._handle_bad_request(
                http_msg,
                http_dialogue,
                {"error": "User prompt is required."},
            )
            return

        prompt, schema = self._get_prompt_and_schema(user_prompt=user_prompt)

        self._send_chatui_llm_request(
            prompt=prompt,
            schema=schema,
            http_msg=http_msg,
            http_dialogue=http_dialogue,
        )

    def _send_chatui_llm_request(
        self,
        prompt: str,
        schema: dict,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
    ) -> None:
        # Prepare payload data
        payload_data = {
            "prompt": prompt,
            "schema": schema,
        }

        self.context.logger.info(f"Payload data: {payload_data}")

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        request_srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(GENAI_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(payload_data),
        )

        callback_kwargs = {"http_msg": http_msg, "http_dialogue": http_dialogue}
        self._send_message(
            request_srr_message,
            srr_dialogue,
            self._handle_llm_response,
            callback_kwargs,
        )

    def _handle_llm_response(
        self,
        llm_response_message: SrrMessage,
        dialogue: Dialogue,  # pylint: disable=unused-argument
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
    ) -> None:
        """
        Handle the response from the LLM.

        :param llm_response_message: the SrrMessage with the LLM output
        :param dialogue: the Dialogue
        :param http_msg: the original HttpMessage
        :param http_dialogue: the original HttpDialogue
        """

        self.context.logger.info(
            f"LLM response payload: {llm_response_message.payload}"
        )

        genai_response: dict = json.loads(llm_response_message.payload)

        if "error" in genai_response:
            self._handle_chatui_llm_error(
                genai_response["error"], http_msg, http_dialogue
            )
            return

        llm_response = genai_response.get("response", "{}")
        updated_persona: str = json.loads(llm_response).get("agent_persona", None)
        updated_heart_cooldown_hours = json.loads(llm_response).get(
            "heart_cooldown_hours", None
        )
        updated_summon_cooldown_seconds = json.loads(llm_response).get(
            "summon_cooldown_seconds", None
        )
        reasoning = json.loads(llm_response).get("message", "")

        updated_params = {}

        if updated_persona:
            # Update the persona in the database
            with self._db_connection_context():
                with self.db.atomic():
                    self._set_value_to_db("persona", updated_persona)
            updated_params.update({"persona": updated_persona})
            self.context.logger.info(f"Updated persona: {updated_persona}")

            with self._db_connection_context():
                with self.db.atomic():
                    agent_details = cast(Dict, self._get_json_from_db("agent_details"))

            agent_details["persona"] = updated_persona

            with self._db_connection_context():
                with self.db.atomic():
                    self._set_value_to_db("agent_details", json.dumps(agent_details))

        if updated_heart_cooldown_hours:
            # One more check just in case the llm allows it through
            if int(updated_heart_cooldown_hours) < 24:
                updated_heart_cooldown_hours = 24

            # Update the heart_cooldown_hours in the database
            with self._db_connection_context():
                with self.db.atomic():
                    self._set_value_to_db(
                        "heart_cooldown_hours", updated_heart_cooldown_hours
                    )
            updated_params.update(
                {"heart_cooldown_hours": updated_heart_cooldown_hours}
            )
            self.context.logger.info(
                f"Updated heart_cooldown_hours: {updated_heart_cooldown_hours}"
            )
        if updated_summon_cooldown_seconds:
            # One more check just in case the llm allows it through
            if int(updated_summon_cooldown_seconds) < 2592000:
                updated_summon_cooldown_seconds = 2592000

            # Update the summon_cooldown_seconds in the database
            with self._db_connection_context():
                with self.db.atomic():
                    self._set_value_to_db(
                        "summon_cooldown_seconds", updated_summon_cooldown_seconds
                    )
            updated_params.update(
                {"summon_cooldown_seconds": updated_summon_cooldown_seconds}
            )
            self.context.logger.info(
                f"Updated summon_cooldown_seconds: {updated_summon_cooldown_seconds}"
            )

        self._send_ok_response(
            http_msg,
            http_dialogue,
            {
                "updated_params": updated_params,
                "message": (
                    "Params successfully updated"
                    if updated_params
                    else "No Params updated"
                ),
                LLM_MESSAGE_FIELD: reasoning,
            },
        )

    def _handle_chatui_llm_error(
        self, error_message: str, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        self.context.logger.error(f"LLM error response: {error_message}")
        if GENAI_API_KEY_NOT_SET_ERROR in error_message:
            self._send_internal_server_error_response(
                http_msg,
                http_dialogue,
                {"error": "No GENAI_API_KEY set."},
            )
            return
        if GENAI_RATE_LIMIT_ERROR in error_message:
            self._send_too_many_requests_response(
                http_msg,
                http_dialogue,
                {"error": "Too many requests to the LLM."},
            )
            return
        self._send_internal_server_error_response(
            http_msg,
            http_dialogue,
            {"error": "An error occurred while processing the request."},
        )

    def _send_ok_response(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        data: Union[Dict, List, str, bytes],
        content_type: Optional[str] = None,
    ) -> None:
        """Send an OK response with the provided data"""

        body_bytes: bytes
        headers: str

        if isinstance(data, bytes):
            body_bytes = data
            header_content_type = (
                f"Content-Type: {content_type}\n"
                if content_type
                else self.json_content_header
            )
            headers = f"{header_content_type}{http_msg.headers}"
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
            header_content_type = (
                f"Content-Type: {content_type}\n"
                if content_type
                else self.html_content_header
            )
            headers = f"{header_content_type}{http_msg.headers}"
        else:
            body_bytes = json.dumps(data).encode("utf-8")
            headers = f"{self.json_content_header}{http_msg.headers}"

        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=OK_CODE,
            status_text="Success",
            headers=headers,
            body=body_bytes,
        )

        # Send response
        self.context.logger.info(f"Responding with {OK_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _send_too_early_response(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a too early response"""
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=TOO_EARLY_CODE,
            status_text="Too Early",
            headers=http_msg.headers,
            body=json.dumps(body).encode("utf-8"),
        )
        # Send response
        self.context.logger.info(f"Responding with {TOO_EARLY_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _send_too_many_requests_response(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a too many requests response"""
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=TOO_MANY_REQUESTS_CODE,
            status_text="Too Many Requests",
            headers=http_msg.headers,
            body=json.dumps(body).encode("utf-8"),
        )
        # Send response
        self.context.logger.info(f"Responding with {TOO_MANY_REQUESTS_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _send_internal_server_error_response(
        self,
        http_msg: HttpMessage,
        http_dialogue: HttpDialogue,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send an internal server error response"""
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=INTERNAL_SERVER_ERROR_CODE,
            status_text="Internal Server Error",
            headers=http_msg.headers,
            body=json.dumps(body).encode("utf-8"),
        )
        # Send response
        self.context.logger.info(f"Responding with {TOO_MANY_REQUESTS_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _send_not_found_response(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Send an not found response"""
        http_response = http_dialogue.reply(
            performative=HttpMessage.Performative.RESPONSE,
            target_message=http_msg,
            version=http_msg.version,
            status_code=NOT_FOUND_CODE,
            status_text="Not found",
            headers=http_msg.headers,
            body=b"",
        )
        # Send response
        self.context.logger.info(f"Responding with {NOT_FOUND_CODE}")
        self.context.outbox.put_message(message=http_response)

    def _handle_get_funds_status(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a fund status request."""

        self._send_ok_response(
            http_msg,
            http_dialogue,
            self.funds_status.get_response_body(),
        )

    def _get_eoa_account(self) -> Optional[LocalAccount]:
        """Get the EOA account, handling both plaintext and encrypted private keys."""
        default_ledger = self.context.default_ledger_id
        eoa_file_path = (
            Path(self.context.data_dir) / f"{default_ledger}_private_key.txt"
        )

        password = get_password_from_args()
        if password is None:
            self.context.logger.error("No password provided for encrypted private key.")

            # Fallback to plaintext private key
            with eoa_file_path.open("r") as f:
                private_key = f.read().strip()
        else:
            crypto = EthereumCrypto(
                private_key_path=str(eoa_file_path), password=password
            )
            private_key = crypto.private_key

        try:
            # pylint: disable=no-value-for-parameter
            return Account.from_key(private_key)
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Failed to decrypt private key: {e}")
            return None

    def _get_web3_instance(self, chain: str) -> Optional[Web3]:
        """Get Web3 instance for the specified chain."""
        try:
            rpc_url = self.params.base_ledger_rpc

            if not rpc_url:
                self.context.logger.warning(f"No RPC URL for {chain}")
                return None

            # Commented for future debugging purposes:
            # Note that you should create only one HTTPProvider with the same provider URL per python process,
            # as the HTTPProvider recycles underlying TCP/IP network connections, for better performance.
            # Multiple HTTPProviders with different URLs will work as expected.
            return Web3(Web3.HTTPProvider(rpc_url))
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error creating Web3 instance: {str(e)}")
            return None

    def _check_usdc_balance(
        self, eoa_address: str, chain: str, usdc_address: str
    ) -> Optional[float]:
        """Check USDC balance using Web3 library."""
        try:
            w3 = self._get_web3_instance(chain)
            if not w3:
                return None

            # ERC20 ABI for balanceOf
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                }
            ]

            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address), abi=erc20_abi
            )
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(eoa_address)
            ).call()
            return balance
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error checking USDC balance: {str(e)}")
            return None

    def _get_lifi_quote_sync(
        self, eoa_address: str, usdc_address: str, to_amount: str
    ) -> Optional[Dict]:
        """Get LiFi quote synchronously."""
        try:
            chain_id = BASE_CHAIN_ID

            params = {
                "fromChain": chain_id,
                "toChain": chain_id,
                "fromToken": ETH_ADDRESS,
                "toToken": usdc_address,
                "fromAddress": eoa_address,
                "toAddress": eoa_address,
                "toAmount": to_amount,
                "slippage": SLIPPAGE_FOR_SWAP,
                "integrator": "valory",
            }

            response = requests.get(
                self.params.lifi_quote_to_amount_url, params=params, timeout=30
            )

            if response.status_code == 200:
                return response.json()

            return None
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error getting LiFi quote: {str(e)}")
            return None

    def _sign_and_submit_tx_web3(
        self, tx_data: Dict, chain: str, eoa_account: LocalAccount
    ) -> Optional[str]:
        """Sign and submit transaction using Web3."""
        try:
            w3 = self._get_web3_instance(chain)
            if not w3:
                return None

            signed_tx = eoa_account.sign_transaction(tx_data)

            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return tx_hash.hex()

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error submitting transaction: {str(e)}")
            return None

    def _check_transaction_status(
        self, tx_hash: str, chain: str, timeout: int = 60
    ) -> bool:
        """Check if transaction was successful by waiting for receipt."""
        try:
            w3 = self._get_web3_instance(chain)
            if not w3:
                return False

            self.context.logger.info(
                f"Waiting for transaction {tx_hash} to be mined..."
            )

            # Wait for transaction receipt with timeout
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)  # type: ignore

            if receipt.status == 1:  # type: ignore[attr-defined]
                self.context.logger.info(f"Transaction {tx_hash} successful")
                return True
            self.context.logger.error(
                f"Transaction {tx_hash} failed (status: {receipt.status})"  # type: ignore[attr-defined]
            )
            return False

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error checking transaction status: {str(e)}")
            return False

    def _get_nonce_and_gas_web3(
        self, address: str, chain: str
    ) -> Tuple[Optional[int], Optional[int]]:
        """Get nonce and gas price using Web3."""
        try:
            w3 = self._get_web3_instance(chain)
            if not w3:
                return None, None

            nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(address))
            gas_price = w3.eth.gas_price

            return nonce, gas_price

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error getting nonce/gas: {str(e)}")
            return None, None

    def _estimate_gas(
        self,
        tx_request: Dict,
        eoa_address: str,
        chain: str,
    ) -> Optional[int]:
        """Estimate gas for a transaction"""
        try:
            w3 = self._get_web3_instance(chain)
            if not w3:
                self.context.logger.error(
                    "Failed to get Web3 instance for gas estimation"
                )
                return False

            tx_value = (
                int(tx_request["value"], 16)
                if isinstance(tx_request["value"], str)
                else tx_request["value"]
            )

            # Prepare transaction data for gas estimation
            tx_data_for_estimation = {
                "to": Web3.to_checksum_address(tx_request["to"]),
                "data": tx_request["data"],
                "value": tx_value,
                "from": Web3.to_checksum_address(eoa_address),
            }
            # Try to estimate gas using Web3
            estimated_gas = w3.eth.estimate_gas(tx_data_for_estimation)  # type: ignore
            # Add 20% buffer to estimated gas
            tx_gas = int(estimated_gas * 1.2)
            self.context.logger.info(
                f"Estimated gas: {estimated_gas}, with 20% buffer: {tx_gas}"
            )
            return tx_gas

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error in gas estimation: {str(e)}")
            return None

    def _ensure_sufficient_funds_for_x402_payments(
        self,
    ) -> (
        bool
    ):  # pylint: disable=too-many-locals,too-many-statements,too-many-return-statements
        """Ensure agent EOA has at sufficient funds for x402 requests payments"""
        self.context.logger.info("Checking USDC balance for x402 payments...")
        try:
            chain = BASE_CHAIN_NAME
            eoa_account = self._get_eoa_account()
            if not eoa_account:
                self.context.logger.error("Failed to get EOA account")
                return False
            eoa_address = eoa_account.address

            usdc_address = USDC_ADDRESS
            if not usdc_address:
                self.context.logger.error(f"No USDC address for {chain}")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            usdc_balance = self._check_usdc_balance(eoa_address, chain, usdc_address)

            if usdc_balance is None:
                self.context.logger.warning("Could not check USDC balance, skipping")
                self.shared_state.sufficient_funds_for_x402_payments = True
                return True

            threshold = self.params.x402_payment_requirements.get("threshold", 0)
            top_up = self.params.x402_payment_requirements.get("top_up", 0)

            if usdc_balance >= threshold:
                self.context.logger.info(
                    f"USDC balance sufficient: {usdc_balance} USDC (threshold: {threshold})"
                )
                self.shared_state.sufficient_funds_for_x402_payments = True
                return True

            self.context.logger.info(
                f"USDC balance ({usdc_balance}) < {threshold}, swapping ETH to {top_up} USDC..."
            )

            top_up_usdc_amount = str(top_up)
            quote = self._get_lifi_quote_sync(
                eoa_address, usdc_address, top_up_usdc_amount
            )
            if not quote:
                self.context.logger.error("Failed to get LiFi quote")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            tx_request: Optional[Dict] = quote.get("transactionRequest")
            if not tx_request:
                self.context.logger.error("No transactionRequest in quote")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            nonce, gas_price = self._get_nonce_and_gas_web3(eoa_address, chain)
            if nonce is None or gas_price is None:
                self.context.logger.error("Failed to get nonce or gas price")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            tx_value = (
                int(tx_request["value"], 16)
                if isinstance(tx_request["value"], str)
                else tx_request["value"]
            )
            tx_gas = self._estimate_gas(tx_request, eoa_address, chain)
            if tx_gas is None:
                self.context.logger.error("Failed to estimate gas for transaction")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            tx_data = {
                "to": Web3.to_checksum_address(tx_request["to"]),
                "data": tx_request["data"],
                "value": tx_value,
                "gas": tx_gas,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": BASE_CHAIN_ID,
            }

            self.context.logger.info(
                f"Signing and submitting tx: value={tx_data['value']}, gas={tx_data['gas']}, to={tx_data['to']}, data={tx_data['data']}..."
            )

            tx_hash = self._sign_and_submit_tx_web3(tx_data, chain, eoa_account)

            if not tx_hash:
                self.context.logger.error("Failed to submit transaction")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            self.context.logger.info(f"ETH to USDC swap submitted: {tx_hash}")

            # Check transaction status to ensure it was successful
            tx_successful = self._check_transaction_status(tx_hash, chain)

            if not tx_successful:
                self.context.logger.error(f"Transaction {tx_hash} failed or timed out")
                self.shared_state.sufficient_funds_for_x402_payments = False
                return False

            self.context.logger.info(
                f"ETH to USDC swap completed successfully: {tx_hash}"
            )
            self.shared_state.sufficient_funds_for_x402_payments = True
            return True

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error in _ensure_usdc_balance: {str(e)}")
            self.shared_state.sufficient_funds_for_x402_payments = False
            return False
