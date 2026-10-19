"""Kafka secrets must be redacted and SASL credentials transported over TLS."""

import pytest
from markettwin_shared.messaging.kafka_consumer import KafkaConsumer, KafkaConsumerSettings
from markettwin_shared.messaging.kafka_producer import KafkaProducer, KafkaProducerSettings


@pytest.mark.parametrize("kind", ["producer", "consumer"])
async def test_sasl_plaintext_rejected_and_password_hidden(kind: str) -> None:
    if kind == "producer":
        settings = KafkaProducerSettings(
            bootstrap_servers=("localhost:9092",),
            security_protocol="SASL_PLAINTEXT",
            username="user",
            password="secret-value",
        )
        client = KafkaProducer(settings)
    else:
        settings = KafkaConsumerSettings(
            bootstrap_servers=("localhost:9092",),
            topic="commands",
            group_id="workers",
            security_protocol="SASL_PLAINTEXT",
            username="user",
            password="secret-value",
        )
        client = KafkaConsumer(settings)
    assert "secret-value" not in repr(settings)
    with pytest.raises(ValueError, match="SASL_SSL"):
        await client.start()


@pytest.mark.parametrize("kind", ["producer", "consumer"])
@pytest.mark.parametrize("username,password", [("", "secret"), ("user", ""), (" ", "secret")])
async def test_blank_sasl_credentials_rejected(kind: str, username: str, password: str) -> None:
    if kind == "producer":
        settings = KafkaProducerSettings(
            bootstrap_servers=("localhost:9092",),
            security_protocol="SASL_SSL",
            sasl_mechanism="PLAIN",
            username=username,
            password=password,
        )
        client = KafkaProducer(settings)
    else:
        settings = KafkaConsumerSettings(
            bootstrap_servers=("localhost:9092",),
            topic="commands",
            group_id="workers",
            security_protocol="SASL_SSL",
            sasl_mechanism="PLAIN",
            username=username,
            password=password,
        )
        client = KafkaConsumer(settings)
    with pytest.raises(ValueError, match="required"):
        await client.start()
