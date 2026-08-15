# Real-Time Multi-Source Vehicle Safety Event Reconciliation System

# Real-Time Multi-Source Vehicle Safety Event Reconciliation System

Title:
Real-Time Multi-Source Vehicle Safety Event Reconciliation System

Background:
In intelligent transportation systems, vehicles generate high-frequency safety-critical events from multiple sensors and communication channels—such as V2V radar data, AI-based anomaly detection, and blockchain-verified compliance logs. These events often arrive asynchronously, contain conflicting information, or reference the same vehicle at different timestamps. A robust system must reconcile these inputs into a consistent, auditable safety state to support real-time decision-making.

Problem Statement:
Design and implement a real-time vehicle safety event reconciliation system that ingests asynchronous, multi-source safety events from a vehicle’s sensors, V2V communication, and blockchain-verified compliance checks. The system must detect and resolve conflicts between these data streams, determine the most reliable safety state at any given time, and produce a deterministic, replayable audit trail of all reconciliation decisions.

Scope:
The system must process real-time event streams from three sources:  
1. **Sensor Events**: Raw vehicle telemetry (position, velocity, acceleration) sent via V2V communication.  
2. **AI Anomaly Detection**: AI-generated alerts (e.g., "potential collision") with confidence scores and timestamps.  
3. **Blockchain Compliance Logs**: Emission and safety compliance events from the Smart PUC system, stored as immutable on-chain records.  

All events are timestamped and may arrive out-of-order. The system must:  
- Reconstruct vehicle states over time.  
- Detect and resolve conflicts between sensor data and AI predictions.  
- Apply replay protection to prevent duplicate or conflicting blockchain logs.  
- Produce a deterministic, auditable reconciliation decision per vehicle at each timepoint.

MVP Scope:
The MVP must implement the following core components:  
1. **Event Ingestion & Buffering**: Accept and buffer asynchronous events from the three sources with proper timestamp handling.  
2. **State Reconstruction Engine**: Reconstruct the vehicle’s state (position, velocity) over time, handling late/out-of-order events.  
3. **Conflict Resolution & Decision Engine**:  
   - Compare sensor data and AI alerts to detect inconsistencies.  
   - Apply a deterministic rule engine to resolve conflicts (e.g., if sensor and AI disagree, use sensor data if confidence > 0.8, otherwise use AI).  
   - Output a single, consistent safety state per vehicle per timepoint.  
4. **Audit Trail Generator**: Produce a traceable decision log for each reconciliation, including:  
   - Input events considered  
   - Conflict resolution logic applied  
   - Final decision  
   - Timestamp and version

Advanced/Bonus Scope:
- Extend reconciliation to support multi-vehicle interactions (e.g., proximity alerts between two vehicles).  
- Add a visualization dashboard showing reconciliation decisions and state changes over time.  
- Support replay of historical events to verify reconciliation consistency.  
- Integrate a mock blockchain API to simulate on-chain compliance log updates.

Functional Requirements:
1. **Event Ingestion**:  
   - Accept POST /events with JSON body:  
     ```json
     {
       "source": "sensor|ai|blockchain",
       "vehicle_id": "string",
       "timestamp": "ISO 8601",
       "data": "object"
     }
     ```  
   - Support late events (up to 10 minutes late) with proper state reconstruction.  
   - Reject malformed events (missing fields, invalid timestamps).  

2. **State Reconstruction**:  
   - Maintain a time-ordered, versioned state for each vehicle.  
   - Apply interpolation for missing sensor readings.  
   - Handle conflicting sensor updates (e.g., two position reports at similar times).  

3. **Conflict Resolution**:  
   - For each vehicle at each timepoint, evaluate all relevant events.  
   - Apply resolution logic:  
     - If sensor and AI disagree: use sensor if confidence ≥ 0.8, otherwise use AI.  
     - If blockchain log conflicts with sensor: use blockchain if timestamp is newer, otherwise use sensor.  
   - Output a single `safety_state` object per vehicle per timepoint.  

4. **Audit Trail**:  
   - Generate a JSON log for each reconciliation decision:  
     ```json
     {
       "vehicle_id": "string",
       "timestamp": "ISO 8601",
       "events_considered": ["event1", "event2"],
       "conflicts_resolved": {"sensor_vs_ai": "used_sensor"},
       "final_state": "safe|alert|danger",
       "decision_reason": "sensor_confidence_0.95"
     }
     ```  
   - Store logs in a MongoDB collection `audit_trail`.  

5. **Replay & Idempotency**:  
   - Replaying the same event must not alter the final state or audit log.  
   - Support replay of historical events to verify state consistency.

Non-Functional Requirements:
1. **Determinism**: Identical input events → identical final states and audit logs.  
2. **Idempotency**: Replaying the same event must not create duplicate entries.  
3. **Replayability**: The system must support replay of historical events to verify reconciliation.  
4. **Performance**: Handle up to 100 events per second with < 500ms latency.  
5. **Auditability**: All decisions must be traceable with full provenance.

Constraints:
- Use only Python, Flask, JavaScript, HTML, CSS, MongoDB, Git, and Docker.  
- No external APIs or cloud services (simulate blockchain logs locally).  
- No ML/LLM components.  
- Do not use Kafka, Redis, or distributed systems.  
- All data must be stored in MongoDB.

Deliverables:
1. Submission — Public GitHub repository URL (required).  
2. Repository contents —  
   - Backend: Flask API with `POST /events` endpoint and state reconciliation logic.  
   - Frontend: Simple dashboard showing vehicle safety states and audit logs.  
   - Sample fixture datasets covering ≥5 interacting edge cases (e.g., late events, conflicting sensor data, blockchain conflicts).  
   - Audit/decision-trace output files.  
3. Test Suite — Automated tests covering all edge cases, including replay and idempotency.  
4. Documentation — README with setup instructions, fixture examples, and audit output locations.
