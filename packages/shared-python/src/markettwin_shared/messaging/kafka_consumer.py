"""Provider-neutral Kafka consumer for MarketTwin."""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from aiokafka import AIOKafkaConsumer  # pyright: ignore[reportMissingTypeStubs]
from aiokafka.structs import ConsumerRecord  # pyright: ignore[reportMissingTypeStubs]


class _ByteConsumer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def getone(self) -> ConsumerRecord[bytes, bytes]: ...
    async def commit(self) -> None: ...


KafkaSecurityProtocol = Literal[
    "PLAINTEXT",
    "SSL",
    "SASL_PLAINTEXT",
    "SASL_SSL",
]

KafkaSaslMechanism = Literal[
    "PLAIN",
    "SCRAM-SHA-256",
    "SCRAM-SHA-512",
]


@dataclass(frozen=True, slots=True)
class KafkaConsumerSettings:
    """Connection settings for a Kafka consumer."""

    bootstrap_servers: tuple[str, ...]
    topic: str
    group_id: str

    security_protocol: KafkaSecurityProtocol = "PLAINTEXT"

    sasl_mechanism: KafkaSaslMechanism | None = None
    username: str | None = None
    password: str | None = None

    ssl_ca_file: str | None = None

    client_id: str = "markettwin"


@dataclass(frozen=True, slots=True)
class KafkaMessage:
    """One Kafka message delivered to MarketTwin."""

    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes


def load_kafka_consumer_settings(
    *,
    topic: str,
    group_id: str,
    client_id: str = "markettwin",
) -> KafkaConsumerSettings:
    """Load Kafka consumer configuration from environment."""

    raw_servers = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "",
    ).strip()

    if not raw_servers:
        raise RuntimeError(
            "KAFKA_BOOTSTRAP_SERVERS is required."
        )

    bootstrap_servers = tuple(
        server.strip()
        for server in raw_servers.split(",")
        if server.strip()
    )

    raw_security_protocol = os.getenv(
        "KAFKA_SECURITY_PROTOCOL",
        "PLAINTEXT",
    ).strip()

    allowed_protocols = {
        "PLAINTEXT",
        "SSL",
        "SASL_PLAINTEXT",
        "SASL_SSL",
    }

    if raw_security_protocol not in allowed_protocols:
        raise RuntimeError(
            "Unsupported KAFKA_SECURITY_PROTOCOL."
        )

    security_protocol = cast(
        KafkaSecurityProtocol,
        raw_security_protocol,
    )

    raw_mechanism = os.getenv(
        "KAFKA_SASL_MECHANISM",
        "",
    ).strip()

    sasl_mechanism: KafkaSaslMechanism | None = None

    if raw_mechanism:
        allowed_mechanisms = {
            "PLAIN",
            "SCRAM-SHA-256",
            "SCRAM-SHA-512",
        }

        if raw_mechanism not in allowed_mechanisms:
            raise RuntimeError(
                "Unsupported KAFKA_SASL_MECHANISM."
            )

        sasl_mechanism = cast(
            KafkaSaslMechanism,
            raw_mechanism,
        )

    return KafkaConsumerSettings(
        bootstrap_servers=bootstrap_servers,
        topic=topic,
        group_id=group_id,
        security_protocol=security_protocol,
        sasl_mechanism=sasl_mechanism,
        username=os.getenv("KAFKA_USERNAME"),
        password=os.getenv("KAFKA_PASSWORD"),
        ssl_ca_file=(
            os.getenv("KAFKA_SSL_CA_FILE")
            or None
        ),
        client_id=client_id,
    )


class KafkaConsumer:
    """Small async wrapper around a Kafka consumer."""

    def __init__(
        self,
        settings: KafkaConsumerSettings,
    ) -> None:
        self._settings = settings
        self._consumer: _ByteConsumer | None = None

    async def start(self) -> None:
        """Connect and subscribe to Kafka."""

        if self._consumer is not None:
            return

        settings = self._settings

        ssl_context: ssl.SSLContext | None = None

        if settings.security_protocol in {
            "SSL",
            "SASL_SSL",
        }:
            ssl_context = ssl.create_default_context(
                cafile=settings.ssl_ca_file,
            )

        if settings.security_protocol in {
            "SASL_PLAINTEXT",
            "SASL_SSL",
        }:
            if settings.sasl_mechanism is None:
                raise ValueError(
                    "Kafka SASL mechanism is required."
                )

            if settings.username is None:
                raise ValueError(
                    "Kafka username is required."
                )

            if settings.password is None:
                raise ValueError(
                    "Kafka password is required."
                )

        consumer = cast(
            _ByteConsumer,
            AIOKafkaConsumer(
                settings.topic,
                bootstrap_servers=",".join(
                    settings.bootstrap_servers
                ),
                client_id=settings.client_id,
                group_id=settings.group_id,
                security_protocol=str(
                    settings.security_protocol
                ),
                ssl_context=ssl_context,
                sasl_mechanism=(
                    settings.sasl_mechanism
                    or "PLAIN"
                ),
                sasl_plain_username=settings.username,
                sasl_plain_password=settings.password,

                # MarketTwin commits only after processing succeeds.
                enable_auto_commit=False,

                # New consumer groups should process existing durable commands.
                auto_offset_reset="earliest",
            ),
        )

        try:
            await consumer.start()
        except Exception:
            await consumer.stop()
            raise

        self._consumer = consumer

    async def stop(self) -> None:
        """Close the Kafka consumer."""

        consumer = self._consumer

        if consumer is None:
            return

        self._consumer = None

        await consumer.stop()

    async def receive(self) -> KafkaMessage:
        """Wait for and return one Kafka message."""

        consumer = self._consumer

        if consumer is None:
            raise RuntimeError(
                "Kafka consumer has not been started."
            )

        message = await consumer.getone() 

        if not isinstance(message.value, bytes):
            raise ValueError("Kafka message value must be bytes.")

        return KafkaMessage(
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            key=message.key,
            value=message.value,
        )

    async def commit(self) -> None:
        """Commit consumed offsets after successful processing."""

        consumer = self._consumer

        if consumer is None:
            raise RuntimeError(
                "Kafka consumer has not been started."
            )

        await consumer.commit()