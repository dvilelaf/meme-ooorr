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

"""Tweepy connection."""

import json
import time
from typing import Any, Dict, List, Optional, cast

from aea.configurations.base import PublicId
from aea.connections.base import BaseSyncConnection
from aea.mail.base import Envelope
from aea.protocols.base import Address, Message
from aea.protocols.dialogue.base import Dialogue

from packages.dvilela.connections.tweepy.tweepy_wrapper import Twitter
from packages.valory.protocols.srr.dialogues import SrrDialogue
from packages.valory.protocols.srr.dialogues import SrrDialogues as BaseSrrDialogues
from packages.valory.protocols.srr.message import SrrMessage


PUBLIC_ID = PublicId.from_str("dvilela/tweepy:0.1.0")

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


class TweepyConnection(BaseSyncConnection):
    """Proxy to the functionality of the Tweepy library."""

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
        self.tweepy_consumer_api_key: str = self.configuration.config.get(
            "tweepy_consumer_api_key", ""
        )
        self.tweepy_consumer_api_key_secret: str = self.configuration.config.get(
            "tweepy_consumer_api_key_secret", ""
        )
        self.tweepy_bearer_token: str = self.configuration.config.get(
            "tweepy_bearer_token", ""
        )
        self.tweepy_access_token: str = self.configuration.config.get(
            "tweepy_access_token", ""
        )
        self.tweepy_access_token_secret: str = self.configuration.config.get(
            "tweepy_access_token_secret", ""
        )

        self.twitter = Twitter(
            self.tweepy_consumer_api_key,
            self.tweepy_consumer_api_key_secret,
            self.tweepy_access_token,
            self.tweepy_access_token_secret,
            self.tweepy_bearer_token,
        )

        self.dialogues = SrrDialogues(connection_id=PUBLIC_ID)

    def main(self) -> None:
        """
        Run synchronous code in background.

        SyncConnection `main()` usage:
        The idea of the `main` method in the sync connection
        is to provide for a way to actively generate messages by the connection via the `put_envelope` method.

        A simple example is the generation of a message every second:
        ```
        while self.is_connected:
            envelope = make_envelope_for_current_time()
            self.put_enevelope(envelope)
            time.sleep(1)
        ```
        In this case, the connection will generate a message every second
        regardless of envelopes sent to the connection by the agent.
        For instance, this way one can implement periodically polling some internet resources
        and generate envelopes for the agent if some updates are available.
        Another example is the case where there is some framework that runs blocking
        code and provides a callback on some internal event.
        This blocking code can be executed in the main function and new envelops
        can be created in the event callback.
        """

    def on_connect(self) -> None:
        """Set up the connection"""

    def on_disconnect(self) -> None:
        """
        Tear down the connection.

        Connection status set automatically.
        """

    def on_send(self, envelope: Envelope) -> None:
        """
        Send an envelope.

        :param envelope: the envelope to send.
        """
        srr_message = cast(SrrMessage, envelope.message)

        dialogue = self.dialogues.update(srr_message)

        if srr_message.performative != SrrMessage.Performative.REQUEST:
            self.logger.error(
                f"Performative `{srr_message.performative.value}` is not supported."
            )
            return

        response = self._get_response(
            payload=json.loads(srr_message.payload),
        )

        response_message = cast(
            SrrMessage,
            dialogue.reply(  # type: ignore
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps({"response": response}),
                error="error" in response,
            ),
        )

        response_envelope = Envelope(
            to=envelope.sender,
            sender=envelope.to,
            message=response_message,
            context=envelope.context,
        )

        self.put_envelope(response_envelope)

    def _get_response(self, payload: dict) -> Dict:
        """Get response from Tweepy."""

        REQUIRED_PROPERTIES = ["method", "kwargs"]
        AVAILABLE_METHODS = [
            "post",
            "like_tweet",
            "unlike_tweet",
            "retweet",
            "unretweet",
            "follow_by_id",
            "follow_by_username",
            "unfollow_by_id",
            "get_me",
        ]

        if not all(i in payload for i in REQUIRED_PROPERTIES):
            return {
                "error": f"Some parameter is missing from the request data: required={REQUIRED_PROPERTIES}, got={list(payload.keys())}"
            }

        method_name = payload.get("method")
        if method_name not in AVAILABLE_METHODS:
            return {
                "error": f"Method {method_name} is not in the list of available methods {AVAILABLE_METHODS}"
            }

        method = getattr(self, method_name)

        self.logger.info(f"Calling Tweepy: {payload}")

        try:
            response = method(**payload.get("kwargs", {}))
            self.logger.info(f"Tweepy response: {response}")
            return response

        except Exception as e:
            return {"error": e}

    def post(self, tweets: List[Dict]) -> List[Optional[str]]:
        """Post a tweet or a thread."""
        tweet_ids: List[Optional[str]] = []
        is_first_tweet = True

        # Iterate the thread
        for tweet_kwargs in tweets:
            if not is_first_tweet:
                tweet_kwargs["reply_to"] = tweet_ids[-1]

            tweet_id = self.twitter.post_tweet(
                text=tweet_kwargs["text"],
                image_paths=tweet_kwargs.get("image_paths", None),
                in_reply_to_tweet_id=tweet_kwargs.get("reply_to", None),
            )
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

                self.delete_tweet(tweet_id)

            return [None] * len(tweet_ids)

        return tweet_ids

    def delete_tweet(self, tweet_id: str) -> None:
        """Delete a tweet"""
        # Delete the tweet
        retries = 0
        while retries < MAX_POST_RETRIES:
            self.logger.info(f"Deleting tweet {tweet_id}")
            success = self.twitter.delete_tweet(tweet_id)
            if success:
                break
            else:
                self.logger.error("Failed to delete the tweet. Retrying...")
                retries += 1
                time.sleep(3)

    def like_tweet(self, tweet_id: str) -> Dict:
        """Like a tweet"""
        success = self.twitter.like_tweet(tweet_id)
        return {"success": success}

    def unlike_tweet(self, tweet_id: str) -> Dict:
        """Unlike a tweet"""
        success = self.twitter.unlike_tweet(tweet_id)
        return {"success": success}

    def retweet(self, tweet_id: str) -> Dict:
        """Retweet a tweet"""
        success = self.twitter.retweet(tweet_id)
        return {"success": success}

    def unretweet(self, tweet_id: str) -> Dict:
        """Unretweet a tweet"""
        success = self.twitter.unretweet(tweet_id)
        return {"success": success}

    def follow_by_id(self, user_id: str) -> Dict:
        """Follow a user"""
        success = self.twitter.follow_by_id(user_id)
        return {"success": success}

    def follow_by_username(self, username: str) -> Dict:
        """Follow a user"""
        success = self.twitter.follow_by_username(username)
        return {"success": success}

    def unfollow_by_id(self, user_id: str) -> Dict:
        """Unfollow a user"""
        success = self.twitter.unfollow_by_id(user_id)
        return {"success": success}

    def get_me(self) -> Optional[Dict]:
        """Get own user information"""
        return self.twitter.get_me()
