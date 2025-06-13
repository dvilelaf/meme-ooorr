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
import os
import traceback
from datetime import datetime
from typing import Generator, List, Optional, Type

import requests

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.payloads import MechPayload
from packages.dvilela.skills.memeooorr_abci.rounds import (
    FailedMechRequestRound,
    FailedMechResponseRound,
    PostMechResponseRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
)


class PostMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """PostMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = PostMechResponseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        mech_for_twitter = False
        failed_mech = False
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"Processing mech response: {self.synchronized_data.mech_responses}"
            )

            # Process response and fetch media using the helper method
            mech_for_twitter = yield from self._process_mech_response_and_fetch_media(
                self.synchronized_data.mech_responses
            )

            if mech_for_twitter:
                self.context.logger.info("Mech response processed successfully")
            else:
                failed_mech = True
                self.context.logger.error("Failed to process mech response")

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=mech_for_twitter,
                failed_mech=failed_mech,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _process_mech_response_and_fetch_media(
        self, mech_responses: List[MechInteractionResponse]
    ) -> Generator[None, None, bool]:
        """
        Process the mech response, fetch media (video or image) based on the format,

        and save media info. Returns True if media was successfully processed and saved, False otherwise.
        """
        if not mech_responses:
            self.context.logger.error("No mech responses found")
            return False

        response_data = mech_responses[0]
        if response_data.result is None:
            self.context.logger.error("Mech response result is None")
            return False  # Early return for None result

        # Handle JSON parsing separately and immediately
        try:
            result_json = json.loads(response_data.result)
        except json.JSONDecodeError as e:
            self.context.logger.error(
                f"Error decoding JSON from mech response result: {response_data.result} - {e}"
            )
            return False  # Fail fast on JSON decode error

        # Main fetch/save logic block
        video_hash = result_json.get("video")
        image_hash = result_json.get("image_hash")

        # Case 1: Video format (Attempt first if key exists)
        if video_hash:
            self.context.logger.info(f"Attempting video fetch for hash: {video_hash}")
            # _fetch_media_from_ipfs_hash handles its own network/IO errors and returns Optional[str]
            video_path = self._fetch_media_from_ipfs_hash(video_hash, "video", ".mp4")

            if video_path:  # Video fetch succeeded
                self.context.logger.info(
                    f"Video downloaded to: {video_path}. Saving metadata..."
                )
                # Attempt to save metadata. _save_media_info handles errors and returns True/False
                save_success = yield from self._save_media_info(video_path, "video")
                if save_success:
                    self.context.logger.info("Video metadata saved successfully.")
                    return True

            else:
                self.context.logger.warning(
                    f"Video fetch failed for hash: {video_hash}. Will check for image fallback."
                )
                # Proceed to image check

        # Case 2: Image hash format
        if image_hash:
            self.context.logger.info(f"Attempting image fetch for hash: {image_hash}")
            # _fetch_media_from_ipfs_hash handles its own network/IO errors and returns Optional[str]
            image_path = self._fetch_media_from_ipfs_hash(image_hash, "image", ".png")

            if image_path:  # Image fetch succeeded
                self.context.logger.info(
                    f"Image downloaded to: {image_path}. Saving metadata..."
                )
                # Attempt to save metadata. _save_media_info handles errors and returns True/False
                save_success = yield from self._save_media_info(image_path, "image")
                if save_success:
                    self.context.logger.info("Image metadata saved successfully.")
                    return True  # SUCCESS

        # If we reach here, neither video nor image processing succeeded.
        self.context.logger.warning(
            "Could not process mech response: No video/image successfully fetched and saved. Looked for keys 'video' and 'image_hash'."
        )
        return False  # FAILURE

    def _save_media_info(
        self, media_path: str, media_type: str
    ) -> Generator[None, None, bool]:
        """Helper method to save media information to the key-value store. Returns True on success, False on failure."""
        media_info = {"path": media_path, "type": media_type}
        try:
            yield from self._store_media_info_list(media_info)

            # this is for backwards compatibility as we are using this in many places inside twitter.py
            yield from self._write_kv({"latest_media_info": json.dumps(media_info)})
            self.context.logger.info(
                f"Stored media info ({media_type}) via _write_kv: {media_info}"
            )
            return True  # Success
        except Exception as e:  # pylint: disable=broad-except
            # Catch potential errors from _write_kv method
            self.context.logger.error(
                f"Failed to save media metadata ({media_type}) for path {media_path} via _write_kv: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            return False  # Failure

    def _download_and_save_media(
        self,
        response: requests.Response,
        ipfs_gateway_url: str,
        suffix: str,
        ipfs_hash: str,
    ) -> Optional[str]:
        """Download media stream from response and save to a designated media directory."""
        media_path = None
        downloaded_size = 0
        chunk_count = 0
        try:
            # Get storage path from params and ensure it exists
            storage_path = os.path.join(self.params.store_path, "media")
            os.makedirs(storage_path, exist_ok=True)

            # Create a unique filename
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_{ipfs_hash}{suffix}"
            media_path = os.path.join(storage_path, filename)

            with open(media_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        chunk_count += 1
                f.flush()
                os.fsync(f.fileno())

            if downloaded_size == 0:
                self.context.logger.error(
                    f"Received empty content (0 bytes downloaded) from {ipfs_gateway_url}"
                )
                # Cleanup is handled by the caller using _cleanup_temp_file
                return None

            self.context.logger.info(
                f"Successfully fetched media (size: {downloaded_size} bytes, chunks: {chunk_count}) to: {media_path}"
            )
            return media_path

        except IOError as e:
            self.context.logger.error(
                f"File I/O error during media download/save to {media_path}: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # Cleanup handled by the caller
            return None

    def _fetch_media_from_ipfs_hash(
        self, ipfs_hash: str, media_type: str, suffix: str
    ) -> Optional[str]:
        """Fetch media data from IPFS hash using requests library, save locally, and return the path."""

        # Synchronous function using requests, ONLY downloads and returns path or None

        # ****************************************************************************
        # ******************************** WARNING ***********************************
        # ****************************************************************************
        # This function uses the 'requests' library directly to fetch video data
        # from an IPFS gateway. This is a deviation from the standard practice of
        # using the built-in IPFS helper functions (like `get_from_ipfs`).
        #
        # REASON: The standard IPFS helpers were consistently failing to retrieve
        # video files correctly, potentially due to issues with handling large files,
        # streaming, or specific gateway interactions for video content type.
        # Using 'requests' provides more direct control over the HTTP request
        # and response handling, which proved necessary to successfully download
        # the video content in this specific case.
        #
        # This approach might be less robust if the IPFS gateway URL changes or if
        # underlying IPFS fetch mechanisms in the framework are updated.
        # Consider revisiting this if the built-in methods become reliable for videos.

        # plan to revisit this and figure out what's wrong with the built-in methods
        # ****************************************************************************

        media_path = None  # Initialize path for potential cleanup
        ipfs_gateway_url = f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
        error_reason = "unknown error"  # Default error reason
        try:
            self.context.logger.info(
                f"Attempting synchronous {media_type} fetch via requests: {ipfs_hash}"
            )
            self.context.logger.info(f"Using IPFS gateway URL: {ipfs_gateway_url}")

            with requests.get(ipfs_gateway_url, timeout=120, stream=True) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

                # Use helper to download and save
                media_path = self._download_and_save_media(
                    response, ipfs_gateway_url, suffix, ipfs_hash
                )

                if media_path is None:
                    # Empty download, error logged in helper
                    self._cleanup_temp_file(
                        media_path, "empty content"
                    )  # media_path will be None here
                    return None

            return media_path  # Return path on success

        except requests.exceptions.Timeout as e:
            self.context.logger.error(
                f"Timeout occurred while fetching {ipfs_gateway_url}: {e}"
            )
            error_reason = "timeout"
        except requests.exceptions.HTTPError as e:
            self.context.logger.error(
                f"HTTP error occurred for {ipfs_gateway_url}: {e.response.status_code} - {e.response.reason}"
            )
            error_reason = "http error"
        except requests.exceptions.RequestException as e:
            self.context.logger.error(
                f"HTTP request failed for {ipfs_gateway_url}: {e}"
            )
            error_reason = "request exception"

        # Centralized cleanup for all error cases
        # media_path might be None if error happened before _download_and_save_media assigned it
        self._cleanup_temp_file(media_path, error_reason)
        return None


class FailedMechRequestBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """FailedMechRequestBehaviour"""

    matching_round: Type[AbstractRound] = FailedMechRequestRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"FailedMechRequest: mech_responses = {self.synchronized_data.mech_responses}"
            )

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=False,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class FailedMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """FailedMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = FailedMechResponseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"FailedMechResponse: mech_responses = {self.synchronized_data.mech_responses}"
            )

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=False,
                failed_mech=True,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
