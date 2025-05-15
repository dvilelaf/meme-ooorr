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
import os
import secrets
import time
from asyncio import Task
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

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
HTTP_OK = 200


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
        self.cookies = self.configuration.config.get("twikit_cookies")
        self.cookies_path = (  # nosec
            Path(self.configuration.config.get("store_path", "/tmp"))  # type: ignore
            / self.username
            / "twikit_cookies.json"
        )
        self.disable_tweets = self.configuration.config.get("twikit_disable_tweets")
        self.skip_connection = self.configuration.config.get("twikit_skip_connection")
        if not self.skip_connection:
            self.client = twikit.Client(language="en-US")
        else:
            self.logger.info("Twikit connecion is disabled.")
            self.client = None
        self.last_call = datetime.now(timezone.utc)

        self.dialogues = SrrDialogues(connection_id=PUBLIC_ID)
        self._response_envelopes: Optional[asyncio.Queue] = None
        self.task_to_request: Dict[asyncio.Future, Envelope] = {}
        self.logged_in = False

        # Write cookies to file if there is no cookies file
        if not self.cookies_path.exists() and self.cookies:
            self.logger.info(f"Removing previous cookie file at {self.cookies_path}")
            self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cookies_path, "w", encoding="utf-8") as cookies_file:
                json.dump(json.loads(self.cookies), cookies_file, indent=4)
                self.logger.info(f"Wrote cookies from config to {self.cookies_path}")
        else:
            self.logger.info(f"Using cookies from {self.cookies_path}")

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
        if not self.skip_connection:
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

    async def send(self, envelope: Envelope) -> None:
        """Send an envelope."""
        task = self._handle_envelope(envelope)
        task.add_done_callback(self._handle_done_task)
        self.task_to_request[task] = envelope

    def _handle_envelope(self, envelope: Envelope) -> Task:
        """Handle incoming envelopes by dispatching background tasks."""
        message = cast(SrrMessage, envelope.message)
        dialogue = self.dialogues.update(message)
        task = self.loop.create_task(self._get_response(message, dialogue))
        return task

    def prepare_error_message(
        self, srr_message: SrrMessage, dialogue: Optional[BaseDialogue], error: str
    ) -> SrrMessage:
        """Prepare error message"""
        response_message = cast(
            SrrMessage,
            dialogue.reply(  # type: ignore
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps({"error": error}),
                error=True,
            ),
        )
        return response_message

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

    async def _get_response(
        self, srr_message: SrrMessage, dialogue: Optional[BaseDialogue]
    ) -> SrrMessage:
        """Get response from Genai."""

        if srr_message.performative != SrrMessage.Performative.REQUEST:
            return self.prepare_error_message(
                srr_message,
                dialogue,
                f"Performative `{srr_message.performative.value}` is not supported.",
            )

        if self.skip_connection:
            return self.prepare_error_message(
                srr_message,
                dialogue,
                "Connection is disabled. Set TWIKIT_SKIP_CONNECTION=false to enable it.",
            )

        payload = json.loads(srr_message.payload)

        REQUIRED_PROPERTIES = ["method", "kwargs"]
        AVAILABLE_METHODS = [
            "search",
            "post",
            "get_user_tweets",
            "like_tweet",
            "retweet",
            "follow_user",
            "filter_suspended_users",
            "get_user_by_screen_name",
            "get_twitter_user_id",
            "upload_media",
        ]

        if not all(i in payload for i in REQUIRED_PROPERTIES):
            return self.prepare_error_message(
                srr_message,
                dialogue,
                f"Some parameter is missing from the request data: required={REQUIRED_PROPERTIES}, got={list(payload.keys())}",
            )

        method_name = payload.get("method")
        if method_name not in AVAILABLE_METHODS:
            return self.prepare_error_message(
                srr_message,
                dialogue,
                f"Method {method_name} is not in the list of available methods {AVAILABLE_METHODS}",
            )

        method = getattr(self, method_name)

        # Avoid calling more than 1 time per 5 seconds
        while (datetime.now(timezone.utc) - self.last_call).total_seconds() < 5:
            time.sleep(1)

        self.logger.info(f"Calling twikit: {payload}")

        if not self.logged_in:
            return self.prepare_error_message(
                srr_message,
                dialogue,
                "Twitter account is not logged in.",
            )

        try:
            # Add random delay
            delay = secrets.randbelow(5)
            time.sleep(delay)

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

        except (
            twikit.errors.AccountLocked,
            twikit.errors.AccountSuspended,
            twikit.errors.Unauthorized,
        ):
            return self.prepare_error_message(
                srr_message,
                dialogue,
                "Twitter account is locked or suspended.",
            )

        except Exception as e:
            return self.prepare_error_message(
                srr_message, dialogue, f"Exception while calling Twikit:\n{e}"
            )

    async def validate_login(self) -> bool:
        """Validate login"""
        valid_login = False
        retries = 0
        while retries < 3:
            try:
                # Check we can recover one example user
                user = await self.client.get_user_by_screen_name("autonolas")
                valid_login = user.id == "1450081635559428107"
                if valid_login:
                    self.logger.info(
                        f"Cookies have succesfully been validated for user {self.username}"
                    )
                    break
                raise ValueError("Could not test the cookies")
            except Exception as e:
                self.logger.error(
                    f"Could not validate the cookies [{retries} / 3 retries]: {e}"
                )
                retries += 1
                time.sleep(3)
                continue
        if not valid_login:
            self.logger.error("Could not validate the cookies")
        return valid_login

    async def twikit_login(self) -> None:
        """Login into Twitter"""

        try:
            # Try to login via cookies
            await self.client.login(
                auth_info_1=self.username,
                auth_info_2=self.email,
                password=self.password,
                cookies_file=str(self.cookies_path),
            )

            valid_login = await self.validate_login()
            if valid_login:
                self.logged_in = True
            else:
                raise ValueError("Could not validate the cookies")

        except (twikit.errors.Unauthorized, ValueError):
            self.logger.error("Twitter cookies are not valid. Regenerating...")
            self.cookies_path.unlink()

            try:
                await self.client.login(
                    auth_info_1=self.username,
                    auth_info_2=self.email,
                    password=self.password,
                    cookies_file=str(self.cookies_path),
                )

                valid_login = await self.validate_login()
                if valid_login:
                    self.logged_in = True

            except Exception as e:
                self.logger.error(f"Exception while trying to login via password: {e}")

        except twikit.errors.AccountLocked:
            self.logger.error("Twitter account is locked")

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

                # Add random delay
                delay = secrets.randbelow(5)
                time.sleep(delay)
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
                if tweet_id is not None:
                    self.logger.info(f"Tweet created with tweet ID: {tweet_id}")
                    break
            except Exception as e:
                self.logger.error(f"Failed to create the tweet: {e}. Retrying...")
            finally:
                retries += 1

        if not tweet_id:
            return None

        # Verify that the tweet exists
        retries = 0
        while retries < MAX_GET_RETRIES:
            try:
                await self.client.get_tweet_by_id(tweet_id)
                return tweet_id
            except twikit.errors.TweetNotAvailable:
                self.logger.error("Failed to verify the tweet. Retrying...")
                time.sleep(3)
            finally:
                retries += 1

        if tweet_id is None:
            self.logger.error("Failed to create the tweet after maximum retries.")
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
                time.sleep(3)

    async def get_user_tweets(
        self, twitter_handle: str, tweet_type: str = "Tweets", count: int = 1
    ) -> List[Dict]:
        """Get user tweets"""

        user = await self.client.get_user_by_screen_name(twitter_handle)
        time.sleep(1)
        tweets = await self.client.get_user_tweets(
            user_id=user.id, tweet_type=tweet_type, count=count
        )
        return [tweet_to_json(t, user.id) for t in tweets]

    async def like_tweet(self, tweet_id: str) -> Dict:
        """Like a tweet"""
        try:
            await self.client.favorite_tweet(tweet_id)
            self.logger.info(f"Successfully liked tweet {tweet_id}")
            return {"success": True}
        except twikit.errors.TwitterException as e:
            self.logger.error(f"Twikit API error liking tweet {tweet_id}: {e}")
            return {"success": False, "error": f"Twikit API error: {e}"}
        except Exception as e:
            self.logger.error(f"Unexpected error liking tweet {tweet_id}: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def follow_user(self, user_id: str) -> Dict:
        """Follow user"""
        try:
            await self.client.follow_user(user_id)
            self.logger.info(f"Successfully followed user {user_id}")
            return {"success": True}
        except twikit.errors.TwitterException as e:
            self.logger.error(f"Twikit API error following user {user_id}: {e}")
            return {"success": False, "error": f"Twikit API error: {e}"}
        except Exception as e:
            self.logger.error(f"Unexpected error following user {user_id}: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def retweet(self, tweet_id: str) -> Dict:
        """Retweet"""
        try:
            await self.client.retweet(tweet_id)
            self.logger.info(f"Successfully retweeted tweet {tweet_id}")
            return {"success": True}
        except twikit.errors.TwitterException as e:
            self.logger.error(f"Twikit API error retweeting tweet {tweet_id}: {e}")
            return {"success": False, "error": f"Twikit API error: {e}"}
        except Exception as e:
            self.logger.error(f"Unexpected error retweeting tweet {tweet_id}: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def filter_suspended_users(self, user_names: List[str]) -> List[str]:
        """Retweet"""
        not_suspendend_users = []
        for user_name in user_names:
            try:
                # Add random delay
                delay = secrets.randbelow(5)
                time.sleep(delay)
                await self.client.get_user_by_screen_name(user_name)
                not_suspendend_users.append(user_name)
            except twikit.errors.TwitterException:
                continue
            except Exception as e:
                self.logger.error(f"Error while checking user {user_name}: {e}")
                continue
        return not_suspendend_users

    async def get_user_by_screen_name(self, screen_name: str) -> Dict:
        """Get user by screen name"""
        user = await self.client.get_user_by_screen_name(screen_name=screen_name)
        return user_to_json(user)

    async def get_twitter_user_id(self) -> str:
        """Returns Twitter ID for the instance Twitter account."""

        with open(self.cookies_path, "r", encoding="utf-8") as cookies_file:
            cookies = json.load(cookies_file)

            twid = cookies.get("twid", "").strip('"')
            if not twid:
                raise ValueError("Twitter ID (twid) not found in cookies.")

            return twid

    async def upload_media(self, media_path: str) -> Optional[str]:
        """
        Upload media to Twitter.

        :param media_path: Path to the media file.
        :return: Media ID if successful, None otherwise.
        """
        media_id = None
        retries = 0

        while retries < MAX_POST_RETRIES:
            try:
                self.logger.info(f"Uploading media from path: {media_path}")

                # Make sure the media_path is a string, not a dictionary
                if isinstance(media_path, dict) and "latest_image_path" in media_path:
                    actual_path = media_path["latest_image_path"]
                    self.logger.info(f"Extracted path from dictionary: {actual_path}")
                    media_path = actual_path

                # Check if file exists
                if not os.path.exists(media_path):
                    raise FileNotFoundError(
                        f"Media file not found at path: {media_path}"
                    )

                # Upload media to Twitter
                result = await self.client.upload_media(
                    source=media_path, wait_for_completion=True
                )
                media_id = result

                if media_id is not None:
                    self.logger.info(f"Media uploaded with ID: {media_id}")
                    break
            except FileNotFoundError as e:
                self.logger.error(f"Media file not found: {e}")
                break  # No point retrying if the file doesn't exist
            except Exception as e:
                self.logger.error(f"Failed to upload media: {e}. Retrying...")
            finally:
                retries += 1
                if retries < MAX_POST_RETRIES:
                    # Add random delay between retries
                    delay = secrets.randbelow(5)
                    time.sleep(delay)

        return media_id


def tweet_to_json(tweet: Any, user_id: Optional[str] = None) -> Dict:
    """Tweet to json"""
    return {
        "id": tweet.id,
        "user_name": tweet.user.name,
        "user_id": user_id or tweet.user.id,
        "text": tweet.text,
        "created_at": tweet.created_at,
        "view_count": tweet.view_count,
        "retweet_count": tweet.retweet_count,
        "quote_count": tweet.quote_count,
        "view_count_state": tweet.view_count_state,
    }


def user_to_json(user: Any) -> Dict:
    """User to Json"""
    return {
        "id": user.id,
        "name": user.name,
        "screen_name": user.screen_name,
    }
