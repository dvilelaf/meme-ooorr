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

"""Tweepy wrapper."""

import logging
import re
from typing import Dict, List, Optional

import tweepy  # type: ignore[import]


DEFAULT_LOGGER = logging.getLogger(__name__)


def is_twitter_id(twitter_id: str) -> bool:
    """
    Check if a string is a valid Twitter ID.

    Args:
        twitter_id (str): The string to check.

    Returns:
        bool: True if the string is a valid Twitter ID, False otherwise.
    """
    return bool(re.match(r"^\d{1,20}$", twitter_id))


class Twitter:
    """A class to interact with Twitter API using Tweepy."""

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        bearer_token: str,
        logger: Optional[logging.Logger] = None,
    ):
        """Constructor"""
        self.oauth2_bearer_auth = tweepy.OAuth2BearerHandler(bearer_token)
        self.oauth2_app_auth = tweepy.OAuth2AppHandler(consumer_key, consumer_secret)
        self.oauth1_user_auth = tweepy.OAuth1UserHandler(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )

        self.api = tweepy.API(auth=self.oauth1_user_auth)

        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        self.logger = logger if logger else DEFAULT_LOGGER

    def post_tweet(
        self,
        text: str,
        image_paths: Optional[List[str]] = None,
        in_reply_to_tweet_id: Optional[int] = None,
        quote_tweet_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Posts a new tweet with optional media.

        Args:
            text (str): The content of the tweet.
            media_ids (list of int, optional): A list of media IDs to attach to the tweet. Defaults to None.
        """
        try:
            tweet = self.client.create_tweet(
                text=text,
                media_ids=(
                    [
                        self.api.media_upload(filename=image_path).media_id
                        for image_path in image_paths
                    ]
                    if image_paths
                    else None
                ),
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                quote_tweet_id=quote_tweet_id,
            )
            return tweet.data["id"]
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method post_tweet: {type(e).__name__} - {e}"
            )
            raise

    def delete_tweet(self, tweet_id: str) -> bool:
        """Deletes a specific tweet."""
        try:
            self.client.delete_tweet(tweet_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method delete_tweet: {type(e).__name__} - {e}"
            )
            raise

    def like_tweet(self, tweet_id: str) -> bool:
        """Likes a specific tweet."""
        try:
            self.client.like(tweet_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method like_tweet: {type(e).__name__} - {e}"
            )
            raise

    def unlike_tweet(self, tweet_id: str) -> bool:
        """Unlikes a specific tweet."""
        try:
            self.client.unlike(tweet_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method unlike_tweet: {type(e).__name__} - {e}"
            )
            raise

    def retweet(self, tweet_id: str) -> bool:
        """Retweets a specific tweet."""
        try:
            self.client.retweet(tweet_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method retweet: {type(e).__name__} - {e}"
            )
            raise

    def unretweet(self, tweet_id: str) -> bool:
        """Unretweets a specific tweet."""
        try:
            self.client.unretweet(tweet_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method unretweet: {type(e).__name__} - {e}"
            )
            raise

    def follow_by_id(self, user_id: str) -> bool:
        """Follow a specific user."""
        try:
            self.client.follow(user_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method follow_by_id: {type(e).__name__} - {e}"
            )
            raise

    def follow_by_username(self, username: str) -> bool:
        """Follow a specific user by username."""
        user_id = self.get_user_id(username=username)

        if not user_id:
            self.logger.error(
                f"Could not follow user by username {username} because their ID could not be retrieved (get_user_id failed)."
            )
            return False

        return self.follow_by_id(user_id)

    def unfollow_by_id(self, user_id: str) -> bool:
        """Unfollow a specific user."""
        try:
            self.client.unfollow(user_id)
            return True
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method unfollow_by_id: {type(e).__name__} - {e}"
            )
            raise

    def get_user_id(self, username: str) -> Optional[str]:
        """Get a user id."""
        try:
            user = self.client.get_user(username=username)
            return user.data.id
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method get_user_id: {type(e).__name__} - {e}"
            )
            raise

    def get_me(self) -> Optional[Dict]:
        """Get my user."""
        try:
            result = self.client.get_me()
            return {
                "user_id": result.data.id,
                "username": result.data.username,
                "display_name": result.data.name,
            }
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method get_me: {type(e).__name__} - {e}"
            )
            raise

    def get_follower_ids(self, user: str) -> Optional[List[str]]:
        """Get a list of follower ids."""

        user_id = user if is_twitter_id(user) else self.get_user_id(user)

        if not user_id:
            self.logger.error(
                f"Could not get follower IDs for {user} because their ID could not be retrieved (get_user_id failed)."
            )
            return None
        try:
            result = self.api.get_follower_ids(user_id=user_id)
            return result
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method get_follower_ids: {type(e).__name__} - {e}"
            )
            raise

    def get_all_user_tweets(
        self,
        user_id: str,
        max_results: int = 100,
        tweet_fields: Optional[List[str]] = None,
    ) -> List:
        """Get a user's tweets."""
        try:
            paginator = tweepy.Paginator(
                self.client.get_users_tweets,
                user_id,
                max_results=max_results,
                tweet_fields=tweet_fields,
            )
            all_tweets = []
            for response in paginator:
                if response.data:
                    all_tweets.extend(response.data)

            return all_tweets
        except tweepy.errors.TweepyException as e:
            self.logger.error(
                f"TweepyException in method get_user_tweets_with_public_metrics: {type(e).__name__} - {e}"
            )
            raise
