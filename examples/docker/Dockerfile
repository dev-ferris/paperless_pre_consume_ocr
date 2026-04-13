# Custom Paperless-NGX image with the pre-consume OCR script installed
# as a proper Python package. After build, the `paperless-pre-consume-ocr`
# console script is available on PATH inside the container.
#
# Build (run from the root of this repo):
#   docker build -t paperless-with-pre-consume-ocr -f examples/docker/Dockerfile .
#
# Then reference `paperless-with-pre-consume-ocr` instead of the upstream
# image in your docker-compose.yml.
FROM ghcr.io/paperless-ngx/paperless-ngx:latest

# Copy the package source and install it. This pulls in the runtime
# dependencies (img2pdf, psycopg, pikepdf, pdfminer.six, ocrmypdf, Pillow)
# and exposes the `paperless-pre-consume-ocr` console script.
COPY . /tmp/paperless_pre_consume_ocr
RUN pip install --no-cache-dir /tmp/paperless_pre_consume_ocr \
    && rm -rf /tmp/paperless_pre_consume_ocr
