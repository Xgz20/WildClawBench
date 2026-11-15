# Independent native renderer layer; keep existing scorer tags and jobs unchanged.
ARG SCORER_BASE_IMAGE=astudio-e2e-scorer:20261114
FROM ${SCORER_BASE_IMAGE}
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
 libreoffice-impress libreoffice-writer libreoffice-calc poppler-utils fonts-noto-cjk fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
COPY configure_linux_office.py /opt/configure-linux-office.py
RUN /opt/scoring-runtime/bin/python /opt/configure-linux-office.py
LABEL org.astron.eval.native-office="libreoffice"
