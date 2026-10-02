# Parameterized Prism mock server image
# Build context: backends/ directory
# Usage: podman build --build-arg SPEC_FILE=specs/<spec-file> -f prism/Dockerfile -t prism-<api> backends/
#
# Per D-04 (use Prism), D-06 (vendor specs into repo, bake into images per RESEARCH.md Pattern 1),
# D-08 (dynamic schema-based mock generation, bind 0.0.0.0)

FROM stoplight/prism:5

# Accept the spec file path as a build argument (relative to build context)
ARG SPEC_FILE
RUN test -n "$SPEC_FILE" || (echo "ERROR: SPEC_FILE build arg is required" && exit 1)

# Bake the vendored spec into the image (D-06: no network fetch at deploy time)
COPY ${SPEC_FILE} /specs/api.yaml

# Production mode avoids processing log overhead (RESEARCH.md anti-pattern)
ENV NODE_ENV=production

# Prism entrypoint
ENTRYPOINT ["node", "dist/index.js"]

# Dynamic mode generates varied responses from schema (D-08)
# Bind to 0.0.0.0 so the mock is reachable from outside the container (D-08, RESEARCH.md anti-pattern)
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "--dynamic", "-m", "false", "/specs/api.yaml"]
