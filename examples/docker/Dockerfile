# Custom Paperless-NGX image with the extra Python packages required
# by the pre-consume OCR script (img2pdf and psycopg).
#
# Build:
#   docker build -t paperless-with-pre-consume-ocr -f examples/docker/Dockerfile .
#
# Then reference `paperless-with-pre-consume-ocr` instead of the upstream
# image in your docker-compose.yml.
FROM ghcr.io/paperless-ngx/paperless-ngx:latest

RUN pip install --no-cache-dir \
        img2pdf \
        "psycopg[binary]"
