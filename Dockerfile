FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
ARG INSTALL_EXIFTOOL=1
RUN if [ "$INSTALL_EXIFTOOL" = "1" ]; then \
      sed -i "s|http://deb.debian.org|https://deb.debian.org|g" /etc/apt/sources.list.d/debian.sources && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=60 update && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=60 install -y --no-install-recommends libimage-exiftool-perl && \
      rm -rf /var/lib/apt/lists/*; fi
WORKDIR /app
COPY wheelhouse/ /wheels/
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-index --no-deps --only-binary=:all: --find-links /wheels --require-hashes -r /tmp/requirements.lock && rm -rf /wheels /tmp/requirements.lock
COPY app/ /app/
RUN chmod -R a+rX /app
LABEL org.opencontainers.image.source="https://github.com/xingyunshijie/carddock"
LABEL org.opencontainers.image.title="CardDock 影像归仓 NAS"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai \
    SOURCE_ROOTS=/sources MANUAL_SOURCE_ROOTS=/manual/area1:/manual/area2 \
    TARGET_ROOTS=/storage/area1:/storage/area2 STATE_DIR=/state HOST_MOUNTINFO=/host/mountinfo
COPY runtime/image-start.sh /usr/local/bin/carddock-start
RUN mkdir /state && chown 1000:10 /state && chmod 0750 /state && chmod 0755 /usr/local/bin/carddock-start
VOLUME /state
RUN ln -sf /usr/local/lib/python3.12/site-packages/tzdata/zoneinfo/Asia/Shanghai /etc/localtime
USER 1000:10
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3)"
CMD ["/usr/local/bin/carddock-start"]
