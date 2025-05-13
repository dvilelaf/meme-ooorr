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

from typing import Dict, List, Optional

import tweepy  # type: ignore[import]


class Twitter:
    """A class to interact with Twitter API using Tweepy."""

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        bearer_token: str,
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

    def post_tweet(
        self,
        text: str,
        image_paths: Optional[List[str]] = None,
        in_reply_to_tweet_id: Optional[int] = None,
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
                media_ids=[
                    self.api.media_upload(filename=image_path).media_id
                    for image_path in image_paths
                ]
                if image_paths
                else None,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
            )
            return tweet.data["id"]
        except tweepy.TweepyException as e:
            print(e)
            return None

    def delete_tweet(self, tweet_id: str) -> bool:
        """
        Deletes a specific tweet.

        Args:
            tweet_id (int): The ID of the tweet to delete.
        """
        try:
            self.client.delete_tweet(tweet_id)
            return True
        except tweepy.TweepyException:
            return False

    def like_tweet(self, tweet_id: str) -> bool:
        """
        Likes a specific tweet.

        Args:
            tweet_id (int): The ID of the tweet to like.
        """
        try:
            self.client.like(tweet_id)
            return True
        except tweepy.TweepyException:
            return False

    def unlike_tweet(self, tweet_id: str) -> bool:
        """
        Unlikes a specific tweet.

        Args:
            tweet_id (int): The ID of the tweet to like.
        """
        try:
            self.client.unlike(tweet_id)
            return True
        except tweepy.TweepyException:
            return False

    def retweet(self, tweet_id: str) -> bool:
        """
        Retweets a specific tweet.

        Args:
            tweet_id (int): The ID of the tweet to retweet.
        """
        try:
            self.client.retweet(tweet_id)
            return True
        except tweepy.TweepyException:
            return False

    def unretweet(self, tweet_id: str) -> bool:
        """
        Unlikes a specific tweet.

        Args:
            tweet_id (int): The ID of the tweet to unretweet.
        """
        try:
            self.client.unretweet(tweet_id)
            return True
        except tweepy.TweepyException:
            return False

    def follow_by_id(self, user_id: str) -> bool:
        """
        Follow a specific user.

        Args:
            user_id (int): The ID of the user to follow.
        """
        try:
            self.client.follow(user_id)
            return True
        except tweepy.TweepyException:
            return False

    def follow_by_username(self, username: str) -> bool:
        """
        Follow a specific user.

        Args:user_name
            user_id (int): The ID of the user to follow.
        """
        try:
            user_id = self.get_user_id(username=username)
            if not user_id:
                return False
            self.follow_by_id(user_id)
            return True
        except tweepy.TweepyException:
            return False

    def unfollow_by_id(self, user_id: str) -> bool:
        """
        Unfollow a specific tweet.

        Args:
            user_id (int): The ID of the user to unfollow.
        """
        try:
            self.client.unfollow(user_id)
            return True
        except tweepy.TweepyException:
            return False

    def get_user_id(self, username: str) -> Optional[str]:
        """
        Get a user id.

        Args:
            username (str): The username of the user to retrieve.
        """
        try:
            user = self.client.get_user(username=username)
            return user.data.id
        except tweepy.TweepyException:
            return None

    def get_me(self) -> Optional[Dict]:
        """
        Get my user.

        Args:
            user_id (int): The ID of the user to unfollow.
        """
        try:
            result = self.client.get_me()
            return {"user_id": result.data.id, "username": result.data.username}
        except tweepy.TweepyException:
            return None
