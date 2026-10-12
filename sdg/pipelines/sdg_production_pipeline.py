"""KFP (Kubeflow / OpenShift AI Data Science Pipelines) definition for the
SDG production pipeline: generate tool-calling examples per tier (with the
tool-coverage rejection-sampling gate, see 04-LEARNINGS.md 2026-10-09),
report tool coverage, and run the three-stage evaluation + OSFT delivery.

Runs against the `sdg-dspa` DataSciencePipelinesApplication in `otel25-sdg`
(sdg/openshift/sdg-dspa.yaml), with artifacts stored in the Garage
S3-compatible bucket wired as that DSPA's externalStorage
(sdg/openshift/garage.yaml) -- every declared Output[Dataset]/Output[Artifact]
below is uploaded there automatically by the KFP driver, which is what
makes a pipeline run's raw examples, coverage report, and delivery files
all independently inspectable/downloadable from the RHOAI Dashboard's
Pipelines > Runs > Artifacts view after the fact, not just from pod logs.

One task per tier (2026-10-09, 04-LEARNINGS.md): the original design ran all
5 tiers inside a single `generate_examples` step. KFP only uploads a step's
artifacts once the whole step finishes, so a failure deep into tier 4 or 5
(confirmed live: an EmptyDatasetError from a coverage-gate resample killed a
run hours in) lost every earlier tier's output too, forcing a full restart.
Splitting into `generate_tier(tier=...)` called once per TIERS entry means
each tier's raw_output is its own artifact, persisted independently --
a later tier's failure no longer erases earlier tiers' work. Tier tasks are
chained sequentially via `.after()` (not run in parallel) on purpose: they
all hit the same shared vLLM/Langflow backend, and parallelizing 5 tiers on
top of `GENERATION_MAX_CONCURRENCY` (already raised from 1 to 4 within a
single tier, see run-generation.py) would stack two untested concurrency
changes at once. Revisit removing `.after()` for a speed win only after this
sequential-but-resilient shape has proven out.

All steps use the same pre-built image (sdg/openshift/Dockerfile), which
bakes sdg_hub + this repo's sdg/ package together -- see that Dockerfile's
header comment for the build/push commands.

Usage (compile only):
    python -m sdg.pipelines.sdg_production_pipeline

Usage (compile and submit a run):
    python -m sdg.pipelines.sdg_production_pipeline --submit \\
        --host https://<sdg-dspa-api-server-route> --token $(oc whoami -t)
"""
import argparse

from kfp import dsl, compiler, kubernetes
from kfp.dsl import Artifact, Dataset, Input, Output

# Built via: oc new-build --binary --name=sdg-pipeline -n otel25-sdg --strategy=docker
#            oc start-build sdg-pipeline --from-dir=. -n otel25-sdg --follow
# (build context = repo root, see sdg/openshift/Dockerfile)
IMAGE = "image-registry.openshift-image-registry.svc:5000/otel25-sdg/sdg-pipeline:latest"

# Fixed curriculum tiers (sdg/config/seed-scenarios.yaml) -- one generate_tier
# task per entry, known at pipeline-definition time (not a runtime list), so
# each gets its own named output artifact rather than a dynamic ParallelFor
# collection.
TIERS = ["single_tool", "parallel", "sequential", "multi_turn", "closed_loop"]

# Secret names already present in otel25-sdg (same ones sdg-dry-run-job.yaml
# and the mcp-token-refresher CronJob use) -- not created by this pipeline.
_CLIENT_SECRET_SECRET = "keycloak-client-secret-sdg-pipeline"
_VLLM_KEY_SECRET = "maas-rhdp-api-key"
_LANGFLOW_KEY_SECRET = "langflow-api-key-sdg-pipeline"

