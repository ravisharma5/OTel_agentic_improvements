# Fault prediction use case — API map

Which APIs does a fault prediction workflow need, which ones exist as OpenAPI specs, and which ones are already in the mcp-telco-toolkit?

## Summary

| API | Key operations for fault prediction | In mcp-telco-toolkit? | OpenAPI spec available? | Notes |
|-----|-------------------------------------|----------------------|------------------------|-------|
| **TMF642 Alarm Management** | GET /alarm, PATCH /alarm, subscribe to alarm events | No | Yes — [v5.0.1 OAS YAML](https://github.com/tmforum-apis/TMF642_AlarmManagement) + v4.0.0 Swagger | Primary alarm source. 18 event listener endpoints for real-time alarm notification. |
| **TMF628 Performance Management** | GET /measurementCollectionJob, POST /onDemandCollection, GET /trackingRecord | No | Yes — [v4.0.0 Swagger](https://github.com/tmforum-apis/TMF628_Performance) | Pull KPI measurements for affected network elements. 5 resource types, 35 operations. |
| **TMF621 Trouble Ticket** | POST /troubleTicket, PATCH /troubleTicket, GET /troubleTicket | No | Yes — [v5.0.1 OAS YAML](https://github.com/tmforum-apis/TMF621_TroubleTicket) + v4.0.0 Swagger | Create/update tickets as part of resolution workflow. 10 event types. |
| **NWDAF AnalyticsInfo (TS 29.520)** | GET /analytics (event-id, event-filter, tgt-ue) | No | Yes — [Rel-18 YAML](https://github.com/jdegre/5GC_APIs/blob/Rel-18/TS29520_Nnwdaf_AnalyticsInfo.yaml), also on [3GPP FTP](https://www.3gpp.org/ftp/Specs/archive/OpenAPI/Rel-16/TS29520_Nnwdaf_AnalyticsInfo.yaml) | Analytics events: LOAD_LEVEL_INFORMATION, ABNORMAL_BEHAVIOUR, USER_DATA_CONGESTION. NextGCore implements this. |
| **NWDAF EventsSubscription (TS 29.520)** | POST /subscriptions, DELETE /subscriptions/{id} | No | Yes — [Rel-18 YAML](https://github.com/jdegre/5GC_APIs/blob/Rel-18/TS29520_Nnwdaf_EventsSubscription.yaml) | Subscribe to real-time analytics notifications. |
| **CAMARA Device Status** | GET device connectivity, GET roaming status | Yes (1 tool) | Yes — [device-status.yaml](https://github.com/camaraproject/DeviceStatus/blob/release-0.5.0/code/API_definitions/device-status.yaml) | Check if affected devices are connected. Repo split into 3 sub-repos after Spring25 release. |
| **CAMARA Device Location** | POST verify-location, POST retrieve-location | No | Yes — [DeviceLocation repo](https://github.com/camaraproject/DeviceLocation) | Locate affected devices geographically. |
| **CAMARA SIM Swap** | POST /check, POST /retrieve-date | Yes (1 tool) | Yes — via camaraproject | Rule out SIM swap as root cause. |
| **CAMARA Number Verification** | POST /verify | Yes (1 tool) | Yes — via camaraproject | Verify subscriber identity during ticket creation. |

**Current mcp-telco-toolkit coverage for fault prediction: 3 of 9 APIs (and none of the core fault/performance ones).**

## The gap

The three most important APIs for fault prediction are TMF642 (alarms), TMF628 (performance metrics), and NWDAF AnalyticsInfo (predictions). None of these are in the mcp-telco-toolkit today. The toolkit covers subscriber-facing CAMARA APIs (SIM Swap, Number Verification, Device Status) and product catalog/ordering (TMF620, TMF622), which are useful for churn and revenue use cases but not for NOC fault workflows.

## Fault prediction workflow mapped to tools

A NOC engineer investigating a potential fault would follow this sequence:

```
Step 1: Get active alarms
  → TMF642: GET /alarm?state=raised&severity=critical,major
  → TMF642: GET /alarm/{id} (detail on specific alarm)

Step 2: Pull performance data for affected network elements
  → TMF628: GET /measurementCollectionJob (find existing collection jobs)
  → TMF628: POST /onDemandCollection (trigger ad-hoc measurement if needed)
  → TMF628: GET /trackingRecord (retrieve measurement results)

Step 3: Query NWDAF for analytics/predictions
  → NWDAF AnalyticsInfo: GET /analytics?event-id=ABNORMAL_BEHAVIOUR
  → NWDAF AnalyticsInfo: GET /analytics?event-id=LOAD_LEVEL_INFORMATION
  → NWDAF EventsSubscription: POST /subscriptions (subscribe to ongoing alerts)

Step 4: Check subscriber/device impact
  → CAMARA Device Status: GET connectivity status for affected devices
  → CAMARA Device Location: POST retrieve-location (locate affected devices)

Step 5: Correlate and decide
  → Model reasoning step (no API call — inference from steps 1-4)

Step 6: Create/update trouble ticket
  → TMF621: POST /troubleTicket (create with correlated evidence)
  → TMF621: PATCH /troubleTicket/{id} (update with resolution)
```

## Tools to build (Wave 1 scope)

Based on this mapping, the minimum set of new MCP tools for fault prediction:

### TMF642 Alarm Management (6 tools)
1. `tmf642_list_alarms` — GET /alarm with filters (state, severity, type, time range)
2. `tmf642_get_alarm` — GET /alarm/{id}
3. `tmf642_acknowledge_alarm` — PATCH /alarm/{id} (set ackState)
4. `tmf642_clear_alarm` — PATCH /alarm/{id} (set state=cleared)
5. `tmf642_add_comment` — PATCH /alarm/{id} (add comment)
6. `tmf642_subscribe_alarms` — POST /hub (subscribe to alarm events)

### TMF628 Performance Management (5 tools)
7. `tmf628_list_collection_jobs` — GET /measurementCollectionJob
8. `tmf628_create_on_demand_collection` — POST /onDemandCollection
9. `tmf628_get_collection_status` — GET /onDemandCollection/{id}
10. `tmf628_get_tracking_records` — GET /trackingRecord
11. `tmf628_get_tracking_record` — GET /trackingRecord/{id}

### NWDAF Analytics (3 tools)
12. `nwdaf_get_analytics` — GET /analytics (with event-id filter)
13. `nwdaf_subscribe_events` — POST /subscriptions
14. `nwdaf_unsubscribe_events` — DELETE /subscriptions/{id}

### TMF621 Trouble Ticket (4 tools)
15. `tmf621_create_ticket` — POST /troubleTicket
16. `tmf621_update_ticket` — PATCH /troubleTicket/{id}
17. `tmf621_get_ticket` — GET /troubleTicket/{id}
18. `tmf621_list_tickets` — GET /troubleTicket

### CAMARA Device Location (2 tools)
19. `camara_verify_location` — POST /verify-location
20. `camara_retrieve_location` — POST /retrieve-location

**Total: 20 new tools, bringing the fault prediction toolkit to 23 tools (20 new + 3 existing CAMARA).**

## OpenAPI spec sources

All specs needed for conversion to MCP tool definitions:

| API | Spec format | Location | License |
|-----|------------|----------|---------|
| TMF642 v5.0.1 | OAS 3.0 YAML | [tmforum-apis/TMF642_AlarmManagement](https://github.com/tmforum-apis/TMF642_AlarmManagement) | Apache 2.0 |
| TMF628 v4.0.0 | Swagger 2.0 JSON | [tmforum-apis/TMF628_Performance](https://github.com/tmforum-apis/TMF628_Performance) | Apache 2.0 |
| TMF621 v5.0.1 | OAS 3.0 YAML | [tmforum-apis/TMF621_TroubleTicket](https://github.com/tmforum-apis/TMF621_TroubleTicket) | Apache 2.0 |
| NWDAF AnalyticsInfo | OAS 3.0 YAML | [jdegre/5GC_APIs Rel-18](https://github.com/jdegre/5GC_APIs/blob/Rel-18/TS29520_Nnwdaf_AnalyticsInfo.yaml) | 3GPP spec |
| NWDAF EventsSubscription | OAS 3.0 YAML | [jdegre/5GC_APIs Rel-18](https://github.com/jdegre/5GC_APIs/blob/Rel-18/TS29520_Nnwdaf_EventsSubscription.yaml) | 3GPP spec |
| CAMARA DeviceLocation | OAS 3.0 YAML | [camaraproject/DeviceLocation](https://github.com/camaraproject/DeviceLocation) | Apache 2.0 |
| CAMARA DeviceStatus | OAS 3.0 YAML | [camaraproject/DeviceStatus](https://github.com/camaraproject/DeviceStatus) | Apache 2.0 |

TMF628 is Swagger 2.0 only (no v5 OAS 3.0 yet). The others have OAS 3.0 specs. @samchon/openapi handles both formats.

## Backend for execution-verified SDG

For fault prediction tool calls to run against something real:

- **TMF642/628/621:** No public live backends. Use Prism to auto-mock from the OpenAPI specs. TM Forum reference implementations (in each repo) also include mock servers.
- **NWDAF:** NextGCore implements TS 29.520 with ONNX-backed analytics. Deploy via Docker Compose. This gives real NWDAF responses.
- **CAMARA Device Status/Location:** Use operator sandboxes (GSMA Open Gateway, Vodafone, BT) or Prism mocks.

## OpenShift deployment

- MCP server (Node.js): runs anywhere, no OpenShift-specific work needed
- NextGCore (for NWDAF backend): has k8s/ directory, needs OpenShift adaptation (SCCs, SCTP)
- fenar/cnvopen5gcore: built for OpenShift, but no NWDAF — useful for general 5G context, not for NWDAF analytics
- Prism mock servers: run anywhere as containers
