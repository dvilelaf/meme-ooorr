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
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Generator, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

import peewee
import yaml
from aea.configurations.data_types import PublicId
from aea.protocols.base import Message

from packages.dvilela.protocols.kv_store.message import KvStoreMessage
from packages.dvilela.skills.memeooorr_abci.dialogues import HttpDialogue, HttpDialogues
from packages.dvilela.skills.memeooorr_abci.models import SharedState
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


ABCIHandler = BaseABCIRoundHandler
SigningHandler = BaseSigningHandler
LedgerApiHandler = BaseLedgerApiHandler
ContractApiHandler = BaseContractApiHandler
TendermintHandler = BaseTendermintHandler
IpfsHandler = BaseIpfsHandler

AGENT_PROFILE_PATH = "agentsfun-ui-build"


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


class SrrHandler(AbstractResponseHandler):
    """A class for handling SRR messages."""

    SUPPORTED_PROTOCOL: Optional[PublicId] = SrrMessage.protocol_id
    allowed_response_performatives = frozenset(
        {
            SrrMessage.Performative.REQUEST,
            SrrMessage.Performative.RESPONSE,
        }
    )


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


OK_CODE = 200
NOT_FOUND_CODE = 404
BAD_REQUEST_CODE = 400
AVERAGE_PERIOD_SECONDS = 10


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

        config_uri_base_hostname = urlparse(
            self.context.params.service_endpoint
        ).hostname

        ip_regex = r"(\d{1,3}\.){3}\d{1,3}"

        # Route regexes
        hostname_regex = rf".*({config_uri_base_hostname}|{ip_regex}|localhost)(:\d+)?"
        self.handler_url_regex = (  # pylint: disable=attribute-defined-outside-init
            rf"{hostname_regex}\/.*"
        )
        health_url_regex = rf"{hostname_regex}\/healthcheck"
        agent_details_url_regex = rf"{hostname_regex}\/agent-info"
        x_activity_url_regex = rf"{hostname_regex}\/x-activity"
        meme_coins_url_regex = rf"{hostname_regex}\/memecoin-activity"
        media_url_regex = rf"{hostname_regex}\/media"
        static_files_regex = rf"{hostname_regex}\/(.*)"
        # Routes
        self.routes = {  # pylint: disable=attribute-defined-outside-init
            (HttpMethod.GET.value, HttpMethod.HEAD.value): [
                (health_url_regex, self._handle_get_health),
                (agent_details_url_regex, self._handle_get_agent_details),
                (x_activity_url_regex, self._handle_get_recent_x_activity),
                (meme_coins_url_regex, self._handle_get_meme_coins),
                (media_url_regex, self._handle_get_media),
                (static_files_regex, self._handle_get_static_file),
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
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
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
            body=b"",
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

    def _handle_get_agent_details(
        self, http_msg: HttpMessage, http_dialogue: HttpDialogue
    ) -> None:
        """Handle a Http request of verb GET."""

        agent_details = self.synchronized_data.agent_details
        self.context.logger.info(f"Agent details: {agent_details}")
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
            "media": [f"{ipfs_gateway_url}/{action_data.get('media_ipfs_hash', None)}"],
        }

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

        activities = []
        # Get the last action, or fewer if not that many exist
        for token_action in token_actions[-limit:]:
            token_address = token_action.get("token_address")
            tweet_id = token_action.get("tweet_id")
            activity = {
                "type": token_action.get("action"),
                "timestamp": token_action.get("timestamp"),
                "postId": tweet_id if tweet_id else None,
                "token": {
                    "address": token_address if token_address else None,
                    "nonce": token_action.get("token_nonce"),
                    "symbol": token_action.get("token_ticker"),
                },
            }
            activities.append(activity)
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
            post_id = media_path_to_tweet_id.get(path)

            if post_id:
                media_item["postId"] = post_id
                media_item["path"] = f"{ipfs_gateway_url}/{media_item.get('ipfs_hash')}"
                media_item.pop("hash", None)
                media_item.pop("media_path", None)
                media_item.pop("ipfs_hash", None)
                processed_media_list.append(media_item)

        media_list[:] = processed_media_list

        self._send_ok_response(http_msg, http_dialogue, media_list)  # type: ignore

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
