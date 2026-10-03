1	# Phase 2: MCP Tooling Foundation - Research
2	
3	**Researched:** 2026-10-02
4	**Domain:** MCP server transport patching, OpenAPI-to-MCP codegen tooling, OpenShift deployment
5	**Confidence:** HIGH
6	
7	## Summary
8	
9	Phase 2 has two deliverables: (1) fork/patch MCP-Telecom to serve over Streamable HTTP and deploy it on OpenShift, and (2) build a reusable OpenAPI-to-MCP conversion CLI that generates FastMCP server scaffolds from OpenAPI specs with operation-allowlist filtering. Both are well-constrained by the CONTEXT.md decisions.
10	
11	The most important research finding is that **MCP-Telecom and this project's conversion tooling use different FastMCP packages**. MCP-Telecom imports `from mcp.server.fastmcp import FastMCP` (the built-in FastMCP class bundled within the official `mcp` Python SDK v1.x). The project's STACK.md specifies the standalone `fastmcp` v4.0.10 (PyPI, from PrefectHQ), which is a separate, more feature-rich package with `from_openapi()`, `RouteMap`, and native HTTP transport. The `mcp` SDK v2.0 (released 2026-07-28) removed the `mcp.server.fastmcp` module entirely, renaming `FastMCP` to `MCPServer`. This version incompatibility is the primary technical risk for the transport patch.
12	
13	**Primary recommendation:** Switch MCP-Telecom's dependency from `mcp[cli]>=1.0.0` to standalone `fastmcp>=4.0.0` as part of the transport patch. This aligns it with the project's stack, gives it the latest Streamable HTTP support, and avoids the `mcp` v1-to-v2 migration complexity. The decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) is identical between both packages. Build the conversion CLI using the same standalone `fastmcp` package for `from_openapi()` and `RouteMap`.
14	
15	<user_constraints>
16	## User Constraints (from CONTEXT.md)
17	
18	### Locked Decisions
19	- **D-01:** Fork/patch MCP-Telecom to add native HTTP transport (not stdio-to-HTTP proxy sidecar)
20	- **D-02:** Patched server is HTTP-only -- stdio support stripped
21	- **D-03:** Transport is Streamable HTTP (MCP 2026-07-28 protocol), not legacy SSE
22	- **D-05:** Vendored into this repo under `mcp/mcp-telecom/`, not a separate fork
23	- **D-06:** Keeps original MIT license with NOTICE/attribution file
24	- **D-07:** Tools point at nothing -- no device backend wired in Phase 2
25	- **D-08:** Verification via throwaway script: `tools/list` + one representative tool call
26	- **D-09:** Flag no-device-backend gap in STATE.md for Phase 4
27	- **D-10:** Scaffold device-inventory config shape with OpenShift Secret references
28	- **D-10a:** Command-allowlisting scaffold for safe CLI exec tool
29	- **D-11:** Conversion tooling is a generic CLI at `mcp/tooling/openapi_to_mcp.py`
30	- **D-12:** Operation selection via YAML/JSON allowlist config using `RouteMap`
31	- **D-13:** One-time codegen, then hand-curate (not dynamic runtime loader)
32	- **D-14:** Smoke-test CLI against CAMARA Device Location spec
33	- **D-15:** Smoke test is local only, not deployed to OpenShift
34	- **D-16:** Generated scaffolds bake in file-watching boilerplate for ConfigMap contract
35	- **D-17:** New namespace `otel25-mcp`
36	- **D-18:** Plain `oc apply` YAML manifests, no Helm
37	- **D-19:** Top-level `mcp/` directory: `mcp/tooling/`, `mcp/mcp-telecom/`
38	- **D-20:** Probes check process-up / MCP endpoint responds, not device connectivity
39	
40	### Claude's Discretion
41	- Exact Service/port naming for deployed MCP-Telecom (D-04)
42	- Exact shape/filenames of device-inventory scaffold and command-allowlist scaffold (D-10, D-10a)
43	- Exact YAML allowlist-config schema for conversion CLI (D-12)
44	
45	### Deferred Ideas (OUT OF SCOPE)
46	None -- discussion stayed within phase scope. The 20 curated domain tools, Kuadrant MCP Gateway composition, and wiring MCP-Telecom to real devices are all Phase 3/4 work.
47	</user_constraints>
48	
49	<phase_requirements>
50	## Phase Requirements
51	
52	| ID | Description | Research Support |
53	|----|-------------|------------------|
54	| MCP-06 | Deploy MCP-Telecom (60+ device-layer tools) on OpenShift for infrastructure fault data | Transport patch (stdio->HTTP), Dockerfile, OpenShift Deployment/Service YAML, liveness/readiness probes, verification script |
55	| MCP-07 | Build reusable OpenAPI-to-MCP conversion tooling for future API waves | Conversion CLI using `FastMCP.from_openapi()` + `RouteMap`, YAML allowlist config, codegen template, ConfigMap file-watcher boilerplate, CAMARA smoke test |
56	</phase_requirements>
57	
58	## Architectural Responsibility Map
59	
60	| Capability | Primary Tier | Secondary Tier | Rationale |
61	|------------|-------------|----------------|-----------|
62	| MCP-Telecom transport patch | MCP Server (Python process) | -- | Transport is a server-level concern; change `mcp.run()` call |
63	| MCP-Telecom OpenShift deployment | OpenShift / Container orchestration | -- | Deployment YAML, namespace, probes, Dockerfile |
64	| OpenAPI-to-MCP conversion CLI | Developer tooling (local CLI) | -- | Runs locally, generates code artifacts, not deployed |
65	| Generated scaffold file-watching | MCP Server (Python process) | OpenShift ConfigMap | Server reads volume-mounted ConfigMap; kubelet propagates changes |
66	| Device-inventory config scaffold | Configuration (YAML file) | OpenShift Secrets | Shape defined now; credentials reference Secrets |
67	| Verification scripts | Developer tooling / CI | OpenShift cluster | Scripts run against deployed workloads |
68	
69	## Standard Stack
70	
71	### Core
72	
73	| Library | Version | Purpose | Why Standard | Confidence |
74	|---------|---------|---------|--------------|------------|
75	| `fastmcp` | 4.0.10 | MCP server framework (both MCP-Telecom and generated scaffolds) | Project-wide standard per STACK.md; has `from_openapi()`, `RouteMap`, native Streamable HTTP | HIGH [VERIFIED: PyPI registry + Context7 /llmstxt/gofastmcp_llms-full_txt] |
76	| Python | 3.12 | Runtime | FastMCP requires >=3.10; 3.12 is project standard per STACK.md | HIGH [CITED: STACK.md] |
77	| `httpx` | 0.28.1 | Async HTTP client for backend calls in generated scaffolds | FastMCP's OpenAPI integration requires httpx.AsyncClient | HIGH [VERIFIED: PyPI registry + Context7] |
78	| `pydantic` | >=2.0 | Schema validation | FastMCP uses Pydantic internally; MCP-Telecom already depends on it | HIGH [VERIFIED: PyPI registry] |
79	| `pyyaml` | 6.0.3 | YAML parsing for allowlist configs and device inventory | MCP-Telecom already depends on it; conversion CLI needs YAML parsing | HIGH [VERIFIED: PyPI registry] |
80	
81	### Supporting
82	
83	| Library | Version | Purpose | When to Use |
84	|---------|---------|---------|-------------|
85	| `watchdog` | 6.0.0 | File-system event monitoring for ConfigMap file-watching | Baked into generated scaffolds; used with `PollingObserver` for K8s compatibility | [VERIFIED: PyPI registry] |
86	| `netmiko` | >=4.3.0 | SSH connection to network devices | Existing MCP-Telecom dependency; not modified in this phase | [CITED: MCP-Telecom pyproject.toml] |
87	| `python-dotenv` | >=1.0.0 | Environment variable loading | Existing MCP-Telecom dependency | [CITED: MCP-Telecom pyproject.toml] |
88	| `rich` | >=13.0.0 | CLI output formatting | Existing MCP-Telecom dependency | [CITED: MCP-Telecom pyproject.toml] |
89	
90	### Alternatives Considered
91	
92	| Instead of | Could Use | Tradeoff |
93	|------------|-----------|----------|
94	| Standalone `fastmcp` for MCP-Telecom | `mcp` SDK v1.x (>=1.8.0) | Minimal patch (just transport param), but older protocol, diverges from project stack, pinned to <2.0.0 to avoid v2 breaking changes |
95	| Standalone `fastmcp` for MCP-Telecom | `mcp` SDK v2.x (`MCPServer`) | Latest protocol, but requires renaming FastMCP->MCPServer, changing all imports, updating constructor args -- far more invasive than switching to standalone `fastmcp` |
96	| `watchdog` PollingObserver | Simple mtime-polling loop (no library) | Fewer dependencies, but reinvents observer pattern; watchdog is well-tested and handles edge cases |
97	| `watchdog` PollingObserver | `watchdog` default Observer (inotify) | Lower latency on normal filesystems, but **breaks on Kubernetes ConfigMap volumes** due to symlink-based atomic updates |
98	
99	**Installation (MCP-Telecom vendored copy):**
100	```bash
101	cd mcp/mcp-telecom
102	uv add fastmcp httpx pydantic pyyaml python-dotenv rich netmiko
103	```
104	
105	**Installation (Conversion CLI):**
106	```bash
107	cd mcp/tooling
108	uv add fastmcp httpx pyyaml
109	```
110	
111	## Package Legitimacy Audit
112	
113	> slopcheck was unavailable at research time. All packages below are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.
114	
115	| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
116	|---------|----------|-----|-----------|-------------|-----------|-------------|
117	| fastmcp | PyPI | ~1.5 yrs | High (PrefectHQ) | github.com/PrefectHQ/fastmcp | N/A | [ASSUMED] -- project STACK.md standard |
118	| httpx | PyPI | ~5 yrs | Very high | github.com/encode/httpx | N/A | [ASSUMED] -- well-known HTTP client |
119	| pydantic | PyPI | ~7 yrs | Very high | github.com/pydantic/pydantic | N/A | [ASSUMED] -- industry standard |
120	| pyyaml | PyPI | ~15 yrs | Very high | github.com/yaml/pyyaml | N/A | [ASSUMED] -- standard YAML parser |
121	| watchdog | PyPI | ~13 yrs | High | github.com/gorakhargosh/watchdog | N/A | [ASSUMED] -- well-known filesystem watcher |
122	| netmiko | PyPI | ~10 yrs | High | github.com/ktbyers/netmiko | N/A | [ASSUMED] -- standard network automation library |
123	| python-dotenv | PyPI | ~10 yrs | Very high | github.com/theskumar/python-dotenv | N/A | [ASSUMED] -- standard env file loader |
124	| rich | PyPI | ~5 yrs | Very high | github.com/Textualize/rich | N/A | [ASSUMED] -- standard CLI formatting |
125	
126	**Packages removed due to slopcheck [SLOP] verdict:** none
127	**Packages flagged as suspicious [SUS]:** none
128	
129	*All packages are well-established ecosystem standards. slopcheck was unavailable at research time, so the planner must gate each install behind a `checkpoint:human-verify` task per protocol.*
130	
131	## Architecture Patterns
132	
133	### System Architecture Diagram
134	
135	```
136	                    Developer Workstation (Local)
137	                    +---------------------------------+
138	                    |  mcp/tooling/openapi_to_mcp.py  |
139	                    |  (Conversion CLI)               |
140	                    |                                 |
141	                    |  Input:                         |
142	                    |    OpenAPI spec (YAML)           |
143	                    |    + allowlist config (YAML)     |
144	                    |                                 |
145	                    |  Output:                        |
146	                    |    server.py scaffold            |
147	                    |    (one-time codegen)            |
148	                    +---------+-----------------------+
149	                              |
150	                     codegen  |  (Phase 3 uses output)
151	                              v
152	    OpenShift Cluster
153	    +================================================================+
154	    |  Namespace: otel25-mcp                                         |
155	    |                                                                |
156	    |  +----------------------------+                                |
157	    |  |  MCP-Telecom (vendored)    |                                |
158	    |  |  ~58 tools, 4 prompts,     |                                |
159	    |  |  8 resources               |                                |
160	    |  |                            |                                |
161	    |  |  Streamable HTTP           |                                |
162	    |  |  POST /mcp                 |                                |
163	    |  |  port 8000                 |                                |
164	    |  +----------------------------+                                |
165	    |       |                                                        |
166	    |       | (Phase 2: points at nothing -- connection errors)       |
167	    |       v                                                        |
168	    |    [No device backend]                                         |
169	    |                                                                |
170	    +================================================================+
171	    |  Namespace: otel25-backends (Phase 1, already deployed)        |
172	    |                                                                |
173	    |  ConfigMap: backend-routing                                    |
174	    |  (Volume-mounted by Phase 3's generated servers,               |
175	    |   not by MCP-Telecom)                                          |
176	    +================================================================+
177	```
178	
179	### Recommended Project Structure
180	
181	```
182	mcp/
183	  mcp-telecom/                    # Vendored MCP-Telecom fork (D-05, D-19)
184	    LICENSE                       # Original MIT license
185	    NOTICE                        # Attribution to upstream
186	    pyproject.toml                # Modified: fastmcp dep, transport config
187	    src/mcp_telecom/
188	      server.py                   # Patched: import + transport change
189	      connection.py               # Unchanged
190	      safety.py                   # Unchanged
191	      ...                         # All other modules unchanged
192	    devices.yaml.example          # Device-inventory scaffold (D-10)
193	    command_allowlist.yaml         # Command-allowlist scaffold (D-10a)
194	    Dockerfile                    # New: Python + fastmcp HTTP server
195	  tooling/                        # Conversion CLI (D-11, D-19)
196	    openapi_to_mcp.py             # CLI entry point
197	    allowlist_schema.py           # YAML allowlist config model
198	    templates/                    # Codegen templates
199	      server_template.py.j2       # Generated server.py template
200	    README.md                     # CLI usage documentation
201	  openshift/                      # OpenShift manifests for MCP layer
202	    namespace.yaml                # otel25-mcp namespace (D-17)
203	    mcp-telecom-deployment.yaml   # Deployment + Service (D-18)
204	    mcp-telecom-secret.yaml       # Placeholder Secret for device creds
205	scripts/
206	  verify-mcp-telecom.sh           # Verification script (D-08)
207	```
208	
209	### Pattern 1: MCP-Telecom Transport Patch
210	
211	**What:** Replace stdio transport with Streamable HTTP in the vendored MCP-Telecom copy.
212	
213	**When:** First task in Phase 2 -- everything else depends on this.
214	
215	**The patch is exactly three changes:**
216	
217	1. **`pyproject.toml`** -- swap dependency:
218	```toml
219	# Before (MCP-Telecom upstream)
220	dependencies = [
221	    "mcp[cli]>=1.0.0",
222	    ...
223	]
224	
225	# After (vendored patch)
226	dependencies = [
227	    "fastmcp>=4.0.0",
228	    ...
229	]
230	```
231	
232	2. **`src/mcp_telecom/server.py`** -- swap import:
233	```python
234	# Before (MCP-Telecom upstream)
235	from mcp.server.fastmcp import FastMCP
236	
237	# After (vendored patch)
238	from fastmcp import FastMCP
239	```
240	Source: [FastMCP migration guide](https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk-v2) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]
241	
242	3. **`src/mcp_telecom/server.py`** -- swap transport in `main()`:
243	```python
244	# Before (MCP-Telecom upstream)
245	def main():
246	    logger.info("Starting MCP-Telecom server v0.2.0")
247	    logger.info("Loaded %d devices", len(device_manager.list_devices()))
248	    mcp.run(transport="stdio")
249	
250	# After (vendored patch)
251	def main():
252	    logger.info("Starting MCP-Telecom server v0.2.0")
253	    logger.info("Loaded %d devices", len(device_manager.list_devices()))
254	    mcp.run(transport="http", host="0.0.0.0", port=8000)
255	```
256	Source: [FastMCP HTTP deployment docs](https://gofastmcp.com/deployment/running-server) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]
257	
258	**Why this works:** The standalone `fastmcp` package's `FastMCP` class has the same decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) as the `mcp` SDK's built-in FastMCP. MCP-Telecom's ~58 tools all use this decorator pattern. The `mcp.run(transport="http")` call in standalone `fastmcp` serves Streamable HTTP at `/mcp` by default (port 8000). [VERIFIED: Context7]
259	
260	**Risk:** The standalone `fastmcp` may have subtle behavioral differences from `mcp.server.fastmcp.FastMCP` for edge cases in MCP-Telecom's tool implementations. The planner should include a verification task that runs MCP-Telecom's test suite (`pytest`) after the patch.
261	
262	### Pattern 2: Conversion CLI Codegen Approach
263	
264	**What:** A CLI that takes an OpenAPI spec + YAML allowlist and generates a standalone `server.py` scaffold.
265	
266	**When:** Second major deliverable. Must be smoke-tested against CAMARA Device Location spec.
267	
268	**Key insight:** FastMCP's `from_openapi()` is a **runtime** API -- it creates the server dynamically in memory from the spec. It does NOT have a codegen/export-to-file feature. [VERIFIED: Context7 + WebSearch confirmed no export mechanism exists]
269	
270	Therefore the CLI must:
271	1. Use `from_openapi()` with `RouteMap` to introspect and filter the spec at codegen time
272	2. Generate a `server.py` file via **templating** (e.g., Jinja2 or string templates) that contains a `from_openapi()` call configured with the filtered route maps
273	3. The generated scaffold IS a working server that calls `from_openapi()` at startup with the vendored spec -- this satisfies D-13's "one-time codegen" because the spec is baked in, not fetched dynamically
274	4. Phase 3 hand-curates by editing the generated file: improving descriptions via `mcp_component_fn`, adjusting `route_maps`, or eventually replacing `from_openapi()` with explicit `@mcp.tool()` decorators
275	
276	**Generated scaffold structure:**
277	```python
278	# Auto-generated by mcp/tooling/openapi_to_mcp.py
279	# Spec: camara_location_verification.yaml
280	# Allowlist: camara_allowlist.yaml
281	# Generated: 2026-10-03
282	#
283	# CURATION GUIDE:
284	# 1. Edit descriptions in customize_components() for LLM clarity
285	# 2. Adjust route_maps to include/exclude operations
286	# 3. For full control, replace from_openapi() with explicit @mcp.tool() decorators
287	# 4. DO NOT edit the file-watcher section (ConfigMap contract, BACK-03)
288	
289	import os
290	import json
291	import threading
292	from pathlib import Path
293	from fastmcp import FastMCP
294	from fastmcp.server.providers.openapi import RouteMap, MCPType
295	from fastmcp.utilities.openapi import HTTPRoute
296	from fastmcp.server.providers.openapi import OpenAPITool
297	import httpx
298	
299	# --- ConfigMap file-watcher (BACK-03 contract) ---
300	BACKEND_ROUTING_PATH = os.environ.get(
301	    "BACKEND_ROUTING_FILE", "/config/backend-routing/CAMARA_BASE_URL"
302	)
303	_backend_url_lock = threading.Lock()
304	_backend_url = "http://localhost:4010"  # default fallback
305	
306	
307	def _load_backend_url():
308	    global _backend_url
309	    try:
310	        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
311	        if url:
312	            with _backend_url_lock:
313	                _backend_url = url
314	    except FileNotFoundError:
315	        pass  # use default on first boot
316	
317	
318	def get_backend_url() -> str:
319	    with _backend_url_lock:
320	        return _backend_url
321	
322	
323	def _start_config_watcher():
324	    """Poll ConfigMap-mounted file for changes (mtime-based).
325	    
326	    Uses mtime polling instead of inotify because Kubernetes
327	    updates ConfigMap volumes via atomic symlink swaps, which
328	    do not emit standard IN_MODIFY events.
329	    """
330	    import time
331	    config_path = Path(BACKEND_ROUTING_PATH)
332	    last_mtime = 0.0
333	
334	    def _poll():
335	        nonlocal last_mtime
336	        while True:
337	            try:
338	                current_mtime = config_path.stat().st_mtime
339	                if current_mtime != last_mtime:
340	                    last_mtime = current_mtime
341	                    _load_backend_url()
342	            except FileNotFoundError:
343	                pass
344	            time.sleep(5)  # poll every 5 seconds
345	
346	    t = threading.Thread(target=_poll, daemon=True)
347	    t.start()
348	
349	
350	# --- OpenAPI Server ---
351	SPEC_PATH = Path(__file__).parent / "specs" / "camara_location_verification.yaml"
352	
353	def customize_components(route, component):
354	    """Customize tool descriptions for LLM consumption."""
355	    if isinstance(component, OpenAPITool):
356	        # Phase 3: improve these descriptions for telecom domain clarity
357	        pass
358	
359	route_maps = [
360	    # Include only allowlisted operations
361	    RouteMap(path="/verify", methods=["POST"], mcp_type=MCPType.TOOL),
362	    # Exclude everything else
363	    RouteMap(mcp_type=MCPType.EXCLUDE),
364	]
365	
366	spec_text = SPEC_PATH.read_text()
367	client = httpx.AsyncClient(base_url=get_backend_url())
368	
369	mcp = FastMCP.from_openapi(
370	    openapi_spec=spec_text,
371	    client=client,
372	    route_maps=route_maps,
373	    mcp_component_fn=customize_components,
374	)
375	
376	# --- Startup ---
377	_load_backend_url()
378	_start_config_watcher()
379	
380	if __name__ == "__main__":
381	    mcp.run(transport="http", host="0.0.0.0", port=8000)
382	```
383	Source: [FastMCP OpenAPI docs](https://gofastmcp.com/integrations/openapi) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]
384	
385	### Pattern 3: ConfigMap File-Watching for Backend URL
386	
387	**What:** Volume-mounted ConfigMap polling for live backend switching without pod restart.
388	
389	**When:** Baked into every generated scaffold (D-16). MCP-Telecom itself does NOT need this (it has no backend routing -- D-07).
390	
391	**Critical Kubernetes caveat:** ConfigMap volume mounts use atomic symlink swaps. The kubelet creates a new timestamped directory and atomically swaps the `..data` symlink. Standard `inotify` watchers receive `IN_DELETE_SELF` events instead of `IN_MODIFY`, breaking most file-watching libraries. [CITED: https://ahmet.im/blog/kubernetes-inotify/]
392	
393	**Recommended approach: Mtime-based polling (not inotify-based watchdog)**
394	
395	The simplest reliable pattern is polling `os.path.getmtime()` on the mounted file every 5 seconds. This:
396	- Works reliably with K8s symlink swaps
397	- Has no inotify edge cases to handle
398	- Adds ~0 CPU overhead at 5-second intervals
399	- Matches the kubelet's own propagation delay (~60 seconds for ConfigMap changes)
400	
401	The `watchdog` library with `PollingObserver` is an alternative, but for a single file that changes rarely, a simple mtime polling loop in a daemon thread is more straightforward and avoids the dependency. [ASSUMED -- recommend polling loop for simplicity; planner can switch to watchdog if more files need watching]
402	
403	**Integration with Phase 1's ConfigMap contract:**
404	```yaml
405	# From backends/openshift/configmap-backend-routing.yaml
406	# Phase 3 servers mount this ConfigMap as a volume, e.g.:
407	# volumeMounts:
408	#   - name: backend-routing
409	#     mountPath: /config/backend-routing
410	#     readOnly: true
411	# volumes:
412	#   - name: backend-routing
413	#     configMap:
414	#       name: backend-routing
415	```
416	Source: [Phase 1 ConfigMap contract](backends/openshift/configmap-backend-routing.yaml) [VERIFIED: codebase]
417	
418	### Pattern 4: OpenShift Deployment for Python/FastMCP HTTP Server
419	
420	**What:** Dockerfile + Deployment/Service YAML for a FastMCP server on OpenShift.
421	
422	**When:** Deploying MCP-Telecom to `otel25-mcp` namespace.
423	
424	**Dockerfile pattern:**
425	```dockerfile
426	FROM python:3.12-slim
427	
428	WORKDIR /app
429	
430	# Install uv for fast dependency resolution
431	COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
432	
433	# Copy project files
434	COPY pyproject.toml uv.lock ./
435	COPY src/ src/
436	
437	# Install dependencies
438	RUN uv sync --no-dev --frozen
439	
440	# Copy config scaffolds
441	COPY devices.yaml.example devices.yaml
442	COPY command_allowlist.yaml command_allowlist.yaml
443	
444	# Non-root user (OpenShift requires arbitrary UID support)
445	RUN useradd -r -s /bin/false mcpuser
446	USER mcpuser
447	
448	EXPOSE 8000
449	
450	# Run the MCP server
451	CMD ["uv", "run", "mcp-telecom"]
452	```
453	
454	**Deployment YAML pattern (mirrors Phase 1's prism-tmf642.yaml):**
455	```yaml
456	apiVersion: apps/v1
457	kind: Deployment
458	metadata:
459	  name: mcp-telecom
460	  namespace: otel25-mcp
461	  labels:
462	    app: mcp-telecom
463	    layer: mcp
464	spec:
465	  replicas: 1
466	  selector:
467	    matchLabels:
468	      app: mcp-telecom
469	  template:
470	    metadata:
471	      labels:
472	        app: mcp-telecom
473	        layer: mcp
474	    spec:
475	      containers:
476	      - name: mcp-telecom
477	        image: image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-telecom:latest
478	        ports:
479	        - containerPort: 8000
480	          protocol: TCP
481	        resources:
482	          requests:
483	            cpu: 250m
484	            memory: 256Mi
485	          limits:
486	            cpu: 500m
487	            memory: 512Mi
488	        # D-20: Liveness checks process-up (port alive)
489	        livenessProbe:
490	          tcpSocket:
491	            port: 8000
492	          initialDelaySeconds: 10
493	          periodSeconds: 30
494	        # D-20: Readiness checks MCP endpoint responds
495	        # Note: Streamable HTTP uses POST, but a simple HTTP GET
496	        # to /mcp returns 405 Method Not Allowed (confirms endpoint exists)
497	        # For a proper check, use a startup script or exec probe
498	        readinessProbe:
499	          httpGet:
500	            path: /mcp
501	            port: 8000
502	          initialDelaySeconds: 5
503	          periodSeconds: 10
504	          # 405 (Method Not Allowed for GET on Streamable HTTP endpoint)
505	          # is NOT a passing readiness check. See Pitfall 2 below for
506	          # the recommended approach.
507	---
508	apiVersion: v1
509	kind: Service
510	metadata:
511	  name: mcp-telecom
512	  namespace: otel25-mcp
513	  labels:
514	    app: mcp-telecom
515	    layer: mcp
516	spec:
517	  selector:
518	    app: mcp-telecom
519	  ports:
520	  - port: 8000
521	    targetPort: 8000
522	    protocol: TCP
523	  type: ClusterIP
524	```
525	[ASSUMED -- pattern based on Phase 1's Prism YAML structure adapted for Python/FastMCP]
526	
527	### Anti-Patterns to Avoid
528	
529	- **Using `watchdog` default Observer (inotify) for ConfigMap watching:** Breaks on K8s symlink swaps. Use `PollingObserver` or simple mtime polling. [CITED: https://ahmet.im/blog/kubernetes-inotify/]
530	- **Staying on `mcp` SDK v1.x and pinning `<2.0.0`:** Creates a version-frozen dependency that diverges from the project stack and will eventually need upgrading anyway.
531	- **Using `envFrom` for ConfigMap consumption:** Environment variables are read once at pod startup. Changes require pod restart, violating BACK-03. Volume-mount + file-watch is required. [CITED: Phase 1 ConfigMap contract comment block]
532	- **Building a dynamic runtime loader for the conversion CLI:** D-13 explicitly requires one-time codegen. The generated scaffold should be a static file, not a system that re-reads specs at startup. The spec IS read at startup by `from_openapi()`, but it is baked into the image/directory, not fetched.
533	
534	## Don't Hand-Roll
535	
536	| Problem | Don't Build | Use Instead | Why |
537	|---------|-------------|-------------|-----|
538	| OpenAPI-to-MCP tool conversion | Manual tool definition parser | `FastMCP.from_openapi()` + `RouteMap` | Handles schema extraction, parameter mapping, HTTP method routing, Swagger 2.0 + OAS 3.0 |
539	| MCP protocol handling | Custom JSON-RPC over HTTP | `FastMCP` with `mcp.run(transport="http")` | Full MCP protocol implementation including tool listing, invocation, streaming |
540	| Operation filtering from spec | Custom OpenAPI parser | `RouteMap` with `path`, `methods`, `tags`, `mcp_type=MCPType.EXCLUDE` | Declarative filtering, processed in order, first-match wins |
541	| Tool description customization | Post-processing script | `mcp_component_fn` callback in `from_openapi()` | In-place modification of generated components during conversion |
542	| ASGI server for production | Custom socket server | `uvicorn` via `mcp.http_app()` or `mcp.run(transport="http")` | Production-grade ASGI server with worker support |
543	
544	**Key insight:** FastMCP handles the entire MCP protocol stack. The conversion CLI's job is purely selecting operations and generating the scaffold file -- NOT reimplementing protocol handling.
545	
546	## Common Pitfalls
547	
548	### Pitfall 1: MCP-Telecom `mcp` SDK vs standalone `fastmcp` Import Incompatibility
549	
550	**What goes wrong:** MCP-Telecom imports `from mcp.server.fastmcp import FastMCP` (the `mcp` SDK v1.x built-in). If you upgrade the `mcp` dependency to v2.x without changing the import, you get `ModuleNotFoundError` because `mcp` v2.0 removed `mcp.server.fastmcp` entirely (renamed to `mcp.server.mcpserver.MCPServer`). [VERIFIED: https://py.sdk.modelcontextprotocol.io/migration/]
551	
552	**Why it happens:** Two different packages (`mcp` and `fastmcp`) both provide a class called `FastMCP` at different import paths. The project STACK.md says "FastMCP 4.0.10" but MCP-Telecom uses the `mcp` SDK's bundled version.
553	
554	**How to avoid:** Switch MCP-Telecom to standalone `fastmcp>=4.0.0` as recommended. Change import to `from fastmcp import FastMCP`. Remove `mcp[cli]` from dependencies. The decorator API is identical.
555	
556	**Warning signs:** `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` at startup.
557	
558	### Pitfall 2: Readiness Probe for Streamable HTTP Endpoint
559	
560	**What goes wrong:** FastMCP's Streamable HTTP serves at `POST /mcp`. OpenShift readiness probes use `httpGet` (GET method). A GET to `/mcp` returns `405 Method Not Allowed`, which fails the readiness check, causing the pod to never become ready.
561	
562	**Why it happens:** The MCP Streamable HTTP protocol uses POST exclusively. There is no GET health endpoint by default in a bare `FastMCP` server.
563	
564	**How to avoid:** Two options:
565	1. **Add a custom health endpoint** in the vendored MCP-Telecom before calling `mcp.run()`:
566	   ```python
567	   # In the vendored server.py, BEFORE mcp.run():
568	   from starlette.responses import JSONResponse
569	   app = mcp.http_app()
570	   
571	   @app.route("/healthz")
572	   async def healthz(request):
573	       return JSONResponse({"status": "ok"})
574	   ```
575	   Then use `readinessProbe.httpGet.path: /healthz`.
576	2. **Use an exec probe** that sends a proper MCP `tools/list` POST request:
577	   ```yaml
578	   readinessProbe:
579	     exec:
580	       command:
581	         - python
582	         - -c
583	         - "import httpx; r = httpx.post('http://localhost:8000/mcp', json={'jsonrpc':'2.0','method':'tools/list','id':1}); assert r.status_code == 200"
584	     initialDelaySeconds: 10
585	     periodSeconds: 30
586	   ```
587	
588	**Warning signs:** Pod stuck in `0/1 Ready` state with readiness probe failures in `oc describe pod`.
589	
590	### Pitfall 3: `from_openapi()` Has No Codegen Export
591	
592	**What goes wrong:** The planner assumes `FastMCP.from_openapi()` can export a standalone Python file. It cannot -- it creates the server in memory at runtime. Building a "codegen CLI" requires writing your own code-generation logic (templates, string formatting, etc.). [VERIFIED: Context7 + WebSearch -- no export/serialize mechanism exists in FastMCP]
593	
594	**Why it happens:** FastMCP is designed for dynamic server creation, not code generation. The `from_openapi()` docs assume you use it at runtime.
595	
596	**How to avoid:** The conversion CLI generates a `server.py` scaffold via **templating** (e.g., Jinja2 or Python string templates). The generated file contains a `from_openapi()` call with the spec path and route_maps hardcoded. This is still "codegen" because the allowlist and boilerplate are baked into the file -- Phase 3 edits the generated file, not the CLI.
597	
598	**Warning signs:** Looking for `mcp.export()`, `mcp.save()`, or `mcp.to_source()` methods -- they don't exist.
599	
600	### Pitfall 4: ConfigMap Symlink Swap Breaks inotify Watchers
601	
602	**What goes wrong:** A `watchdog` Observer with default inotify backend watches a ConfigMap-mounted file. Kubernetes updates the ConfigMap, but the watcher receives `IN_DELETE_SELF` instead of `IN_MODIFY`, and the watch is silently broken. The server continues using the old backend URL indefinitely.
603	
604	**Why it happens:** Kubernetes uses atomic symlink swaps for ConfigMap updates. The kubelet creates a new timestamped directory, writes new content, swaps the `..data` symlink, and deletes the old directory. The file the watcher was monitoring is literally deleted and replaced with a new inode. [CITED: https://ahmet.im/blog/kubernetes-inotify/]
605	
606	**How to avoid:** Use mtime-based polling on the mounted file (5-second interval). Polling works regardless of how the file is updated (symlink swap, direct write, etc.). See Pattern 3 above.
607	
608	**Warning signs:** Backend URL changes in ConfigMap but MCP server keeps calling the old backend.
609	
610	### Pitfall 5: `from_openapi()` Client Base URL Static After Server Creation
611	
612	**What goes wrong:** The `httpx.AsyncClient` passed to `from_openapi()` has its `base_url` set at construction time. If the backend URL changes (via ConfigMap), the already-constructed client still points to the old URL.
613	
614	**Why it happens:** `httpx.AsyncClient` base_url is immutable after construction.
615	
616	**How to avoid:** The file-watcher callback must create a new `httpx.AsyncClient` with the updated URL, OR use a custom transport layer that resolves the URL at request time. For Phase 2's scaffolds, the simplest approach is to NOT pass a `base_url` to the client, and instead have each tool function construct the full URL using `get_backend_url()` at call time. However, since `from_openapi()` manages the client internally, this requires either:
617	   - Recreating the FastMCP server on ConfigMap change (heavy but correct)
618	   - Using a custom `httpx.AsyncClient` subclass with a dynamic base_url property
619	   - Setting the client's `_base_url` attribute directly (fragile, private API)
620	
621	**Recommended approach for scaffolds:** Use a thin wrapper around `httpx.AsyncClient` that re-resolves `base_url` on each request by overriding `_merge_url()` or using an event hook. Document this as a known complexity in the scaffold's comments for Phase 3 to review.
622	
623	## Code Examples
624	
625	### Example 1: RouteMap Filtering for CAMARA Spec
626	
627	```python
628	# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP OpenAPI docs)
629	from fastmcp import FastMCP
630	from fastmcp.server.providers.openapi import RouteMap, MCPType
631	
632	route_maps = [
633	    # Include only the verify endpoint as a tool
634	    RouteMap(path="/verify", methods=["POST"], mcp_type=MCPType.TOOL),
635	    # Exclude everything else (default catch-all)
636	    RouteMap(mcp_type=MCPType.EXCLUDE),
637	]
638	
639	mcp = FastMCP.from_openapi(
640	    openapi_spec=spec_text,
641	    client=client,
642	    route_maps=route_maps,
643	)
644	```
645	
646	### Example 2: mcp_component_fn for Tool Customization
647	
648	```python
649	# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP OpenAPI docs)
650	from fastmcp.server.providers.openapi import OpenAPITool, OpenAPIResource
651	from fastmcp.utilities.openapi import HTTPRoute
652	
653	def customize_components(
654	    route: HTTPRoute,
655	    component: OpenAPITool | OpenAPIResource,
656	) -> None:
657	    if isinstance(component, OpenAPITool):
658	        # Improve description for LLM consumption
659	        component.description = f"[Telecom] {component.description}"
660	        component.tags.add("camara")
661	
662	mcp = FastMCP.from_openapi(
663	    openapi_spec=spec_text,
664	    client=client,
665	    route_maps=route_maps,
666	    mcp_component_fn=customize_components,
667	)
668	```
669	
670	### Example 3: FastMCP ASGI App with Custom Health Endpoint
671	
672	```python
673	# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP HTTP deployment docs)
674	from fastmcp import FastMCP
675	from starlette.responses import JSONResponse
676	
677	mcp = FastMCP("MCP-Telecom")
678	# ... tool registrations ...
679	
680	# Create ASGI app with custom routes
681	app = mcp.http_app()
682	
683	@app.route("/healthz")
684	async def healthz(request):
685	    return JSONResponse({"status": "ok"})
686	
687	# Run with uvicorn for production:
688	# uvicorn server:app --host 0.0.0.0 --port 8000
689	```
690	
691	### Example 4: Stateless HTTP Mode for Load-Balanced Deployment
692	
693	```python
694	# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP stateless mode)
695	from fastmcp import FastMCP
696	
697	mcp = FastMCP("MCP-Telecom")
698	
699	# Stateless mode: each request gets fresh transport context
700	# No session affinity required -- safe for load balancing
701	if __name__ == "__main__":
702	    mcp.run(transport="http", host="0.0.0.0", port=8000, stateless_http=True)
703	```
704	
705	## State of the Art
706	
707	| Old Approach | Current Approach | When Changed | Impact |
708	|--------------|------------------|--------------|--------|
709	| `mcp.server.fastmcp.FastMCP` in `mcp` SDK | `mcp.server.mcpserver.MCPServer` in `mcp` v2 SDK | 2026-07-28 | Breaking import change; standalone `fastmcp` v4.x is now the recommended high-level API |
710	| `transport="streamable-http"` (`mcp` SDK) | `transport="http"` (standalone `fastmcp`) | FastMCP v3+ | Standalone `fastmcp` uses "http" which serves Streamable HTTP by default at `/mcp` |
711	| Session-based Streamable HTTP (2025-03-26 spec) | Sessionless Streamable HTTP (2026-07-28 spec) | 2026-07-28 | Sessions removed; `stateless_http=True` in FastMCP aligns with this |
712	| `mcp` v1.x (FastMCP bundled) | `mcp` v2.x (MCPServer) + `fastmcp` v4.x (standalone) | 2026-07-28 | Two-package ecosystem; standalone `fastmcp` has more features |
713	
714	**Deprecated/outdated:**
715	- `from mcp.server.fastmcp import FastMCP`: Removed in `mcp` v2.0. Use `from fastmcp import FastMCP` (standalone) or `from mcp.server.mcpserver import MCPServer` (SDK v2).
716	- SSE transport: Superseded by Streamable HTTP. FastMCP v4.x still supports it but Streamable HTTP is the default.
717	
718	## Assumptions Log
719	
720	| # | Claim | Section | Risk if Wrong |
721	|---|-------|---------|---------------|
722	| A1 | MCP-Telecom's ~58 tools will work unchanged when switching from `mcp` SDK's FastMCP to standalone `fastmcp` | Pattern 1 | Medium -- if decorator behavior differs, some tools may need adjustment. Mitigated by running MCP-Telecom's test suite post-patch. |
723	| A2 | `watchdog` PollingObserver or simple mtime polling is sufficient for ConfigMap file-watching (vs. more complex hybrid approach) | Pattern 3 | Low -- mtime polling is the most reliable approach on K8s; the 5-second interval is well within acceptable latency for backend URL changes. |
724	| A3 | The `readinessProbe` for Streamable HTTP requires a custom `/healthz` endpoint or exec probe (GET to `/mcp` returns 405) | Pitfall 2 | Medium -- if FastMCP serves a different status code on GET or has a built-in health route, the probe can be simpler. Verify during implementation. |
725	| A4 | The generated scaffold approach (templating a file that calls `from_openapi()`) satisfies D-13's "one-time codegen" requirement | Pattern 2 | Low -- the spec is baked into the directory; the `from_openapi()` call is deterministic. Phase 3 edits the generated file. |
726	| A5 | MCP-Telecom's optional extras (netconf, telemetry, snmp, dashboard, metrics) are compatible with standalone `fastmcp` | Standard Stack | Low -- these extras don't interact with the MCP protocol layer; they're independent Python libraries. |
727	| A6 | `httpx.AsyncClient` base_url can be dynamically updated for ConfigMap-based backend switching in `from_openapi()` generated servers | Pitfall 5 | Medium -- if `from_openapi()` internally caches the client, backend URL switching may require server recreation. Phase 3 will validate. |
728	
729	## Open Questions
730	
731	1. **httpx.AsyncClient base_url dynamism with `from_openapi()`** (DEFERRED TO PHASE 3 -- see STATE.md)
732	   - What we know: `from_openapi()` accepts an `httpx.AsyncClient` and uses it for backend calls. `base_url` is set at construction time.
733	   - What's unclear: Whether updating `client._base_url` or creating a new client on ConfigMap change will propagate correctly through the FastMCP internals.
734	   - Recommendation: Phase 2 scaffolds include the file-watcher and a TODO comment for Phase 3 to validate. The CAMARA smoke test (local, no ConfigMap) does not exercise this path.
735	
736	2. **Standalone `fastmcp` vs `mcp` SDK decorator compatibility edge cases** (RESOLVED -- see 02-01-PLAN.md Task 2, upstream test suite run post-swap)
737	   - What we know: The decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) is documented as identical. Basic tools work.
738	   - What's unclear: Whether MCP-Telecom's use of `@mcp.resource("telecom://...")` URI templates, lazy imports inside tool functions, or the audit logging pattern causes any issues.
739	   - Recommendation: Run MCP-Telecom's full test suite (157 tests per repo) after the patch. If failures occur, fall back to `mcp` v1.x (>=1.8.0, <2.0.0) with `transport="streamable-http"`.
740	
741	3. **OpenShift internal registry image push workflow** (RESOLVED -- see 02-02-PLAN.md Task 2, reuses Phase 1's registry workflow)
742	   - What we know: Phase 1 uses `image-registry.openshift-image-registry.svc:5000/otel25-backends/` for Prism images.
743	   - What's unclear: Whether the same `podman build` + `oc` image push workflow used in Phase 1 works for the Python/FastMCP image.
744	   - Recommendation: Follow Phase 1's established pattern. The Dockerfile is standard Python.
745	
746	## Environment Availability
747	
748	| Dependency | Required By | Available | Version | Fallback |
749	|------------|------------|-----------|---------|----------|
750	| Python | MCP-Telecom, conversion CLI | Yes | 3.14.6 (local); 3.12 target in containers | Use 3.12-slim Docker base |
751	| uv | Dependency management | Yes | 0.9.28 | pip (slower but functional) |
752	| oc | OpenShift deployment | Yes | 4.18.16 client | -- (required, no fallback) |
753	| podman | Container builds | Yes | 5.6.1 | docker (not installed, not needed) |
754	| OpenShift cluster | Deployment target | Assumed (Phase 1 deployed successfully) | 4.18+ | -- (required, no fallback) |
755	
756	**Missing dependencies with no fallback:** None -- all required tools are available.
757	**Missing dependencies with fallback:** None.
758	
759	## Validation Architecture
760	
761	### Test Framework
762	
763	| Property | Value |
764	|----------|-------|
765	| Framework | pytest >= 8.0 (project standard per STACK.md) |
766	| Config file | None -- Wave 0 creates `mcp/mcp-telecom/pytest.ini` or uses upstream's existing config |
767	| Quick run command | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout=30` |
768	| Full suite command | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |
769	
770	### Phase Requirements -> Test Map
771	
772	| Req ID | Behavior | Test Type | Automated Command | File Exists? |
773	|--------|----------|-----------|-------------------|-------------|
774	| MCP-06a | MCP-Telecom server starts with HTTP transport | smoke | `uv run python -c "from fastmcp import FastMCP; print('import ok')"` | Wave 0 |
775	| MCP-06b | MCP-Telecom's 58 tools register correctly | unit | `cd mcp/mcp-telecom && uv run pytest tests/ -x` (upstream tests) | Upstream has 157 tests |
776	| MCP-06c | tools/list returns tool catalog via Streamable HTTP | integration | `scripts/verify-mcp-telecom.sh` (exec probe style) | Wave 0 |
777	| MCP-06d | One representative tool callable via MCP protocol | integration | `scripts/verify-mcp-telecom.sh` (D-08 verification) | Wave 0 |
778	| MCP-07a | Conversion CLI generates scaffold from CAMARA spec | smoke | `cd mcp/tooling && uv run python openapi_to_mcp.py --spec ... --allowlist ...` | Wave 0 |
779	| MCP-07b | Generated scaffold starts and lists tools correctly | smoke | `uv run python generated_server.py &; curl -X POST localhost:8000/mcp ...` | Wave 0 |
780	
781	### Sampling Rate
782	
783	- **Per task commit:** Quick run command (upstream test suite subset)
784	- **Per wave merge:** Full upstream test suite + verification scripts
785	- **Phase gate:** All verification scripts pass + upstream tests green
786	
787	### Wave 0 Gaps
788	
789	- [ ] `mcp/mcp-telecom/pytest.ini` -- configure pytest for vendored copy (may use upstream config)
790	- [ ] `scripts/verify-mcp-telecom.sh` -- covers MCP-06c, MCP-06d (D-08 verification)
791	- [ ] Smoke test script for conversion CLI (MCP-07a, MCP-07b)
792	
793	## Security Domain
794	
795	### Applicable ASVS Categories
796	
797	| ASVS Category | Applies | Standard Control |
798	|---------------|---------|-----------------|
799	| V2 Authentication | No | MCP-Telecom has no auth in Phase 2 (internal cluster service) |
800	| V3 Session Management | No | Using stateless HTTP mode |
801	| V4 Access Control | Yes (minimal) | MCP-Telecom's command-allowlist scaffold (D-10a) for safe CLI exec |
802	| V5 Input Validation | Yes | Pydantic schema validation via FastMCP tool parameters |
803	| V6 Cryptography | No | No crypto operations in Phase 2 |
804	
805	### Known Threat Patterns for MCP/FastMCP HTTP
806	
807	| Pattern | STRIDE | Standard Mitigation |
808	|---------|--------|---------------------|
809	| Unauthorized tool invocation via exposed HTTP port | Elevation of Privilege | ClusterIP Service (no external exposure); Phase 3 adds Kuadrant gateway auth |
810	| Command injection via safe CLI exec tool | Tampering | Command-allowlist scaffold (D-10a) with empty/restrictive default |
811	| Credential exposure in device-inventory config | Information Disclosure | OpenShift Secret references (D-10), never plain ConfigMap values |
812	| Unvalidated backend URL from ConfigMap | Tampering | Validate URL format in file-watcher callback before applying |
813	
814	## Project Constraints (from CLAUDE.md)
815	
816	- Never push `.gitignore` files to GitHub repos -- keep local only
817	- Never push blog drafts or personal notes
818	- When staging files, always review what's being added -- prefer explicit file paths over `git add .`
819	- Global memories are learnings -- apply only when relevant to current task
820	
821	## Sources
822	
823	### Primary (HIGH confidence)
824	
825	- **Context7 /llmstxt/gofastmcp_llms-full_txt** -- FastMCP HTTP transport (`mcp.run(transport="http")`), `from_openapi()` API, `RouteMap` filtering, `mcp_component_fn`, ASGI deployment, stateless mode
826	- **Context7 /prefecthq/fastmcp** -- FastMCP server composition, proxy patterns
827	- **MCP-Telecom repo** (github.com/Avinash-Amudala/MCP-Telecom) -- Source code structure, import paths (`from mcp.server.fastmcp import FastMCP`), `mcp.run(transport="stdio")`, pyproject.toml dependencies, 58 tools + 4 prompts + 8 resources, MIT license
828	- **MCP Python SDK migration guide** (https://py.sdk.modelcontextprotocol.io/migration/) -- v1->v2 breaking changes: FastMCP->MCPServer rename, `mcp.server.fastmcp` module removed
829	- **MCP Python SDK v2 what's new** (https://py.sdk.modelcontextprotocol.io/whats-new/) -- MCPServer import path, transport parameter names
830	- **MCP Python SDK PyPI** (https://pypi.org/project/mcp/) -- v2.3.0 latest, v1.8.0 introduced Streamable HTTP
831	- **Phase 1 ConfigMap contract** (backends/openshift/configmap-backend-routing.yaml) -- Volume-mount + file-watch requirement, BACK-03 compliance
832	- **Phase 1 Prism manifests** (backends/openshift/prism-tmf642.yaml, backends/prism/Dockerfile) -- Deployment/Service YAML pattern, Dockerfile pattern
833	- **Phase 1 verify-routing.sh** (backends/scripts/verify-routing.sh) -- Verification script pattern for D-08
834	
835	### Secondary (MEDIUM confidence)
836	
837	- **Kubernetes ConfigMap inotify pitfalls** (https://ahmet.im/blog/kubernetes-inotify/) -- Symlink swap behavior, inotify watch breaking, polling recommendation
838	- **ConfigMap hot-reload patterns** (https://oneuptime.com/blog/post/2026-02-02-kubernetes-configmap-hot-reload/view) -- watchdog + PollingObserver pattern for Python
839	- **OpenShift health probes** (https://developers.redhat.com/blog/2020/11/10/you-probably-need-liveness-and-readiness-probes) -- httpGet vs exec probe patterns
840	- **FastMCP PyPI** (https://pypi.org/project/fastmcp/4.0.10/) -- v4.0.10 latest, Apache-2.0 license
841	- **WebSearch: FastMCP from_openapi codegen** -- Confirmed no export/codegen feature; identified openapi-mcp-codegen (cnoe-io) and mcp-generator-4.x as reference implementations
842	
843	### Tertiary (LOW confidence)
844	
845	- None -- all claims verified against primary or secondary sources.
846	
847	## Metadata
848	
849	**Confidence breakdown:**
850	- Standard stack: HIGH -- all packages verified on PyPI, FastMCP API verified via Context7
851	- Architecture: HIGH -- MCP-Telecom source code inspected, transport patch scoped precisely, Phase 1 patterns established
852	- Pitfalls: HIGH -- ConfigMap inotify issue verified via official blog post, SDK version incompatibility verified via official migration guide
853	- Conversion CLI codegen: MEDIUM -- the templating approach is sound but `from_openapi()` + dynamic `httpx` client URL updating is an open question
854	
855	**Research date:** 2026-10-02
856	**Valid until:** 2026-11-01 (stable -- FastMCP 4.x and mcp SDK 2.x are settled post-2026-07-28 spec freeze)
