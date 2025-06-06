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
import base64
import json
import os
import re  # Added import for re module
import tempfile
import traceback
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Type
from urllib.parse import urlparse

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
from packages.valory.skills.abstract_round_abci.io_.store import SupportedFiletype
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
            # fetch_video_data_from_ipfs handles its own network/IO errors and returns Optional[str]
            video_path = self.fetch_video_data_from_ipfs(video_hash)

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

        # Case 2: Image format
        if image_hash:
            self.context.logger.info(f"Attempting image fetch for hash: {image_hash}")
            # fetch_image_data_from_ipfs handles its own fetch/IO/parse errors and returns Optional[str]
            image_path = self.fetch_image_data_from_ipfs(image_hash)

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
            "Could not process mech response: No video/image successfully fetched and saved. Looked for keys 'video' and 'image_hash' in the parsed 'result' data."
        )
        return False  # FAILURE

    def _save_media_info(
        self, media_path: str, media_type: str
    ) -> Generator[None, None, bool]:
        """Helper method to save media information to the key-value store. Returns True on success, False on failure."""
        media_info = {"path": media_path, "type": media_type}
        try:
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

    def _save_image_content(
        self, response: requests.Response, source_url: str
    ) -> Optional[str]:
        """Helper to save image content from a response object to a temporary file."""
        image_path = None
        downloaded_size = 0
        try:
            # Determine content type and extension
            raw_content_type = response.headers.get("content-type")
            content_type_lower = raw_content_type.lower() if raw_content_type else ""

            extension = ".png"  # Default
            if "jpeg" in content_type_lower or "jpg" in content_type_lower:
                extension = ".jpg"
            elif "gif" in content_type_lower:
                extension = ".gif"

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            with tempfile.NamedTemporaryFile(
                suffix=f"_{timestamp}{extension}", delete=False
            ) as temp_file:
                image_path = temp_file.name
                content = response.content  # Read all content at once for images
                if content:
                    temp_file.write(content)
                    downloaded_size = len(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            if downloaded_size == 0:
                self.context.logger.error(
                    f"Received empty content (0 bytes downloaded) for image from {source_url}"
                )
                if image_path:  # if file was created before finding out it's empty
                    self._cleanup_temp_file(image_path, "empty content after creation")
                return None

            self.context.logger.info(
                f"Successfully saved image (size: {downloaded_size} bytes) from {source_url} to: {image_path}"
            )
            return image_path

        except IOError as e:
            self.context.logger.error(
                f"File I/O error during image save to {image_path} (from {source_url}): {e}"
            )
            self.context.logger.error(traceback.format_exc())
            if image_path:
                self._cleanup_temp_file(image_path, "IOError during save")
            return None
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Unexpected error during image save to {image_path} (from {source_url}): {e}"
            )
            self.context.logger.error(traceback.format_exc())
            if image_path:
                self._cleanup_temp_file(image_path, "Unexpected error during save")
            return None

    def _download_and_save_image(
        self,
        response: requests.Response,
        ipfs_gateway_url: str,
        original_hash_for_html_path: str,
    ) -> Optional[str]:
        """Download image stream from response, handle HTML, and save to a temporary file."""
        try:
            raw_content_type = response.headers.get("content-type")
            content_type_lower = raw_content_type.lower() if raw_content_type else ""

            if content_type_lower.startswith("text/html"):
                self.context.logger.info(
                    f"Received HTML content from {ipfs_gateway_url}. Will parse for image links."
                )
                html_content = response.text
                # Regex to find href attributes pointing to common image file types
                image_links = re.findall(
                    r"href=[\'\"]?([^\'\" >]+\.(?:png|jpe?g|gif))[\'\"]?",
                    html_content,
                    re.IGNORECASE,
                )

                if not image_links:
                    self.context.logger.warning(
                        f"No direct image links found in HTML content from {ipfs_gateway_url}."
                    )
                    return None

                first_image_relative_path = image_links[0]
                new_image_url = ""

                if first_image_relative_path.startswith(("http://", "https://")):
                    new_image_url = first_image_relative_path
                elif first_image_relative_path.startswith("/ipfs/"):
                    # Absolute path from gateway root, e.g., /ipfs/QmHash/file.png
                    parsed_original_url = urlparse(
                        ipfs_gateway_url
                    )  # ipfs_gateway_url is the one that returned HTML
                    new_image_url = f"{parsed_original_url.scheme}://{parsed_original_url.netloc}{first_image_relative_path}"
                elif first_image_relative_path.startswith("ipfs/"):
                    # Path like ipfs/QmHash/file.png, treat as relative to gateway root
                    parsed_original_url = urlparse(ipfs_gateway_url)
                    new_image_url = f"{parsed_original_url.scheme}://{parsed_original_url.netloc}/{first_image_relative_path}"
                else:
                    # Truly relative path like "image.png" or "subdir/image.png"
                    # Construct the full URL using the original IPFS hash (directory) and the relative image path found.
                    base_ipfs_dir_url = f"https://gateway.autonolas.tech/ipfs/{original_hash_for_html_path}"
                    new_image_url = f"{base_ipfs_dir_url.rstrip('/')}/{first_image_relative_path.lstrip('/')}"

                self.context.logger.info(
                    f"Found image link in HTML: '{first_image_relative_path}'. Constructed new URL: {new_image_url}"
                )

                with requests.get(
                    new_image_url, timeout=60, stream=True
                ) as new_response:
                    new_response.raise_for_status()
                    new_raw_content_type = new_response.headers.get("content-type")
                    new_content_type_lower = (
                        new_raw_content_type.lower() if new_raw_content_type else ""
                    )
                    if not new_content_type_lower.startswith("image/"):
                        self.context.logger.error(
                            f"Expected an image from HTML-derived URL {new_image_url}, but got '{new_raw_content_type}'. Preview: {new_response.text[:200]}"
                        )
                        return None

                    self.context.logger.info(
                        f"Successfully fetched image data from HTML-derived URL: {new_image_url}"
                    )
                    return self._save_image_content(new_response, new_image_url)

            elif content_type_lower.startswith("image/"):
                self.context.logger.info(
                    f"Received direct image content from {ipfs_gateway_url}. Proceeding to save."
                )
                return self._save_image_content(response, ipfs_gateway_url)

            else:  # Neither HTML nor a direct image
                try:
                    response_text_preview = response.text[:200]
                except Exception:
                    response_text_preview = (
                        "(binary or non-text content preview unavailable)"
                    )
                self.context.logger.error(
                    f"Expected an image or HTML content from {ipfs_gateway_url}, but got '{raw_content_type}'. "
                    f"Response preview: '{response_text_preview}...' Skipping."
                )
                return None

        except requests.exceptions.RequestException as e:
            # This handles errors from the requests.get(new_image_url, ...) call if HTML was parsed
            self.context.logger.error(
                f"Request error during image download processing (URL: {ipfs_gateway_url} or derived HTML link): {e}"
            )
            self.context.logger.error(traceback.format_exc())
            return None
        # Note: _save_image_content handles its own IO/unexpected errors and associated cleanup.
        # Errors from the initial response (passed to this function) are handled by the caller (fetch_image_data_from_ipfs).

    def fetch_image_data_from_ipfs(self, image_hash: str) -> Optional[str]:
        """Fetch image from IPFS hash using requests, save to temp file, and return path or None."""
        # image_path is determined by _download_and_save_image and then _save_image_content
        # This function primarily handles the initial fetch and delegates processing.
        ipfs_gateway_url = f"https://gateway.autonolas.tech/ipfs/{image_hash}"

        self.context.logger.info(
            f"Attempting to fetch content for image_hash: {image_hash} via {ipfs_gateway_url}"
        )

        try:
            with requests.get(ipfs_gateway_url, timeout=60, stream=True) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

                # Pass image_hash as original_hash_for_html_path for correct URL construction
                # if the response is an HTML directory listing.
                image_path = self._download_and_save_image(
                    response, ipfs_gateway_url, image_hash
                )

                if image_path:
                    self.context.logger.info(
                        f"Successfully processed and saved image for hash {image_hash} to {image_path}"
                    )
                    return image_path  # Success

                # If image_path is None here, it means _download_and_save_image (or its delegate _save_image_content)
                # encountered an issue (e.g., HTML with no image, non-image content, save error) and logged it.
                self.context.logger.warning(
                    f"Failed to obtain a valid image path from _download_and_save_image for hash {image_hash} and URL {ipfs_gateway_url}."
                )
                return None  # Failure

        except requests.exceptions.Timeout as e:
            self.context.logger.error(
                f"Timeout occurred while attempting initial fetch from {ipfs_gateway_url} for hash {image_hash}: {e}"
            )
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else "Unknown Status"
            reason = e.response.reason if e.response else "Unknown Reason"
            self.context.logger.error(
                f"HTTP error {status_code} - {reason} during initial fetch from {ipfs_gateway_url} for hash {image_hash}."
            )
        except requests.exceptions.RequestException as e:
            self.context.logger.error(
                f"Request exception during initial fetch from {ipfs_gateway_url} for hash {image_hash}: {e}"
            )
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Unexpected error during initial fetch processing for hash {image_hash} from {ipfs_gateway_url}: {e}"
            )
            self.context.logger.error(traceback.format_exc())

        # If any exception occurred above, or if image_path was None from _download_and_save_image.
        # Temp file cleanup (if a file was partially created before an error) is handled
        # by _save_image_content or _cleanup_temp_file if called directly.
        # No explicit cleanup call here as _download_and_save_image and _save_image_content should manage it.
        return None  # Return None on any failure not resulting in a returned path

    def _cleanup_temp_file(self, file_path: Optional[str], reason: str) -> None:
        """Attempt to remove a temporary file and log the outcome."""
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                self.context.logger.info(
                    f"Removed temporary file ({reason}): {file_path}"
                )
            except OSError as rm_err:
                self.context.logger.warning(
                    f"Could not remove temp file {file_path} ({reason}): {rm_err}"
                )
        elif (
            reason == "empty content"
        ):  # This specific log might become less common if check moves inside save helper
            self.context.logger.info(
                "No temporary file to remove (empty download or not created)."
            )
        # else: file_path is None and reason is likely an error before file creation

    def _download_and_save_video(
        self, response: requests.Response, ipfs_gateway_url: str
    ) -> Optional[str]:
        """Download video stream from response and save to a temporary file."""
        video_path = None
        downloaded_size = 0
        chunk_count = 0
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            with tempfile.NamedTemporaryFile(
                suffix=f"_{timestamp}.mp4", delete=False
            ) as temp_file:
                video_path = temp_file.name  # Assign path *before* writing
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                        downloaded_size += len(chunk)
                        chunk_count += 1
                temp_file.flush()
                os.fsync(temp_file.fileno())

            if downloaded_size == 0:
                self.context.logger.error(
                    f"Received empty content (0 bytes downloaded) from {ipfs_gateway_url}"
                )
                # Cleanup is handled by the caller using _cleanup_temp_file
                return None

            self.context.logger.info(
                f"Successfully fetched video (size: {downloaded_size} bytes, chunks: {chunk_count}) to: {video_path}"
            )
            return video_path

        except IOError as e:
            self.context.logger.error(
                f"File I/O error during video download/save to {video_path}: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # Cleanup handled by the caller
            return None

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
    def fetch_video_data_from_ipfs(  # pylint: disable=too-many-locals
        self, ipfs_hash: str
    ) -> Optional[str]:  # Returns Optional[str], not bool or Generator
        """Fetch video data from IPFS hash using requests library, save locally, and return the path."""
        video_path = None  # Initialize video_path for potential cleanup
        ipfs_gateway_url = f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
        error_reason = "unknown error"  # Default error reason
        try:
            self.context.logger.info(
                f"Attempting synchronous video fetch via requests: {ipfs_hash}"
            )
            self.context.logger.info(f"Using IPFS gateway URL: {ipfs_gateway_url}")

            with requests.get(ipfs_gateway_url, timeout=120, stream=True) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

                # Use helper to download and save
                video_path = self._download_and_save_video(response, ipfs_gateway_url)

                if video_path is None:
                    # Empty download, error logged in helper
                    self._cleanup_temp_file(
                        video_path, "empty content"
                    )  # video_path will be None here
                    return None

            return video_path  # Return path on success

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
        # video_path might be None if error happened before _download_and_save_video assigned it
        self._cleanup_temp_file(video_path, error_reason)
        return None  # Return None on any failure


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
