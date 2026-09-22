"""Failure-path tests of the proposed protocol; no production integration implied."""

import asyncio

import pytest
from handoff_protocol import Handoff, Rejected, escalation


async def noop():
    return "done"


async def active():
    machine = Handoff("context_a", frozenset({"alice", "bob"}))
    await machine.request_handoff("context_a")
    lease = await machine.claim("alice", "context_a", now=0, ttl=10)
    return machine, lease


@pytest.mark.asyncio
async def test_queued_agent_action_cannot_run_after_pause_requested():
    machine = Handoff("context_a", frozenset({"alice"}))
    await machine.lock.acquire()
    queued = asyncio.create_task(machine.agent_action(0, "context_a", noop))
    await asyncio.sleep(0)
    pause = asyncio.create_task(machine.request_handoff("context_a"))
    await asyncio.sleep(0)
    machine.lock.release()
    with pytest.raises(Rejected):
        await queued
    await pause
    assert machine.state == "waiting"


@pytest.mark.asyncio
async def test_existing_action_finishes_before_human_can_claim():
    machine = Handoff("context_a", frozenset({"alice"}))
    entered, release = asyncio.Event(), asyncio.Event()

    async def operation():
        entered.set()
        await release.wait()

    action = asyncio.create_task(machine.agent_action(0, "context_a", operation))
    await entered.wait()
    pause = asyncio.create_task(machine.request_handoff("context_a"))
    await asyncio.sleep(0)
    assert machine.pause_requested and machine.state == "agent"
    assert not pause.done()
    release.set()
    await action
    await pause
    assert machine.state == "waiting"


@pytest.mark.asyncio
async def test_only_one_of_two_claimants_acquires_control():
    machine = Handoff("context_a", frozenset({"alice", "bob"}))
    await machine.request_handoff("context_a")
    results = await asyncio.gather(
        machine.claim("alice", "context_a", 0, 10),
        machine.claim("bob", "context_a", 0, 10), return_exceptions=True,
    )
    assert sum(isinstance(result, Rejected) for result in results) == 1


@pytest.mark.asyncio
async def test_unrecognized_user_cannot_claim():
    machine = Handoff("context_a", frozenset({"alice"}))
    await machine.request_handoff("context_a")
    with pytest.raises(Rejected):
        await machine.claim("eve", "context_a", 0, 10)


@pytest.mark.asyncio
async def test_wrong_context_rejected():
    machine, lease = await active()
    with pytest.raises(Rejected):
        await machine.human_action(lease, "context_b", 1, noop)


@pytest.mark.asyncio
async def test_expiry_blocks_input_before_background_cleanup():
    machine, lease = await active()
    with pytest.raises(Rejected):
        await machine.human_action(lease, "context_a", 10, noop)
    assert machine.state == "human"
    await machine.expire(10)
    assert machine.state == "waiting" and not machine.capture


@pytest.mark.asyncio
async def test_done_revokes_human_input_without_resuming_agent():
    machine, lease = await active()
    await machine.done(lease, "context_a", 1)
    with pytest.raises(Rejected):
        await machine.human_action(lease, "context_a", 2, noop)
    with pytest.raises(Rejected):
        await machine.agent_action(machine.epoch, "context_a", noop)
    assert machine.state == "verifying" and not machine.capture


@pytest.mark.asyncio
@pytest.mark.parametrize("postcondition,capture_safe", [(False, True), (True, False)])
async def test_failed_verification_does_not_resume(postcondition, capture_safe):
    machine, lease = await active()
    await machine.done(lease, "context_a", 1)
    assert not await machine.verify(
        "context_a", postcondition=postcondition, capture_safe=capture_safe,
    )
    assert machine.state == "waiting" and not machine.capture


@pytest.mark.asyncio
async def test_old_agent_epoch_rejected_after_successful_resume():
    machine, lease = await active()
    await machine.done(lease, "context_a", 1)
    assert await machine.verify("context_a", postcondition=True, capture_safe=True)
    with pytest.raises(Rejected):
        await machine.agent_action(0, "context_a", noop)
    assert await machine.agent_action(machine.epoch, "context_a", noop) == "done"


@pytest.mark.asyncio
async def test_old_lease_rejected_after_reacquisition():
    machine, old = await active()
    await machine.expire(10)
    new = await machine.claim("alice", "context_a", 11, 10)
    with pytest.raises(Rejected):
        await machine.human_action(old, "context_a", 12, noop)
    assert await machine.human_action(new, "context_a", 12, noop) == "done"


@pytest.mark.asyncio
async def test_secret_canary_not_recorded_during_handoff():
    machine, lease = await active()
    machine.record_page_event("SYNTHETIC_SECRET_CANARY")
    await machine.done(lease, "context_a", 1)
    machine.record_page_event("SYNTHETIC_SECRET_CANARY")
    assert "SYNTHETIC_SECRET_CANARY" not in machine.audit


@pytest.mark.asyncio
async def test_context_loss_never_creates_silent_replacement():
    machine, lease = await active()
    await machine.context_lost()
    with pytest.raises(Rejected):
        await machine.done(lease, "context_a", 1)
    with pytest.raises(Rejected):
        await machine.agent_action(machine.epoch, "context_a", noop)
    assert machine.state == "context_lost" and not machine.capture


@pytest.mark.parametrize("inputs,expected", [
    ({"forbidden": True, "secret_step": True}, "stop_policy_blocked"),
    ({"secret_step": True}, "request_private_handoff"),
    ({"missing_observation": True}, "expand_evidence"),
    ({"missing_user_fact": True}, "ask_targeted_question"),
    ({"recovery_exhausted": True}, "request_assistance_or_finish_unresolved"),
    ({}, "continue_within_scope"),
])
def test_escalation_type(inputs, expected):
    assert escalation(**inputs) == expected
