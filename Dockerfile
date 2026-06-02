FROM python:3.11-slim
WORKDIR /workspace
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY . /workspace
ENTRYPOINT ["python3"]
CMD ["scripts/manual_lifecycle_from_deployment.py", "--deployment", "deployments/wr-demo-jenkins-hello-dev.yaml", "--action", "create-environment"]
