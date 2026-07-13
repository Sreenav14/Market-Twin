# MarketTwin Execution Orchestrator

Runs approved, version-pinned MarketTwin missions.

## Responsibilities

- Load Test Plans
- Load approved Skills and Agent Blueprints
- Compile declarative agents into Google ADK runtime objects
- Manage mission state
- Request browser observations
- Produce structured action proposals
- Call the deterministic policy engine
- Pause for human authentication
- Manage browser control leases
- Verify outcomes
- Record execution events
- Trigger evaluation

The orchestrator decides what action is needed. The Browser Runtime performs the browser action.
