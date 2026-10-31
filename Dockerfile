FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
ARG INSTALL_EXIFTOOL=1
RUN if [ "$INSTALL_EXIFTOOL" = "1" ]; then \
      sed -i "s|http://deb.debian.org|https://deb.debian.org|g" /etc/apt/sources.list.d/debian.sources && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=0 -o Acquire::https::Timeout=20 update && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=0 -o Acquire::https::Timeout=20 install -y --no-install-recommends libimage-exiftool-perl && \
      rm -rf /var/lib/apt/lists/*; fi
WORKDIR /app
COPY wheelhouse/ /wheels/
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-index --no-deps --only-binary=:all: --find-links /wheels --require-hashes -r /tmp/requirements.lock && rm -rf /wheels /tmp/requirements.lock
COPY app/ /app/
RUN chmod -R a+rX /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
RUN ln -sf /usr/local/lib/python3.12/site-packages/tzdata/zoneinfo/Asia/Shanghai /etc/localtime
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3)"
CMD ["python", "server.py"]
