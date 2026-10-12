# Vendored OpenAPI Spec Manifest

Downloaded: 2026-10-02 (CAMARA Device Status specs added 2026-10-12)

## Spec Sources

| File | Source | Version/Branch | Commit SHA | Pinning |
|------|--------|---------------|------------|---------|
| tmf642_alarm_v5.0.1.oas.yaml | tmforum-apis/TMF642_AlarmManagement | main (no v5.0.1 tag) | 1dcbfa183c4674678853ba02ecd3178ba534e527 | SHA-pinned |
| tmf628_performance_v4.0.0.swagger.json | tmforum-apis/TMF628_Performance | main (no v4.0.0 tag) | f958e5c2831aa61286e9356282cf451b16e7a5d2 | SHA-pinned |
| tmf621_troubleticket_v5.0.1.oas.yaml | tmforum-apis/TMF621_TroubleTicket | main (no v5.0.1 tag) | cd24d2357e28501b4ab0def951150639443c0058 | SHA-pinned |
| camara_location_verification.yaml | camaraproject/DeviceLocation | r3.2 (release tag) | N/A | Tag-pinned |
| camara_location_retrieval.yaml | camaraproject/DeviceLocation | r3.2 (release tag) | N/A | Tag-pinned |
| camara_device_roaming_status.yaml | camaraproject/DeviceStatus | r2.2 (release tag) | N/A | Tag-pinned |
| camara_device_reachability_status.yaml | camaraproject/DeviceStatus | r2.2 (release tag) | N/A | Tag-pinned |
| camara_connected_network_type.yaml | camaraproject/DeviceStatus | r2.2 (release tag) | N/A | Tag-pinned |
| nwdaf_analyticsinfo_rel16.yaml | jdegre/5GC_APIs | Rel-16 (frozen branch) | N/A | Branch-pinned |
| nwdaf_eventssubscription_rel16.yaml | jdegre/5GC_APIs | Rel-16 (frozen branch) | N/A | Branch-pinned |
| nwdaf_analyticsinfo_bundled.yaml | Derived from nwdaf_analyticsinfo_rel16.yaml | v1.1.5 (TS 29.520 V16.12.0) | N/A | Derived (see Notes) |

## Notes

- TMF repos do not publish release tags matching spec versions. Specs downloaded from main branch; commit SHAs recorded above for reproducibility.
- CAMARA DeviceLocation and DeviceStatus specs pinned to release tags (r3.2 and r2.2 respectively, both immutable).
- CAMARA Device Status r2.2 bundles 6 API definitions (3 query APIs + 3 matching event-subscription APIs). Only the 3 query APIs (device-roaming-status, device-reachability-status, connected-network-type) were vendored -- the subscription variants are webhook/notification-based, not request/response tool-calling shapes, and were out of scope for this server (same reasoning CAMARA DeviceLocation's own subscription-style operations were never wrapped).
- CAMARA Device Status specs ship with realistic named `examples` for every response already (multiple named cases per 200 response, e.g. roaming by country code, reachability by connectivity type, connected network generation) -- no enrichment needed, unlike the Phase 4 TMF/CAMARA DeviceLocation specs which required manual enrichment to avoid Prism's Lorem-Ipsum dynamic-mode output.
- NWDAF specs pinned to Rel-16 frozen release branch (3GPP release freeze).
- TMF628 is Swagger 2.0 JSON format (not OAS 3.0). Mocked as-is.
- All other specs are OAS 3.0 YAML format.
- `nwdaf_analyticsinfo_bundled.yaml` is derived from `nwdaf_analyticsinfo_rel16.yaml` with all external `$ref` links (TS29571, TS29510, TS29503, TS29554) inlined for Prism mock compatibility. Regenerate by re-bundling the rel16 source when the upstream spec changes.
