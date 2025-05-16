import json
import random
import secrets
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Set, Tuple, Type, Union, cast

from twitter_text import parse_tweet  # type: ignore

from packages.valory.protocols.srr.dialogues import SrrDialogue, SrrDialogues
from packages.valory.protocols.srr.message import SrrMessage

from packages.dvilela.connections.tweepy.connection import (
    PUBLIC_ID as TWEEPY_CONNECTION_PUBLIC_ID,
)

from packages.valory.skills.abstract_round_abci.base import AbstractRound

from packages.dvilela.skills.base_abci.behaviours import BaseSkillBehaviour


class BaseTweetBehaviour(BaseSkillBehaviour):  # pylint: disable=too-many-ancestors
    """BaseTweetBehaviour"""

    """
    This class will contain the common methods for the EngageTwitterBehaviour 
    """

    matching_round: Type[AbstractRound] = None  # type: ignore

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
        response = yield from self.do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        if method != "get_me":
            # Handle MirrorDB interaction if applicable
            yield from self._handle_mirrordb_interaction_post_tweepy(
                method, kwargs, response_json, mirror_db_config_data  # type: ignore
            )
        return response_json.get("response")

    # TODO: We need to implement the store_tweet method which will be used to store the tweet in the database (MirrorDB, KVStore, etc.)\
    # This depends on how the KV db interaction connection is implemented

    # def store_tweet(
    #     self, tweet: Union[dict, List[dict]]
    # ) -> Generator[None, None, bool]:
    #     """Store tweet"""
    #     tweets = yield from self.get_tweets_from_db()
    #     if isinstance(tweet, list):
    #         tweets.extend(tweet)
    #     else:
    #         tweets.append(tweet)
    #     yield from self._write_kv({"tweets": json.dumps(tweets)})
    #     return True

    def post_tweet(
        self, tweet: List[str], store: bool = True
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""
        self.context.logger.info(f"Posting tweet: {tweet}")

        # Post the tweet
        tweet_ids = yield from self._call_tweepy(
            method="post",
            tweets=[{"text": t} for t in tweet],
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting to Twitter.")
            return None

        latest_tweet = {
            "tweet_id": tweet_ids[0],
            "text": tweet,
            "timestamp": self.get_sync_timestamp(),
        }

        # Write latest tweet to the database
        if store:
            yield from self.store_tweet(latest_tweet)
            self.context.logger.info("Wrote latest tweet to db")

        return latest_tweet

    def respond_tweet(
        self,
        tweet_id: str,
        text: str,
        quote: bool = False,
        user_name: Optional[str] = None,
    ) -> Generator[None, None, bool]:
        """Like a tweet"""

        self.context.logger.info(f"Replying to tweet with ID: {tweet_id}")
        tweet = {"text": text}
        if quote:
            tweet["attachment_url"] = f"https://x.com/{user_name}/status/{tweet_id}"
        else:
            tweet["reply_to"] = tweet_id
        tweet_ids = yield from self._call_tweepy(
            method="post",
            tweets=[tweet],
        )
        return tweet_ids is not None and tweet_ids

    def like_tweet(self, tweet_id: str) -> Generator[None, None, bool]:
        """Like a tweet"""
        self.context.logger.info(f"Liking tweet with ID: {tweet_id}")
        try:
            response = yield from self._call_tweepy(
                method="like_tweet", tweet_id=tweet_id
            )
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for like_tweet ID {tweet_id} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error liking tweet with ID {tweet_id}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Exception liking tweet with ID {tweet_id}: {e}")
            return False

    def retweet(self, tweet_id: str) -> Generator[None, None, bool]:
        """Retweet"""
        self.context.logger.info(f"Retweeting tweet with ID: {tweet_id}")
        try:
            response = yield from self._call_tweepy(method="retweet", tweet_id=tweet_id)
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for retweet ID {tweet_id} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error retweeting tweet with ID {tweet_id}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception retweeting tweet with ID {tweet_id}: {e}"
            )
            return False

    def follow_user(self, user_name: str) -> Generator[None, None, bool]:
        """Follow user"""
        self.context.logger.info(f"Following user with user_name: {user_name}")
        try:
            response = yield from self._call_tweepy(
                method="follow_by_username", username=user_name
            )
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for follow_user user_name {user_name} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error Following user with user_name {user_name}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception following user with user_name {user_name}: {e}"
            )
            return False
