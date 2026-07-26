"""Tests del protocolo MESH — Fase 4."""

from __future__ import annotations

import json

import pytest

from eidos.mesh.protocol import (
    MeshMessage,
    MessageType,
    NodeRole,
    NodeStatus,
    PubTopic,
    RpcMethod,
    error,
    pub,
    request,
    response,
)


class TestMeshMessage:
    def test_message_to_json_roundtrip(self) -> None:
        m = pub(
            source="node-1",
            topic=PubTopic.HEARTBEAT,
            params={"leader_id": "node-1"},
        )
        j = m.to_json()
        m2 = MeshMessage.from_json(j)
        assert m2.id == m.id
        assert m2.source == "node-1"
        assert m2.topic == "heartbeat"
        assert m2.params == {"leader_id": "node-1"}

    def test_message_from_bytes(self) -> None:
        m = pub(source="x", topic="custom")
        b = m.to_json().encode("utf-8")
        m2 = MeshMessage.from_json(b)
        assert m2.id == m.id

    def test_message_has_id_and_ts(self) -> None:
        m = pub(source="x", topic="t")
        assert m.id
        assert m.ts
        # ts debe ser ISO-8601
        assert "T" in m.ts
        assert "Z" in m.ts or "+" in m.ts


class TestBuilders:
    def test_pub_builder(self) -> None:
        m = pub(source="worker-1", topic=PubTopic.MEMORY_UPDATE, params={"key": "v"})
        assert m.type == MessageType.PUB
        assert m.topic == "memory_update"
        assert m.params == {"key": "v"}
        assert m.method is None
        assert m.in_reply_to is None

    def test_request_builder(self) -> None:
        m = request(
            source="worker-1",
            method=RpcMethod.ACQUIRE_TOKEN,
            params={"resource": "cortex"},
            target="leader-1",
        )
        assert m.type == MessageType.REQUEST
        assert m.method == "acquire_token"
        assert m.target == "leader-1"

    def test_response_builder(self) -> None:
        m = response(
            source="leader-1",
            in_reply_to="req-123",
            params={"granted": True},
            target="worker-1",
        )
        assert m.type == MessageType.RESPONSE
        assert m.in_reply_to == "req-123"
        assert m.params == {"granted": True}

    def test_error_builder(self) -> None:
        m = error(
            source="leader-1",
            in_reply_to="req-123",
            error_msg="resource busy",
            target="worker-1",
        )
        assert m.type == MessageType.ERROR
        assert m.error == "resource busy"


class TestEnums:
    def test_node_roles(self) -> None:
        assert NodeRole.LEADER.value == "leader"
        assert NodeRole.WORKER.value == "worker"
        assert NodeRole.CANDIDATE.value == "candidate"

    def test_pub_topics(self) -> None:
        assert PubTopic.HEARTBEAT.value == "heartbeat"
        assert PubTopic.MEMORY_UPDATE.value == "memory_update"
        assert PubTopic.NODE_JOINED.value == "node_joined"

    def test_rpc_methods(self) -> None:
        assert RpcMethod.HELLO.value == "hello"
        assert RpcMethod.ACQUIRE_TOKEN.value == "acquire_token"
        assert RpcMethod.DELEGATE_INFERENCE.value == "delegate_inference"
