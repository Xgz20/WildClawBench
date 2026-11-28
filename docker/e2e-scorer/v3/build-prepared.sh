#!/usr/bin/env bash
# Incremental build from locally available, versioned scorer and CLI images.
set -euo pipefail
CONTEXT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CONTEXT_DIR}/build-inputs.env"
[[ "${PLATFORM}" == linux/amd64 ]] || { echo 'v0.3 requires linux/amd64' >&2; exit 2; }
rm -f "${CONTEXT_DIR}/runtime-validation.json" "${CONTEXT_DIR}/image-receipt.txt" "${CONTEXT_DIR}/source-images.txt"
DOCKER=(docker --context "${DOCKER_CONTEXT}")
for reference in "${EVAL_BASE_IMAGE}" "${CLAUDE_CODE_IMAGE}"; do
  actual="$("${DOCKER[@]}" image inspect --format '{{.Os}}/{{.Architecture}}' "${reference}")"
  [[ "${actual}" == "${PLATFORM}" ]] || { echo "SCORER_SOURCE_PLATFORM_MISMATCH: ${reference}" >&2; exit 1; }
  "${DOCKER[@]}" image inspect --format '{{json .Id}} {{json .Architecture}} {{json .RepoTags}}' "${reference}" >> "${CONTEXT_DIR}/source-images.txt"
done
if "${DOCKER[@]}" image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${EVAL_BASE_IMAGE}" | grep -Eq '(^|_)(API_KEY|TOKEN|PASSWORD|SECRET)=.+$'; then
  echo 'SCORER_BASE_HAS_CREDENTIAL_ENVIRONMENT' >&2
  exit 1
fi
BUILD_ARGS=()
for key in EVAL_BASE_IMAGE CLAUDE_CODE_IMAGE CODEX_VERSION DSH_VERSION CLAUDE_CODE_VERSION; do
  BUILD_ARGS+=(--build-arg "${key}=${!key}")
done
"${DOCKER[@]}" build --platform "${PLATFORM}" --progress=plain "${BUILD_ARGS[@]}" \
  --file "${CONTEXT_DIR}/Dockerfile" --tag "${IMAGE_TAG}" "${CONTEXT_DIR}"
actual="$("${DOCKER[@]}" image inspect --format '{{.Os}}/{{.Architecture}}' "${IMAGE_TAG}")"
[[ "${actual}" == "${PLATFORM}" ]] || { echo 'SCORER_PLATFORM_MISMATCH' >&2; exit 1; }
"${DOCKER[@]}" run --platform "${PLATFORM}" --rm --network none \
  --entrypoint /opt/scoring-runtime/bin/python "${IMAGE_TAG}" /opt/validate-scorer-runtime.py \
  --codex-version "${CODEX_VERSION}" --dsh-version "${DSH_VERSION}" \
  --claude-code-version "${CLAUDE_CODE_VERSION}" --platform "${PLATFORM}" --office \
  > "${CONTEXT_DIR}/runtime-validation.json.tmp"
mv "${CONTEXT_DIR}/runtime-validation.json.tmp" "${CONTEXT_DIR}/runtime-validation.json"
"${DOCKER[@]}" image inspect --format '{{json .Id}} {{json .Architecture}} {{json .Config.Labels}}' \
  "${IMAGE_TAG}" > "${CONTEXT_DIR}/image-receipt.txt"
echo "OK: ${IMAGE_TAG} (offline validation passed)"