# PipelineTask.set_env_variable() only accepts literal str values in this kfp
# version (kfp/dsl/pipeline_task.py), not dynamic pipeline-parameter
# references the way container command/args placeholders do -- so unlike
# gateway_url/keycloak_url/client_id below (genuine per-run knobs, wired as
# pipeline parameters), these two are fixed per-cluster serving endpoints and
# are plain constants, matching sdg-dry-run-job.yaml's hardcoded env vars.
_VLLM_API_BASE = "https://ai-inference.apps.cluster-qbq4v.qbq4v.sandbox2667.opentlc.com/models/redhataigemma-4-31b-it/v1"
_LANGFLOW_URL = "http://langflow-service-backend.otel25-sdg.svc.cluster.local:7860/api/v1/run/90d9df0e-6bdd-465b-8064-385998b1a437"


@dsl.container_component
def generate_tier(
    tier: str,
    gateway_url: str,
    keycloak_url: str,
    client_id: str,
    raw_output: Output[Dataset],
):
    """Materialize seeds from the live MCP Gateway and run the
    mcp_distillation_training flow for a single curriculum tier, gated by
    the tool-coverage rejection-sampling filter in run-generation.py's
    _run_generation(). Seed materialization re-runs per tier task (cheap --
    a single gateway call) rather than being a separate shared step, trading
    a few redundant seconds for not needing an extra artifact-passing hop.
    """
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python3", "-m", "sdg.scripts.run-generation"],
        args=[
            "--tiers", tier,
            "--output-dir", raw_output.path,
            "--gateway-url", gateway_url,
            "--keycloak-url", keycloak_url,
            "--client-id", client_id,
        ],
    )


@dsl.container_component
def coverage_report(
    raw_single_tool: Input[Dataset],
    raw_parallel: Input[Dataset],
    raw_sequential: Input[Dataset],
    raw_multi_turn: Input[Dataset],
    raw_closed_loop: Input[Dataset],
    report: Output[Artifact],
):
    """Cross-reference every generated row's actual tool trace against its
    scenario's intended_tools (sdg/config/seed-scenarios.yaml), producing
    the JSON+Markdown report this project uses for both pipeline QA and
    blog/documentation purposes (04-LEARNINGS.md, 2026-10-09).

    Takes one Input[Dataset] per tier (rather than a single merged input)
    since each tier now lands as its own independent artifact -- concatenates
    them here. `2>/dev/null || true` per tier directory: a tier whose every
    scenario ended up in coverage_failed (none accepted) legitimately has no
    *_raw.jsonl file, which must not fail the whole report.
    """
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["sh", "-c"],
        args=[
            'set -e; '
            'for d in "$1" "$2" "$3" "$4" "$5"; do cat "$d"/*_raw.jsonl 2>/dev/null || true; done '
            '> /tmp/all_tiers_raw.jsonl; '
            'python3 -m sdg.scripts.tool_coverage_report '
            '--input /tmp/all_tiers_raw.jsonl '
            '--seed-scenarios sdg/config/seed-scenarios.yaml '
            '--output-dir "$6"',
            "coverage_report",  # $0 -- script name, unused, required by sh -c's arg convention
            raw_single_tool.path,  # $1
            raw_parallel.path,  # $2
            raw_sequential.path,  # $3
            raw_multi_turn.path,  # $4
            raw_closed_loop.path,  # $5
            report.path,  # $6
        ],
    )


