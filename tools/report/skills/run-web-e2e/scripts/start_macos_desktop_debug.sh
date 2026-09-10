#!/usr/bin/env bash
set -euo pipefail

application="all"
codex_port=9230
astronstudio_port=9240
timeout_seconds=20
check_only=false
codex_app_path=""
astronstudio_app_path=""

usage() {
  cat <<'EOF'
Usage: start_macos_desktop_debug.sh [options]

Options:
  --application all|codex|astronstudio
  --codex-port PORT
  --astronstudio-port PORT
  --timeout-seconds SECONDS
  --codex-app-path PATH
  --astronstudio-app-path PATH
  --check-only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --application)
      application="${2:-}"
      shift 2
      ;;
    --codex-port)
      codex_port="${2:-}"
      shift 2
      ;;
    --astronstudio-port)
      astronstudio_port="${2:-}"
      shift 2
      ;;
    --timeout-seconds)
      timeout_seconds="${2:-}"
      shift 2
      ;;
    --codex-app-path)
      codex_app_path="${2:-}"
      shift 2
      ;;
    --astronstudio-app-path)
      astronstudio_app_path="${2:-}"
      shift 2
      ;;
    --check-only)
      check_only=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$application" in
  all)
    include_codex=true
    include_astronstudio=true
    ;;
  codex)
    include_codex=true
    include_astronstudio=false
    ;;
  astronstudio)
    include_codex=false
    include_astronstudio=true
    ;;
  *)
    echo "--application must be all, codex, or astronstudio" >&2
    exit 2
    ;;
esac

validate_number() {
  local name="$1"
  local value="$2"
  local minimum="$3"
  local maximum="$4"

  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value < minimum || value > maximum )); then
    echo "$name must be an integer from $minimum through $maximum" >&2
    exit 2
  fi
}

validate_number "--codex-port" "$codex_port" 1024 65535
validate_number "--astronstudio-port" "$astronstudio_port" 1024 65535
validate_number "--timeout-seconds" "$timeout_seconds" 1 120

if $include_codex && $include_astronstudio && [[ "$codex_port" == "$astronstudio_port" ]]; then
  echo "Codex and AstronStudio ports must be different" >&2
  exit 2
fi

resolve_app_path() {
  local requested="$1"
  shift

  if [[ -n "$requested" ]]; then
    if [[ -d "$requested" ]]; then
      printf '%s\n' "$requested"
      return 0
    fi
    echo "Application bundle was not found: $requested" >&2
    return 1
  fi

  local candidate
  for candidate in "$@"; do
    if [[ -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

listener_pid() {
  local port="$1"
  /usr/sbin/lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | /usr/bin/head -n 1
}

cdp_ready() {
  local port="$1"
  local process_pattern="$2"
  local version
  local targets
  local pid
  local command

  version="$(/usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:${port}/json/version" 2>/dev/null)" || return 1
  targets="$(/usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:${port}/json/list" 2>/dev/null)" || return 1
  [[ "$version" == *'"webSocketDebuggerUrl"'* ]] || return 1
  [[ "$targets" == *'"webSocketDebuggerUrl"'* ]] || return 1

  pid="$(listener_pid "$port")"
  [[ -n "$pid" ]] || return 1
  command="$(/bin/ps -p "$pid" -o comm= 2>/dev/null)" || return 1
  command="$(/usr/bin/basename "$command")"
  [[ "$command" =~ $process_pattern ]]
}

app_is_running() {
  local app_path="$1"
  /usr/bin/pgrep -f "${app_path}/Contents/MacOS/" >/dev/null 2>&1
}

stop_app() {
  local name="$1"
  local app_path="$2"
  local bundle_id="$3"

  if ! app_is_running "$app_path"; then
    return 0
  fi

  echo "Stopping $name because its CDP endpoint is not ready..."
  /usr/bin/osascript -e "tell application id \"${bundle_id}\" to quit" >/dev/null 2>&1 || true

  local attempt
  for attempt in {1..20}; do
    if ! app_is_running "$app_path"; then
      return 0
    fi
    /bin/sleep 0.5
  done

  /usr/bin/pkill -TERM -f "${app_path}/Contents/MacOS/" >/dev/null 2>&1 || true
  for attempt in {1..10}; do
    if ! app_is_running "$app_path"; then
      return 0
    fi
    /bin/sleep 0.5
  done

  /usr/bin/pkill -KILL -f "${app_path}/Contents/MacOS/" >/dev/null 2>&1 || true
  /bin/sleep 1

  if app_is_running "$app_path"; then
    echo "Unable to stop $name" >&2
    return 1
  fi
}

assert_port_available() {
  local port="$1"
  local pid
  pid="$(listener_pid "$port")"
  if [[ -n "$pid" ]]; then
    echo "Port $port is already used by PID $pid" >&2
    return 1
  fi
}

assert_port_restartable() {
  local port="$1"
  local process_pattern="$2"
  local pid
  local command

  pid="$(listener_pid "$port")"
  if [[ -z "$pid" ]]; then
    return 0
  fi

  command="$(/bin/ps -p "$pid" -o comm= 2>/dev/null || true)"
  command="$(/usr/bin/basename "$command")"
  if [[ ! "$command" =~ $process_pattern ]]; then
    echo "Port $port is already used by $command (PID $pid); refusing to stop an unrelated process" >&2
    return 1
  fi
}

start_app() {
  local name="$1"
  local app_path="$2"
  local port="$3"

  assert_port_available "$port"
  echo "Starting $name with CDP on port $port..."
  /usr/bin/open -na "$app_path" --args \
    "--remote-debugging-address=127.0.0.1" \
    "--remote-debugging-port=${port}"
}

wait_for_cdp() {
  local name="$1"
  local port="$2"
  local process_pattern="$3"
  local deadline=$(( $(/bin/date +%s) + timeout_seconds ))

  while (( $(/bin/date +%s) < deadline )); do
    if cdp_ready "$port" "$process_pattern"; then
      return 0
    fi
    /bin/sleep 0.5
  done

  echo "$name CDP endpoint did not become ready on port $port within $timeout_seconds seconds" >&2
  return 1
}

report_status() {
  local name="$1"
  local port="$2"
  local version
  local targets
  local pid
  local browser
  local target_count

  version="$(/usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:${port}/json/version")"
  targets="$(/usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:${port}/json/list")"
  pid="$(listener_pid "$port")"
  browser="$(printf '%s\n' "$version" | /usr/bin/sed -n 's/.*"Browser"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  target_count="$(printf '%s\n' "$targets" | /usr/bin/grep -o '"webSocketDebuggerUrl"' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"

  printf '%-15s 127.0.0.1:%-5s PID=%-7s targets=%-3s %s\n' \
    "$name" "$port" "$pid" "$target_count" "$browser"
  printf '  http://127.0.0.1:%s/json/list\n' "$port"
}

