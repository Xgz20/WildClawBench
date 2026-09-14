#!/usr/bin/env bash
set -euo pipefail

application="all"
codex_port=9230
astronstudio_port=9240
workbuddy_port=9229
qwenwork_port=9250
timeout_seconds=20
check_only=false
codex_app_path=""
astronstudio_app_path=""
workbuddy_app_path=""
qwenwork_app_path=""

usage() {
  cat <<'EOF'
Usage: start_macos_desktop_debug.sh [options]

Options:
  --application all|codex|astronstudio|workbuddy|codex-workbuddy|qwenwork|codex-qwenwork
  --codex-port PORT
  --astronstudio-port PORT
  --workbuddy-port PORT
  --qwenwork-port PORT
  --timeout-seconds SECONDS
  --codex-app-path PATH
  --astronstudio-app-path PATH
  --workbuddy-app-path PATH
  --qwenwork-app-path PATH
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
    --workbuddy-port)
      workbuddy_port="${2:-}"
      shift 2
      ;;
    --qwenwork-port)
      qwenwork_port="${2:-}"
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
    --workbuddy-app-path)
      workbuddy_app_path="${2:-}"
      shift 2
      ;;
    --qwenwork-app-path)
      qwenwork_app_path="${2:-}"
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

include_codex=false
include_astronstudio=false
include_workbuddy=false
include_qwenwork=false

case "$application" in
  all)
    include_codex=true
    include_astronstudio=true
    ;;
  codex)
    include_codex=true
    ;;
  astronstudio)
    include_astronstudio=true
    ;;
  workbuddy)
    include_workbuddy=true
    ;;
  codex-workbuddy)
    include_codex=true
    include_workbuddy=true
    ;;
  qwenwork)
    include_qwenwork=true
    ;;
  codex-qwenwork)
    include_codex=true
    include_qwenwork=true
    ;;
  *)
    echo "Unsupported --application value: $application" >&2
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
validate_number "--workbuddy-port" "$workbuddy_port" 1024 65535
validate_number "--qwenwork-port" "$qwenwork_port" 1024 65535
validate_number "--timeout-seconds" "$timeout_seconds" 1 120

