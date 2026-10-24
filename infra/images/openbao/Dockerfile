FROM busybox:latest
COPY bao /bin/bao
RUN mkdir -p /openbao/data /openbao/config && adduser -D -u 1000 openbao && chown -R openbao /openbao
USER openbao
ENTRYPOINT ["/bin/bao"]
