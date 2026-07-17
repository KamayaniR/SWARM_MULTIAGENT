FROM python:3.11-slim

# Test deps the generated code + pytest runs need (unchanged from the local
# Docker sandbox image).
RUN pip install --no-cache-dir pytest click pandas requests pyyaml requests-mock responses

# The in-container HTTP agent (see sandbox/agent_server.py). On Akash there is
# no Docker socket, so the orchestrator talks to this over HTTP instead.
COPY agent_server.py /opt/agent_server.py

ENV SANDBOX_WORKSPACE=/workspace \
    SANDBOX_AGENT_PORT=8080
WORKDIR /workspace
EXPOSE 8080

CMD ["python", "/opt/agent_server.py"]
