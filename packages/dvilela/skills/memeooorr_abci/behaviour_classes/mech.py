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

from dataclasses import asdict
import json
import random
from typing import Generator, Optional, Tuple, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.dvilela.skills.memeooorr_abci.rounds import (
    PostMechRequestRound,
    PreMechRequestRound,
    MechMetadata,

)

from packages.dvilela.skills.memeooorr_abci.payloads import (
    PostMechRequestPayload,
    )

# class PreMechRequestBehaviour(MemeooorrBaseBehaviour):
#     """PreMechRequestBehaviour"""

#     matching_round: Type[AbstractRound] = PreMechRequestRound

#     def async_act(self) -> Generator:
#         """Do the act, supporting asynchronous execution."""

#         with self.context.benchmark_tool.measure(self.behaviour_id).local():
#             new_mech_requests = []

#             mech_responses = self.synchronized_data.mech_responses
#             pending_tweet_ids = [r.nonce for r in mech_responses]

#             self.context.logger.info(f"PreMech: mech_responses = {mech_responses}")
#             self.context.logger.info(f"pending_tweet_ids = {pending_tweet_ids}")

#             new_mech_requests.append(
#                     asdict(
#                         MechMetadata(
#                             nonce=nonce,
#                             tool="openai-gpt-3.5-turbo",
#                             prompt=Prompt,
#                             ),
#                         )
#                     )


#             if not new_mech_requests:
#                 self.context.logger.info("No new mech requests. Skipping evaluation...")

#             sender = self.context.agent_address
#             payload = PreMechRequestPayload(
#                 sender=sender,
#                 content=json.dumps(
#                     {"new_mech_requests": new_mech_requests}, sort_keys=True
#                 ),
#             )

#         with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
#             yield from self.send_a2a_transaction(payload)
#             yield from self.wait_until_round_end()

#         self.set_done()


class PostMechRequestBehaviour(MemeooorrBaseBehaviour):
    """PostMechRequestBehaviour"""

    matching_round: Type[AbstractRound] = PostMechRequestRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():

            self.context.logger.info(
                f"PostMech: mech_responses = {self.synchronized_data.mech_responses}"
            )

            sender = self.context.agent_address
            payload = PostMechRequestPayload(
                sender=sender,
                content="", #content to add here 
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
