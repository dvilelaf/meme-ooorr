#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
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

"""Test openai"""

import json
import os

import dotenv
import requests
from openai import OpenAI


dotenv.load_dotenv(override=True)


def openai_call():
    """Call through OpenAI"""
    client = OpenAI(
        base_url=os.getenv("OPENAI_API_BASE"), api_key=os.getenv("OPENAI_API_KEY")
    )

    completion = client.completions.create(
        model="accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new",
        prompt="Write a tweet about memecoins",
    )
    print(completion.choices[0].text)


def api_call():
    """Call through API"""
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    payload = {
        "model": "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new",
        "max_tokens": 16384,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "temperature": 0.6,
        "messages": [{"role": "user", "content": "Write a tweet about memecoins"}],
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('FIREWORKS_API_KEY')}",
    }
    response = requests.request(
        "POST", url, headers=headers, data=json.dumps(payload), timeout=60
    )
    print(response.status_code, response.json())
    print(response.json()["choices"][0]["message"]["content"])


api_call()
