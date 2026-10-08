FROM python:3.12-slim
ARG INSTALL_EXIFTOOL=1
RUN if [ "$INSTALL_EXIFTOOL" = "1" ]; then \
      sed -i "s|http://deb.debian.org|https://deb.debian.org|g" /etc/apt/sources.list.d/debian.sources && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=0 -o Acquire::https::Timeout=20 update && \
      apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=0 -o Acquire::https::Timeout=20 install -y --no-install-recommends libimage-exiftool-perl && \
      rm -rf /var/lib/apt/lists/*; fi
WORKDIR /app
COPY app/ /app/
RUN chmod -R a+rX /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3)"
CMD ["python", "server.py"]
