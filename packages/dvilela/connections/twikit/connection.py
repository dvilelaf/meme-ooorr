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

"""Twikit connection."""

import asyncio
import json
import time
from asyncio import Task
from concurrent.futures import Executor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

import twikit  # type: ignore
from aea.configurations.base import PublicId
from aea.connections.base import Connection, ConnectionStates
from aea.mail.base import Envelope
from aea.protocols.base import Address, Message
from aea.protocols.dialogue.base import Dialogue
from aea.protocols.dialogue.base import Dialogue as BaseDialogue

from packages.valory.protocols.srr.dialogues import SrrDialogue
from packages.valory.protocols.srr.dialogues import SrrDialogues as BaseSrrDialogues
from packages.valory.protocols.srr.message import SrrMessage


PUBLIC_ID = PublicId.from_str("dvilela/twikit:0.1.0")

MAX_POST_RETRIES = 5
MAX_GET_RETRIES = 10


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


class TwikitConnection(Connection):
    """Proxy to the functionality of the Twikit library."""

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
        self.username = self.configuration.config.get("twikit_username")
        self.email = self.configuration.config.get("twikit_email")
        self.password = self.configuration.config.get("twikit_password")
        cookies_str = self.configuration.config.get("twikit_cookies")
        self.cookies_path = Path(
            self.configuration.config.get(
                "twikit_cookies_path", "/tmp/twikit_cookies.json"  # nosec
            )
        )
        self.cookies = json.loads(cookies_str) if cookies_str else None
        self.disable_tweets = self.configuration.config.get("twikit_disable_tweets")
        self.client = twikit.Client(language="en-US")
        self.last_call = datetime.now(timezone.utc)

        self.dialogues = SrrDialogues(connection_id=PUBLIC_ID)
        self._response_envelopes: Optional[asyncio.Queue] = None
        self.loop_executor: Optional[Executor] = None
        self.task_to_request: Dict[asyncio.Future, Envelope] = {}

    @property
    def response_envelopes(self) -> asyncio.Queue:
        """Returns the response envelopes queue."""
        if self._response_envelopes is None:
            raise ValueError(
                "`TwikitConnection.response_envelopes` is not yet initialized. Is the connection setup?"
            )
        return self._response_envelopes

    async def connect(self) -> None:
        """Connect to a HTTP server."""
        self._response_envelopes = asyncio.Queue()
        await self.twikit_login()
        self.state = ConnectionStates.connected

    async def disconnect(self) -> None:
        """Disconnect from a HTTP server."""
        if self.is_disconnected:  # pragma: nocover
            return

        self.state = ConnectionStates.disconnecting

        for task in self.task_to_request.keys():
            if not task.cancelled():  # pragma: nocover
                task.cancel()
        self._response_envelopes = None

        self.state = ConnectionStates.disconnected

    def run_async(
        self, func: Callable, *args: Any, timeout: Optional[float] = None
    ) -> Task:
        """Run a function asynchronously by using threads."""
        operation = self.loop.run_in_executor(
            self.loop_executor,
            func,
            *args,
        )
        timely_operation = asyncio.wait_for(operation, timeout=timeout)
        task = self.loop.create_task(timely_operation)
        return task

    async def send(self, envelope: Envelope) -> None:
        """Send an envelope."""
        task = self._handle_envelope(envelope)
        task.add_done_callback(self._handle_done_task)
        self.task_to_request[task] = envelope

    def _handle_envelope(self, envelope: Envelope) -> Task:
        """Handle incoming envelopes by dispatching background tasks."""
        message = cast(SrrMessage, envelope.message)
        handler = getattr(self, "_get_response")
        dialogue = self.dialogues.update(message)
        task = self.run_async(handler, message, dialogue)
        return task

    def _handle_done_task(self, task: asyncio.Future) -> None:
        """
        Process a done receiving task.

        :param task: the done task.
        """
        request = self.task_to_request.pop(task)
        response_message: Optional[Message] = task.result()

        response_envelope = None
        if response_message is not None:
            response_envelope = Envelope(
                to=request.sender,
                sender=request.to,
                message=response_message,
                context=request.context,
            )

        # not handling `asyncio.QueueFull` exception, because the maxsize we defined for the Queue is infinite
        self.response_envelopes.put_nowait(response_envelope)

    async def receive(
        self, *args: Any, **kwargs: Any
    ) -> Optional[Union["Envelope", None]]:
        """
        Receive an envelope.

        :param args: arguments
        :param kwargs: keyword arguments
        :return: the envelope received, or None.
        """
        return await self.response_envelopes.get()

    async def _get_response(
        self, srr_message: SrrMessage, dialogue: BaseDialogue
    ) -> SrrMessage:
        """Get response from Genai."""

        if srr_message.performative != SrrMessage.Performative.REQUEST:
            self.logger.error(
                f"Performative `{srr_message.performative.value}` is not supported."
            )
            return

        payload = json.loads(srr_message.payload)

        REQUIRED_PROPERTIES = ["method", "kwargs"]
        AVAILABLE_METHODS = ["search", "post", "get_user_tweets"]

        if not all(i in payload for i in REQUIRED_PROPERTIES):
            return {
                "error": f"Some parameter is missing from the request data: required={REQUIRED_PROPERTIES}, got={list(payload.keys())}"
            }, True

        method_name = payload.get("method")
        if method_name not in AVAILABLE_METHODS:
            return {
                "error": f"Method {method_name} is not in the list of available methods {AVAILABLE_METHODS}"
            }, True

        method = getattr(self, method_name)

        # Avoid calling more than 1 time per second
        while (datetime.now(timezone.utc) - self.last_call).total_seconds() < 1:
            time.sleep(1)

        self.logger.info(f"Calling twikit: {payload}")

        retries = 0
        while retries < MAX_POST_RETRIES:
            try:
                response = await method(**payload.get("kwargs", {}))
                self.logger.info(f"Twikit response: {response}")
                response_message = cast(
                    SrrMessage,
                    dialogue.reply(  # type: ignore
                        performative=SrrMessage.Performative.RESPONSE,
                        target_message=srr_message,
                        payload=json.dumps({"response": response}),
                        error=False,
                    ),
                )
                return response_message

            except KeyError as e:
                self.logger.error(f"Exception while calling Twikit:\n{e}. Retrying...")
                retries += 1
                time.sleep(1)
                continue

            except Exception as e:
                response_message = cast(
                    SrrMessage,
                    dialogue.reply(  # type: ignore
                        performative=SrrMessage.Performative.RESPONSE,
                        target_message=srr_message,
                        payload=json.dumps(
                            {"error": f"Exception while calling Twikit:\n{e}"}
                        ),
                        error=True,
                    ),
                )
                return response_message

        response_message = cast(
            SrrMessage,
            dialogue.reply(  # type: ignore
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps(
                    {"error": "Error calling Twikit. Max amount of retries reached."}
                ),
                error=True,
            ),
        )
        return response_message

    async def twikit_login(self) -> None:
        """Login into Twitter"""
        if not self.cookies and self.cookies_path.exists():
            self.logger.info(f"Loading Twitter cookies from {self.cookies_path}")
            with open(self.cookies_path, "r", encoding="utf-8") as cookies_file:
                self.cookies = json.load(cookies_file)

        if self.cookies:
            self.logger.info("Set cookies")
            self.client.set_cookies(self.cookies)
        else:
            self.logger.info("Logging into Twitter with username and password")
            await self.client.login(
                auth_info_1=self.username,
                auth_info_2=self.email,
                password=self.password,
            )

        if not self.cookies_path.parent.exists():
            self.cookies_path.parent.mkdir(parents=True)

        self.client.save_cookies(self.cookies_path)
        self.logged_in = True

    async def search(
        self, query: str, product: str = "Top", count: int = 10
    ) -> List[Dict]:
        """Search tweets"""
        tweets = await self.client.search_tweet(
            query=query, product=product, count=count
        )
        return [tweet_to_json(t) for t in tweets]

    async def post(self, tweets: List[Dict]) -> List[Optional[str]]:
        """Post a thread"""

        if self.disable_tweets:
            self.logger.info("Twitting is disabled. Skipping.")
            return ["0"] * len(tweets)

        tweet_ids: List[Optional[str]] = []
        is_first_tweet = True

        # Iterate the thread
        for tweet_kwargs in tweets:
            if not is_first_tweet:
                tweet_kwargs["reply_to"] = tweet_ids[-1]

            tweet_id = await self.post_tweet(**tweet_kwargs)
            tweet_ids.append(tweet_id)
            is_first_tweet = False

            # Stop posting if any tweet fails
            if tweet_id is None:
                break

        # If any tweet failed to be created, remove all the thread
        if None in tweet_ids:
            for tweet_id in tweet_ids:
                # Skip tweets that failed
                if not tweet_id:
                    continue
                await self.delete_tweet(tweet_id)

            return [None] * len(tweet_ids)

        return tweet_ids

    async def post_tweet(self, **kwargs: Any) -> Optional[str]:
        """Post a single tweet"""
        tweet_id = None

        # Post the tweet
        retries = 0
        while retries < MAX_POST_RETRIES:
            try:
                self.logger.info(f"Posting: {kwargs}")
                result = await self.client.create_tweet(**kwargs)
                tweet_id = result.id
                break
            except Exception as e:
                self.logger.error(f"Failed to create the tweet: {e}. Retrying...")
                retries += 1

        # Verify that the tweet exists
        retries = 0
        while retries < MAX_GET_RETRIES:
            try:
                await self.client.get_tweet_by_id(tweet_id)
                return tweet_id
            except twikit.errors.TweetNotAvailable:
                self.logger.error("Failed to verify the tweet. Retrying...")
                retries += 1
                continue

        return None

    async def delete_tweet(self, tweet_id: str) -> None:
        """Delete a tweet"""
        # Delete the tweet
        retries = 0
        while retries < MAX_POST_RETRIES:
            try:
                self.logger.info(f"Deleting tweet {tweet_id}")
                await self.client.delete_tweet(tweet_id)
                break
            except Exception as e:
                self.logger.error(f"Failed to delete the tweet: {e}. Retrying...")
                retries += 1

    async def get_user_tweets(
        self, twitter_handle: str, tweet_type: str = "Tweets", count: int = 1
    ) -> List[Dict]:
        """Get user tweets"""

        user = await self.client.get_user_by_screen_name(twitter_handle)
        tweets = await self.client.get_user_tweets(
            user_id=user.id, tweet_type=tweet_type, count=count
        )
        return [tweet_to_json(t) for t in tweets]


def tweet_to_json(tweet: Any) -> Dict:
    """Tweet to json"""
    return {
        "id": tweet.id,
        "user_name": tweet.user.name,
        "text": tweet.text,
        "created_at": tweet.created_at,
        "view_count": tweet.view_count,
        "retweet_count": tweet.retweet_count,
        "quote_count": tweet.quote_count,
        "view_count_state": tweet.view_count_state,
    }
