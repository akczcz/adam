FROM busybox:latest
COPY spire-server spire-agent /opt/spire/bin/
RUN mkdir -p /opt/spire/conf /run/spire
ENV PATH=/opt/spire/bin:$PATH
