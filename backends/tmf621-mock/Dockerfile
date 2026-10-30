# Stateful TMF621 Trouble Ticket mock (replaces static Prism for TMF621).
# Build context: backends/ (same binary-build context as the Prism images)
#   oc start-build tmf621-mock --from-dir=backends/ -n <namespace>
FROM python:3.12-slim

WORKDIR /app
COPY tmf621-mock/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY tmf621-mock/app.py ./

# OpenShift arbitrary-UID support
RUN chgrp -R 0 /app && chmod -R g=u /app
ENV PYTHONDONTWRITEBYTECODE=1
USER 1001

EXPOSE 4010
CMD ["python", "app.py"]
