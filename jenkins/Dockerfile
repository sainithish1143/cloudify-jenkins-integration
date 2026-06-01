FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3 \
       python3-pip \
       ca-certificates \
       curl \
       git \
       unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/cloudify-lifecycle-requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/cloudify-lifecycle-requirements.txt

COPY jenkins/plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

COPY jenkins/init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/

ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"

USER jenkins
