# Parameterized Prism mock server image
# Build context: backends/ directory
# Usage: podman build --build-arg SPEC_FILE=specs/<spec-file> -f prism/Dockerfile -t prism-<api> backends/
#
# Per D-04 (use Prism), D-06 (vendor specs into repo, bake into images per RESEARCH.md Pattern 1)

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

# Static (example-based) mode, NOT --dynamic: Pitfall #3 / D-08 / D-16 documented
# Prism's dynamic mode as "merely unrealistic" (Lorem-Ipsum-style values in
# otherwise-correct fields). In practice, for schemas with oneOf/discriminator
# polymorphism (e.g. CAMARA's Circle/Polygon Area, Device identifier union),
# dynamic mode goes further and fabricates WRONG STRUCTURE: garbled property
# names in place of real ones (e.g. "center"/"radius" replaced by "et_0e_"/
# "tempor36"), missing required nested objects, and areaType/device-identifier
# flip-flopping per call regardless of the request. That's not safe input for
# execution-verified SDG -- it actively teaches the model incorrect API
# contracts, not just unrealistic values. Static mode returns one of the
# spec's vendored named examples verbatim (schema-correct, but identical
# across calls). D-16's planned mitigation (enrich specs with realistic
# examples) is still the right long-term fix for variety; until that's done,
# static mode is the safe default -- correctness over per-call variety.
# Bind to 0.0.0.0 so the mock is reachable from outside the container (RESEARCH.md anti-pattern)
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "-m", "false", "/specs/api.yaml"]
