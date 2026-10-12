# SDG pipeline image -- bakes sdg_hub + this repo's sdg/ package together so
# KFP pipeline components run `python3 -m sdg.scripts.<script>` exactly like
# sdg-dry-run-job.yaml's Kubernetes Job did, but without a pip install step
# on every pod start (that Job's `pip install` at runtime was fine for a
# single manual Job, but KFP pipeline steps run far more often during
# development/iteration and should start fast and not depend on PyPI being
# reachable from every step).
#
# Build context must be the repo root (needs sdg/ at the top level):
#   oc new-build --binary --name=sdg-pipeline -n otel25-sdg --strategy=docker
#   oc start-build sdg-pipeline --from-dir=. -n otel25-sdg --follow
# (pushes to the internal registry ImageStream image-registry.openshift-image-registry.svc:5000/otel25-sdg/sdg-pipeline:latest,
# referenced directly by sdg/pipelines/sdg_production_pipeline.py's component base_image.)

FROM python:3.12-slim

# OpenShift runs containers under an arbitrary, dynamically-assigned UID with
# no entry in /etc/passwd, and HOME is unset -- pip (and anything else that
# wants to write a per-user cache/config dir) needs HOME pointed at a
# world-writable path or installs fail with permission errors. Confirmed
# live this session via sdg-dry-run-job.yaml needing the same env var.
ENV HOME=/tmp
WORKDIR /opt/app-root/src

RUN pip install --no-cache-dir \
    "sdg-hub==0.9.4" \
    jsonschema \
    pyyaml \
    pandas \
    requests \
    "kfp==2.9.0"

COPY sdg/ ./sdg/

# KFP pipeline steps (and OpenShift generally) run containers under an
# arbitrary, dynamically-assigned UID that is always a member of group 0 --
# COPY leaves files owned by root:root with no group-write bit, so a fresh
# ephemeral pipeline pod (no PVC, unlike sdg-dry-run-job.yaml) can't create
# sdg/data/seeds/ to write materialized seeds into. Standard OpenShift
# "support arbitrary user IDs" fix: make group 0 permissions match owner.
RUN chgrp -R 0 /opt/app-root/src && chmod -R g=u /opt/app-root/src

ENTRYPOINT ["python3"]