@dsl.container_component
def evaluate_and_deliver(
    raw_single_tool: Input[Dataset],
    raw_parallel: Input[Dataset],
    raw_sequential: Input[Dataset],
    raw_multi_turn: Input[Dataset],
    raw_closed_loop: Input[Dataset],
    filtered_output: Output[Dataset],
    delivery_output: Output[Dataset],
):
    """Three-stage verification (format/execution/semantic), OSFT schema
    validation, and dual-format (single-turn + multi-turn) serialization --
    sdg_hub's mcp_distillation_evaluation flow plus run-evaluation.py's
    column-mapping and validation steps (D-02, amended D-04, D-20).

    run-evaluation.py's --input-dir expects one directory containing all
    *_raw.jsonl files, so the five per-tier artifacts are merged into a
    scratch directory first (copy, not cat -- OSFT evaluation reads whole
    files, unlike coverage_report's single-stream concatenation).
    """
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["sh", "-c"],
        args=[
            'set -e; mkdir -p /tmp/merged_raw; '
            'for d in "$1" "$2" "$3" "$4" "$5"; do cp "$d"/*_raw.jsonl /tmp/merged_raw/ 2>/dev/null || true; done; '
            'python3 -m sdg.scripts.run-evaluation '
            '--input-dir /tmp/merged_raw --output-dir "$6" --delivery-dir "$7"',
            "evaluate_and_deliver",  # $0
            raw_single_tool.path,  # $1
            raw_parallel.path,  # $2
            raw_sequential.path,  # $3
            raw_multi_turn.path,  # $4
            raw_closed_loop.path,  # $5
            filtered_output.path,  # $6
            delivery_output.path,  # $7
        ],
    )


def _wire_env(task: dsl.PipelineTask) -> dsl.PipelineTask:
    """Attach the plain env vars + secret-backed env vars every generation/
    evaluation step needs -- both LLMChatBlocks (teacher model) and the
    AgentBlock (Langflow) read these from flow-training.yaml/
    flow-evaluation.yaml's ${VAR:-default} placeholders, not CLI args.
    """
    task = task.set_env_variable("VLLM_API_BASE", _VLLM_API_BASE)
    task = task.set_env_variable("LANGFLOW_URL", _LANGFLOW_URL)
    task = kubernetes.use_secret_as_env(
        task,
        secret_name=_CLIENT_SECRET_SECRET,
        secret_key_to_env={"CLIENT_SECRET": "CLIENT_SECRET"},
    )
    task = kubernetes.use_secret_as_env(
        task,
        secret_name=_VLLM_KEY_SECRET,
        secret_key_to_env={"api-key": "VLLM_API_KEY"},
    )
    task = kubernetes.use_secret_as_env(
        task,
        secret_name=_LANGFLOW_KEY_SECRET,
        secret_key_to_env={"LANGFLOW_API_KEY": "LANGFLOW_API_KEY"},
    )
    return task


