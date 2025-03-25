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
import tempfile
import traceback
from datetime import datetime
from typing import Generator, Type

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


class PostMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """PostMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = PostMechResponseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Initialize mech_for_twitter to False by default
            mech_for_twitter = False
            ipfs_link = None

            self.context.logger.info(
                f"Mech request was successful, response = {self.synchronized_data.mech_responses}"
            )
            if self.synchronized_data.mech_responses:
                try:
                    # Check if the response contains an image by examining the result
                    response = self.synchronized_data.mech_responses[0]
                    # Add null check before parsing JSON
                    if response.result is not None:
                        result_json = json.loads(response.result)

                        # check if the result_json has an ipfs_link
                        if "ipfs_link" in result_json:
                            ipfs_link = result_json["ipfs_link"]
                            self.context.logger.info(
                                "IPFS link found in mech response fetching the image from IPFS"
                            )
                            self.context.logger.info(f"IPFS link: {ipfs_link}")
                            success = yield from self.fetch_image_data_from_ipfs(
                                ipfs_link
                            )
                            if success:
                                self.context.logger.info(
                                    "Image data fetched and saved successfully"
                                )
                                mech_for_twitter = True
                        else:
                            self.context.logger.info(
                                "No IPFS link found in mech response, skipping image fetching"
                            )
                            mech_for_twitter = False
                    else:
                        self.context.logger.error("Mech response result is None")
                        mech_for_twitter = False
                except Exception as e:  # pylint: disable=broad-except
                    self.context.logger.error(f"Error parsing mech response: {e}")
                    # mech_for_twitter remains False in case of exception
            else:
                self.context.logger.error("No mech responses found")
                # mech_for_twitter remains False if no responses

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=mech_for_twitter,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def fetch_image_data_from_ipfs(  # pylint: disable=too-many-return-statements
        self, ipfs_link: str
    ) -> Generator[None, None, bool]:
        """Fetch image from IPFS link and save it to a temporary file."""
        try:
            self.context.logger.info(f"Fetching image from IPFS link: {ipfs_link}")

            # Extract the IPFS hash from the URL
            path_parts = ipfs_link.split("/")
            ipfs_hash = path_parts[4]
            self.context.logger.info(f"Extracted IPFS hash: {ipfs_hash}")

            response = yield from self.get_from_ipfs(
                ipfs_hash=ipfs_hash, filetype=SupportedFiletype.JSON
            )

            if response:
                try:
                    # The response from get_from_ipfs is a Python object, might be dict or list
                    # Check if it's a dictionary with 'result' field
                    if isinstance(response, dict) and "result" in response:
                        result_data = response["result"]
                    # Check if it's a list (the actual error case)
                    elif isinstance(response, list) and len(response) > 0:
                        # Take the first item if it's a list
                        result_item = response[0]
                        # Check if the first item has a result field
                        if isinstance(result_item, dict) and "result" in result_item:
                            result_data = result_item["result"]
                        else:
                            self.context.logger.error(
                                f"Unexpected response format: {response}"
                            )
                            return False
                    else:
                        self.context.logger.error(
                            f"Unexpected response format: {response}"
                        )
                        return False

                    # Parse result_data if it's a string
                    if isinstance(result_data, str):
                        result_data = json.loads(result_data)

                    # Process artifacts
                    if "artifacts" in result_data and result_data["artifacts"]:
                        # Get the first artifact's base64 data
                        image_base64 = result_data["artifacts"][0]["base64"]
                        image_data = base64.b64decode(image_base64)

                        # Create a temporary file with a specific suffix for the image
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        with tempfile.NamedTemporaryFile(
                            suffix=f"_{timestamp}.png", delete=False
                        ) as temp_file:
                            temp_file.write(image_data)
                            image_path = temp_file.name

                        self.context.logger.info(
                            f"Successfully saved image to temporary file: {image_path}"
                        )

                        # Store the image path in the context
                        yield from self._write_kv({"latest_image_path": image_path})
                        return True

                    self.context.logger.error("No artifacts found in result data")
                    return False

                except Exception as e:  # pylint: disable=broad-except
                    self.context.logger.error(f"Error processing response: {e}")
                    self.context.logger.error(traceback.format_exc())
                    return False

            self.context.logger.error("Failed to fetch image: Empty response")
            return False

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error fetching image: {e}")
            self.context.logger.error(traceback.format_exc())
            return False


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
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