selected_ports=()
$include_codex && selected_ports+=("Codex:$codex_port")
$include_astronstudio && selected_ports+=("AstronStudio:$astronstudio_port")
$include_workbuddy && selected_ports+=("WorkBuddy:$workbuddy_port")
$include_qwenwork && selected_ports+=("QwenWork:$qwenwork_port")
for (( index=0; index<${#selected_ports[@]}; index+=1 )); do
  for (( other=index+1; other<${#selected_ports[@]}; other+=1 )); do
    if [[ "${selected_ports[index]#*:}" == "${selected_ports[other]#*:}" ]]; then
      echo "Selected desktop applications must use different CDP ports" >&2
      exit 2
    fi
  done
done

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
  /usr/sbin/lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | /usr/bin/head -n 1 || true
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

sqlite_scalar() {
  local database="$1"
  local query="$2"
  local name="$3"
  local output

  if [[ ! -f "$database" ]]; then
    echo "$name session database was not found; refusing to restart a running client: $database" >&2
    return 1
  fi
  if [[ ! -x /usr/bin/sqlite3 ]]; then
    echo "macOS sqlite3 is unavailable; refusing to restart a running $name client" >&2
    return 1
  fi
  if ! output="$(/usr/bin/sqlite3 -readonly "$database" "$query" 2>&1)"; then
    echo "Unable to verify $name active sessions; refusing to restart: $output" >&2
    return 1
  fi
  if [[ ! "$output" =~ ^[0-9]+$ ]]; then
    echo "Invalid $name active-session count; refusing to restart: $output" >&2
    return 1
  fi
  printf '%s\n' "$output"
}

assert_workbuddy_restart_safe() {
  local database="$HOME/Library/Application Support/WorkBuddy/codebuddy-sessions.vscdb"
  local active_count
  active_count="$(sqlite_scalar "$database" \
    "select count(*) from ItemTable where key like 'session:%' and lower(coalesce(json_extract(cast(value as text), '\$.status'), '')) in ('running','needs_attention','pending','starting');" \
    "WorkBuddy")" || return 1
  if (( active_count > 0 )); then
    echo "WorkBuddy has $active_count active or pending session(s); refusing to restart the client" >&2
    return 1
  fi
}

assert_qwenwork_restart_safe() {
  local database="$HOME/Library/Application Support/QwenWorkCN/data/agents.db"
  local active_count
  active_count="$(sqlite_scalar "$database" \
    "select count(*) from sub_chats join chats on chats.id = sub_chats.chat_id where chats.deleted_at is null and (sub_chats.stream_id is not null or lower(coalesce(json_extract(chats.ext, '\$.taskStatus'), '')) in ('running','needs_attention','pending','starting'));" \
    "QwenWork")" || return 1
  if (( active_count > 0 )); then
    echo "QwenWork has $active_count active or pending session(s); refusing to restart the client" >&2
    return 1
  fi
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
workbuddy_ready=true
qwenwork_ready=true

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

if $include_workbuddy; then
  if ! cdp_ready "$workbuddy_port" '^(WorkBuddy|CodeBuddy)$'; then
    workbuddy_ready=false
  fi
fi

if $include_qwenwork; then
  if ! cdp_ready "$qwenwork_port" '^(QwenWorkCN|QwenWork)$'; then
    qwenwork_ready=false
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
  if ! $workbuddy_ready; then
    echo "WorkBuddy is not exposing a valid CDP target on port $workbuddy_port" >&2
    exit 1
  fi
  if ! $qwenwork_ready; then
    echo "QwenWork is not exposing a valid CDP target on port $qwenwork_port" >&2
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

  if $include_workbuddy && ! $workbuddy_ready; then
    assert_port_restartable "$workbuddy_port" '^(WorkBuddy|CodeBuddy)$'
    workbuddy_app_path="$(resolve_app_path \
      "$workbuddy_app_path" \
      "/Applications/WorkBuddy.app" \
      "$HOME/Applications/WorkBuddy.app")" || {
        echo "WorkBuddy application bundle was not found" >&2
        exit 1
      }
    if app_is_running "$workbuddy_app_path"; then
      assert_workbuddy_restart_safe
    fi
    stop_app "WorkBuddy" "$workbuddy_app_path" "com.tencent.workbuddy.mac"
    start_app "WorkBuddy" "$workbuddy_app_path" "$workbuddy_port"
  fi

  if $include_qwenwork && ! $qwenwork_ready; then
    assert_port_restartable "$qwenwork_port" '^(QwenWorkCN|QwenWork)$'
    qwenwork_app_path="$(resolve_app_path \
      "$qwenwork_app_path" \
      "/Applications/QwenWorkCN.app" \
      "/Applications/QwenWork.app" \
      "$HOME/Applications/QwenWorkCN.app" \
      "$HOME/Applications/QwenWork.app")" || {
        echo "QwenWork application bundle was not found" >&2
        exit 1
      }
    if app_is_running "$qwenwork_app_path"; then
      assert_qwenwork_restart_safe
    fi
    stop_app "QwenWork" "$qwenwork_app_path" "cn.qwenwork.desktop.mac"
    start_app "QwenWork" "$qwenwork_app_path" "$qwenwork_port"
  fi
fi

echo "Waiting for $application CDP endpoints..."
if $include_codex; then
  wait_for_cdp "Codex Desktop" "$codex_port" '^(ChatGPT|Codex)$'
fi
if $include_astronstudio; then
  wait_for_cdp "AstronStudio" "$astronstudio_port" '^(AStudio|AstronStudio|Acode)$'
fi
if $include_workbuddy; then
  wait_for_cdp "WorkBuddy" "$workbuddy_port" '^(WorkBuddy|CodeBuddy)$'
fi
if $include_qwenwork; then
  wait_for_cdp "QwenWork" "$qwenwork_port" '^(QwenWorkCN|QwenWork)$'
fi

echo
if $include_codex; then
  report_status "Codex Desktop" "$codex_port"
fi
if $include_astronstudio; then
  report_status "AstronStudio" "$astronstudio_port"
fi
if $include_workbuddy; then
  report_status "WorkBuddy" "$workbuddy_port"
fi
if $include_qwenwork; then
  report_status "QwenWork" "$qwenwork_port"
fi
