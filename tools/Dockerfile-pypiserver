# docker build -t embercsi/pypiserver -f tools/Dockerfile-pypiserver .
# docker run -d --rm --name pypiserver -p 12345:8080  embercsi/pypiserver
FROM alpine
RUN apk add --no-cache python2 py2-pip && \
    pip install --no-cache-dir pypiserver && \
    mkdir -p /packages && \
    rm -rf /var/cache/apk/*

ENTRYPOINT ["pypi-server", "-p", "8080", "-P", ".", "-a", ""]
CMD ["/packages"]
