# MirrorDB Agent and Attribute Data Flow

This document explains how the Memeooorr service interacts with the MirrorDB backend API to manage agent and attribute data.

## Overview

The MirrorDB stores persistent data related to agents, their types, attributes, and specific attribute values (instances). The service interacts with the MirrorDB's REST API to perform CRUD (Create, Read, Update, Delete) operations on this data.

## Core Concepts & IDs

- **Agent Type (`type_id`):** Defines a category of agents (e.g., `memeooorr`). Created via `POST /api/agent-types/` or retrieved by name via `GET /api/agent-types/name/{agent_type_name}`.
- **Agent Registry (`agent_id`):** Represents a specific instance of an agent, linked to an Agent Type and an Ethereum address. Created via `POST /api/agent-registry/` or retrieved by address via `GET /api/agent-registry/address/{eth_address}`.
- **Attribute Definition (`attr_def_id`):** Defines a specific piece of data that can be associated with an Agent Type (e.g., `twitter_username`, `twitter_interactions`). It specifies the attribute's name, data type (string, json, etc.), and whether it's required. Created via `POST /api/agent-types/{type_id}/attributes/` or retrieved by name via `GET /api/attributes/name/{attr_def_name}`. Requires authentication.
- **Attribute Instance (`attribute_id`):** Represents the actual value of a specific Attribute Definition for a specific Agent. Created via `POST /api/agents/{agent_id}/attributes/`, retrieved via `GET /api/agents/{agent_id}/attributes/{attr_def_id}/`, and updated via `PUT /api/agent-attributes/{attribute_id}`. Requires authentication.

## Registration and Attribute Setup Flow

When an agent starts or needs to ensure its registration, the following MirrorDB API interactions typically occur:

1. **Get/Create Agent Type:**
    - `GET /api/agent-types/name/{agent_type_name}` (e.g., `memeooorr`)
    - If not found (404), `POST /api/agent-types/` with `type_name` and `description` to create it.
    - The `type_id` is obtained from the response.
2. **Get/Create Agent Registry Entry:**
    - `POST /api/agent-registry/` with `agent_name`, `type_id`, and `eth_address`.
    - If this fails (e.g., address already exists), `GET /api/agent-registry/address/{eth_address}` to fetch the existing entry.
    - The `agent_id` is obtained from the response.
3. **Get/Create Attribute Definitions:**
    - For each required attribute (e.g., `twitter_username`, `twitter_interactions`):
        - `GET /api/attributes/name/{attr_def_name}`
        - If not found (404):
            - Generate authentication signature based on the target endpoint and `agent_id`.
            - `POST /api/agent-types/{type_id}/attributes/` with the attribute definition details (`attr_name`, `data_type`, etc.) and the authentication signature.
        - The `attr_def_id` is obtained from the response.
4. **Store Configuration:** The obtained `agent_id`, `type_id`, and `attr_def_id`s are typically stored locally (e.g., in a KV store) for later use.

## Managing Attribute Instances (Values)

Once the agent and attribute definitions are set up, the service manages the specific values (instances) for each agent:

1. **Checking/Updating an Attribute (e.g., `twitter_username`):**
    - `GET /api/agents/{agent_id}/attributes/{username_attr_def_id}/` to retrieve the current stored value.
    - **If exists and needs update:**
        - Obtain the `attribute_id` from the GET response.
        - Generate authentication signature for the update endpoint.
        - `PUT /api/agent-attributes/{attribute_id}` with the updated `agent_attr` payload (containing the new `string_value`) and authentication.
    - **If not exists (404 from GET):**
        - Generate authentication signature for the creation endpoint.
        - `POST /api/agents/{agent_id}/attributes/` with the full `agent_attr` payload (including `agent_id`, `attr_def_id`, `string_value`, etc.) and authentication.
2. **Recording Interactions (e.g., `twitter_interactions` - JSON type):**
    - This attribute is typically append-only in practice.
    - Generate authentication signature for the creation endpoint.
    - `POST /api/agents/{agent_id}/attributes/` with the `agent_attr` payload containing:
        - `agent_id`
        - `attr_def_id` for `twitter_interactions`
        - `json_value` containing the interaction details (action, timestamp, specific data like tweet_id or user_id).
        - Authentication signature.
    - Note: Each interaction creates a *new* attribute instance record.

## Retrieving Attribute Data

The service can retrieve attribute data in bulk:

- **Get all values for a specific attribute across all agents of a type:**
    - `GET /api/agent-types/{agent_type_id}/attributes/{attr_def_id}/values`
    - Used, for example, to get all recorded `twitter_interactions` to find recently active agents.
- **Get a specific agent's attribute value:**
    - `GET /api/agents/{agent_id}/attributes/{attr_def_id}/`
    - Used to fetch the `twitter_username` for a specific `agent_id` found through interaction analysis.

This allows the service to, for instance, find agents active in the last N days based on their interaction timestamps and then retrieve their corresponding Twitter usernames.