@dsl.pipeline(
    name="sdg-production-pipeline",
    description=(
        "Generate telecom tool-calling training examples per tier "
        "(tool-coverage gated, one artifact per tier), report coverage, "
        "and run three-stage evaluation + OSFT delivery. See "
        ".planning/phases/04-sdg-pipeline-and-dataset-production/"
        "04-LEARNINGS.md for the rejection-sampling and per-tier-split "
        "design rationale."
    ),
)
def sdg_production_pipeline(
    gateway_url: str = "https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp",
    keycloak_url: str = "https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com",
    client_id: str = "sdg-pipeline",
):
    tier_tasks: dict[str, dsl.PipelineTask] = {}
    previous_task = None
    for tier in TIERS:
        t = generate_tier(
            tier=tier,
            gateway_url=gateway_url,
            keycloak_url=keycloak_url,
            client_id=client_id,
        )
        # Caching ON (2026-10-10, 04-LEARNINGS.md): a resubmitted run with
        # identical tier/gateway_url/keycloak_url/client_id inputs will skip
        # a tier that already succeeded in a prior run, instead of redoing
        # it -- this is what "restart after an unrelated infra failure
        # (Langflow's disk filling up) shouldn't redo tiers 1-2" actually
        # requires, since KFP has no separate resume-from-failure mechanism
        # and TIERS is a fixed compile-time list, not a runtime parameter.
        # Tradeoff, accepted deliberately: a genuine from-scratch regeneration
        # later (new seeds, changed gateway tools, intentionally different
        # sampling) will also hit this cache and silently return old data
        # unless caching is turned back off first or some input is changed.
        # Only applied to generate_tier -- coverage_report/evaluate_and_deliver
        # stay uncached (cheap, no live-model cost, always want fresh output
        # reflecting whatever tier artifacts actually exist).
        t.set_caching_options(True)
        t.set_cpu_request("250m").set_cpu_limit("1").set_memory_request("512Mi").set_memory_limit("1Gi")
        _wire_env(t)
        # Sequential on purpose -- see module docstring. Each tier has no
        # data dependency on the previous one; .after() is a pure ordering
        # constraint so all 5 don't hit the shared vLLM/Langflow backend
        # concurrently.
        if previous_task is not None:
            t.after(previous_task)
        tier_tasks[tier] = t
        previous_task = t

    raw_outputs = {tier: tier_tasks[tier].outputs["raw_output"] for tier in TIERS}

    # Coverage report and evaluation both only need the five tiers' raw
    # outputs -- they run in parallel with each other (coverage reporting
    # doesn't gate delivery; it's a documentation/QA artifact, not a
    # correctness filter -- the actual filtering already happened inside
    # each generate_tier task via the rejection-sampling gate).
    coverage_task = coverage_report(
        raw_single_tool=raw_outputs["single_tool"],
        raw_parallel=raw_outputs["parallel"],
        raw_sequential=raw_outputs["sequential"],
        raw_multi_turn=raw_outputs["multi_turn"],
        raw_closed_loop=raw_outputs["closed_loop"],
    )
    coverage_task.set_caching_options(False)

    evaluate_task = evaluate_and_deliver(
        raw_single_tool=raw_outputs["single_tool"],
        raw_parallel=raw_outputs["parallel"],
        raw_sequential=raw_outputs["sequential"],
        raw_multi_turn=raw_outputs["multi_turn"],
        raw_closed_loop=raw_outputs["closed_loop"],
    )
    evaluate_task.set_caching_options(False)
    evaluate_task.set_cpu_request("250m").set_cpu_limit("1").set_memory_request("512Mi").set_memory_limit("1Gi")
    _wire_env(evaluate_task)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="sdg/pipelines/sdg_production_pipeline.yaml",
        help="Where to write the compiled pipeline IR YAML.",
    )
    parser.add_argument("--submit", action="store_true", help="Submit a run after compiling.")
    parser.add_argument("--host", default=None, help="DSPA API server route (required with --submit).")
    parser.add_argument("--token", default=None, help="Bearer token, e.g. $(oc whoami -t) (required with --submit).")
    parser.add_argument(
        "--experiment", default="sdg-production", help="KFP experiment name to run under (--submit only)."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "Force every generate_tier task to re-run even if a prior run with identical "
            "tier/gateway_url/keycloak_url/client_id inputs is cached (--submit only). "
            "Needed when the backends/MCP tools changed but the pipeline's own inputs did not "
            "-- otherwise set_caching_options(True) on generate_tier (04-LEARNINGS.md, "
            "2026-10-10) silently reuses stale per-tier outputs instead of re-generating."
        ),
    )
    args = parser.parse_args()

    compiler.Compiler().compile(sdg_production_pipeline, args.output)
    print(f"Compiled pipeline IR written to {args.output}")

    if args.submit:
        if not args.host or not args.token:
            raise SystemExit("--submit requires both --host and --token")
        import kfp

        # verify_ssl=False: the in-cluster kube-rbac-proxy sidecar in front of the DSPA API
        # server (sdg/openshift/sdg-dspa-submit-rbac.yaml) serves a self-signed cert -- not
        # the cluster's service-ca -- so TLS verification fails even for an in-cluster caller.
        client = kfp.Client(host=args.host, existing_token=args.token, verify_ssl=False)
        run = client.create_run_from_pipeline_package(
            args.output,
            arguments={},
            experiment_name=args.experiment,
            enable_caching=False if args.no_cache else None,
        )
        print(f"Submitted run: {run.run_id}")


if __name__ == "__main__":
    main()
