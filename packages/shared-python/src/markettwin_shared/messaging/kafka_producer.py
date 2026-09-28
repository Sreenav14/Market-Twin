"""Provider-neutral Kafka producer for MarketTwin."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Literal

from aiokafka import AIOKafkaProducer  # pyright: ignore[reportMissingTypeStubs]

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
class KafkaProducerSettings:
    """Connection settings for a Kafka producer."""

    bootstrap_servers: tuple[str, ...]

    security_protocol: KafkaSecurityProtocol = (
        "PLAINTEXT"
    )

    sasl_mechanism: KafkaSaslMechanism | None = None
    username: str | None = None
    password: str | None = None

    ssl_ca_file: str | None = None

    client_id: str = "markettwin"


class KafkaProducer:
    """Small async wrapper around the Kafka client."""

    def __init__(
        self,
        settings: KafkaProducerSettings,
    ) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Create the Kafka connection."""

        if self._producer is not None:
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

        producer = AIOKafkaProducer(
            bootstrap_servers=",".join(
                settings.bootstrap_servers
            ),
            client_id=settings.client_id,
            security_protocol=(
                settings.security_protocol
            ),
            ssl_context=ssl_context,
            sasl_mechanism=(
                settings.sasl_mechanism
                or "PLAIN"
            ),
            sasl_plain_username=settings.username,
            sasl_plain_password=settings.password,

            # Required by our architecture.
            enable_idempotence=True,
        )

        await producer.start()

        self._producer = producer

    async def stop(self) -> None:
        """Close the Kafka connection."""

        producer = self._producer

        if producer is None:
            return

        self._producer = None

        await producer.stop()

    async def publish(
        self,
        *,
        topic: str,
        key: bytes | None,
        value: bytes,
    ) -> None:
        """Publish one message and wait for broker acknowledgement."""

        producer = self._producer

        if producer is None:
            raise RuntimeError(
                "Kafka producer has not been started."
            )

        await producer.send_and_wait(  # pyright: ignore[reportUnknownMemberType]
            topic,
            key=key,
            value=value,
        )