codex_ready=true
astronstudio_ready=true

if $include_codex; then
  if ! cdp_ready "$codex_port" '^(ChatGPT|Codex)$'; then
    codex_ready=false
  fi
fi

if $include_astronstudio; then
  if ! cdp_ready "$astronstudio_port" '^(AStudio|AstronStudio|Acode)$'; then
    astronstudio_ready=false
  fi
fi

if $check_only; then
  if ! $codex_ready; then
    echo "Codex Desktop is not exposing a valid CDP target on port $codex_port" >&2
    exit 1
  fi
  if ! $astronstudio_ready; then
    echo "AstronStudio is not exposing a valid CDP target on port $astronstudio_port" >&2
    exit 1
  fi
else
  if $include_codex && ! $codex_ready; then
    assert_port_restartable "$codex_port" '^(ChatGPT|Codex)$'
    codex_app_path="$(resolve_app_path \
      "$codex_app_path" \
      "/Applications/ChatGPT.app" \
      "/Applications/Codex.app" \
      "$HOME/Applications/ChatGPT.app" \
      "$HOME/Applications/Codex.app")" || {
        echo "Codex Desktop application bundle was not found" >&2
        exit 1
      }
    stop_app "Codex Desktop" "$codex_app_path" "com.openai.codex"
    start_app "Codex Desktop" "$codex_app_path" "$codex_port"
  fi

  if $include_astronstudio && ! $astronstudio_ready; then
    assert_port_restartable "$astronstudio_port" '^(AStudio|AstronStudio|Acode)$'
    astronstudio_app_path="$(resolve_app_path \
      "$astronstudio_app_path" \
      "/Applications/AStudio.app" \
      "/Applications/AstronStudio.app" \
      "$HOME/Applications/AStudio.app" \
      "$HOME/Applications/AstronStudio.app")" || {
        echo "AstronStudio application bundle was not found" >&2
        exit 1
      }
    stop_app "AstronStudio" "$astronstudio_app_path" "cn.xfyun.acode"
    start_app "AstronStudio" "$astronstudio_app_path" "$astronstudio_port"
  fi
fi

echo "Waiting for $application CDP endpoints..."
if $include_codex; then
  wait_for_cdp "Codex Desktop" "$codex_port" '^(ChatGPT|Codex)$'
fi
if $include_astronstudio; then
  wait_for_cdp "AstronStudio" "$astronstudio_port" '^(AStudio|AstronStudio|Acode)$'
fi

echo
if $include_codex; then
  report_status "Codex Desktop" "$codex_port"
fi
if $include_astronstudio; then
  report_status "AstronStudio" "$astronstudio_port"
fi
