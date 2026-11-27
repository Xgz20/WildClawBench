# Add the browser required by the frozen managed Python, preserving old images.
ARG SCORER_BASE_IMAGE=astudio-e2e-scorer:20261114
FROM ${SCORER_BASE_IMAGE}
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/scoring-runtime/playwright-browsers
RUN /opt/scoring-runtime/bin/python -m playwright install chromium
RUN --network=none /opt/scoring-runtime/bin/python /opt/runtime-score-skill/scripts/offline_browser_validate.py --probe --output-dir /opt/scoring-browser-preflight
LABEL org.astron.eval.managed-browser="playwright-chromium"
