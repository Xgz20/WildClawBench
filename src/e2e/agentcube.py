"""AgentCube session, PicoD job and Windows file interfaces."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import shlex
import time
import uuid
from urllib.parse import quote, urlsplit

import requests

from . import DEFAULT_AGENTCUBE_NAMESPACE, DEFAULT_AGENTCUBE_TEMPLATE
from .common import E2EError, identifier, read_json, redact


class PlatformError(E2EError):
    def __init__(self, message: str, *, uncertain: bool = False, platform_code: str | None = None):
        super().__init__(message)
        self.uncertain = uncertain
        self.platform_code = platform_code


@dataclass(frozen=True)
class AgentCubeConfig:
    workload_manager_url: str = "http://eval-agent-prod.maas.private"
    router_url: str = "http://eval-agent-prod.maas.private"
    namespace: str = DEFAULT_AGENTCUBE_NAMESPACE
    template: str = DEFAULT_AGENTCUBE_TEMPLATE
    app_id: str = "AstronEval"
    user_id: str = ""
    active_ttl: int = 10800
    expire_ttl: int = 14400
    trust_env: bool = False
    astudio_runtime: dict | None = None
    chatgpt_gateway_url: str | None = None
    auth_token: str = field(default="", repr=False)
    create_timeout_seconds: int = 900

    @classmethod
    def load(cls, path: Path | None = None, *, template: str | None = None):
        values = {key.lower(): value for key, value in (read_json(path) if path else {}).items()}
        # Existing deployments may still carry the retired admission field.
        values.pop("preprocessing_profiles", None)
        unknown = set(values) - set(cls.__dataclass_fields__)
        if unknown:
            raise E2EError("AGENTCUBE_CONFIG_UNKNOWN_KEYS: " + ",".join(sorted(unknown)))
        if "auth_token" in values:
            raise E2EError("AGENTCUBE_TOKEN_MUST_USE_ENVIRONMENT")
        values["auth_token"] = os.environ.get("AGENTCUBE_AUTH_TOKEN", "")
        for key in ("app_id", "user_id", "workload_manager_url", "router_url"):
            if os.environ.get("AGENTCUBE_" + key.upper()):
                values[key] = os.environ["AGENTCUBE_" + key.upper()]
        if template:
            values["template"] = template
        result = cls(**values)
        if type(result.trust_env) is not bool:
            raise E2EError("AGENTCUBE_TRUST_ENV_MUST_BE_BOOLEAN")
        if not result.auth_token or not isinstance(result.user_id, str) or not result.user_id.strip():
            raise E2EError("AGENTCUBE_AUTH_TOKEN_AND_USER_ID_REQUIRED")
        if not isinstance(result.app_id, str) or not result.app_id.strip():
            raise E2EError("AGENTCUBE_APP_ID_REQUIRED")
        for endpoint in (result.workload_manager_url, result.router_url):
            if not isinstance(endpoint, str):
                raise E2EError("AGENTCUBE_ENDPOINT_INVALID")
            parsed = urlsplit(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise E2EError("AGENTCUBE_ENDPOINT_INVALID")
        if type(result.active_ttl) is not int or type(result.expire_ttl) is not int or not 0 < result.active_ttl <= result.expire_ttl:
            raise E2EError("AGENTCUBE_TTL_INVALID")
        if type(result.create_timeout_seconds) is not int or result.create_timeout_seconds <= 0:
            raise E2EError("AGENTCUBE_CREATE_TIMEOUT_INVALID")
        if result.astudio_runtime is not None:
            from .windows_runtime import validate_runtime
            validate_runtime(result.astudio_runtime)
        if result.chatgpt_gateway_url is not None:
            validate_chatgpt_gateway(result.chatgpt_gateway_url)
        identifier(result.template, "template")
        identifier(result.namespace, "namespace")
        return result

    def public(self) -> dict:
        return {key: value for key, value in asdict(self).items()
                if key != "auth_token"
                and not (key in {"astudio_runtime", "chatgpt_gateway_url"} and value is None)
                # Keep legacy runtime fingerprints stable when using their original timeout.
                and not (key == "create_timeout_seconds" and value == 900)}

    def required_expire_ttl(self, execution_timeout: int, preprocessing_timeout: int = 0) -> int:
        return execution_timeout + preprocessing_timeout + 2400 + max(0, self.create_timeout_seconds - 900)


def validate_chatgpt_gateway(value: str) -> None:
    try:
        endpoint = urlsplit(value)
    except (TypeError, ValueError) as error:
        raise E2EError("CHATGPT_GATEWAY_URL_INVALID") from error
    if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username
            or endpoint.password or endpoint.query or endpoint.fragment):
        raise E2EError("CHATGPT_GATEWAY_URL_INVALID")


class AgentCubeClient:
    def __init__(self, config: AgentCubeConfig):
        self.config = config
        self.http = requests.Session()
        self.http.trust_env = config.trust_env
        self.http.headers.update({"Authorization": "Bearer " + config.auth_token,
                                  "Ifly-App-ID": config.app_id, "Ifly-User-ID": config.user_id,
                                  "sdk-version": "v3"})
        self.manager = config.workload_manager_url.rstrip("/") + "/v1/code-interpreter"
        base = config.router_url.rstrip("/") + "/v1/namespaces/" + config.namespace + "/code-interpreters/"
        self.picod = base + "picod/invocations/api"
        self.windows = base + config.template + "/invocations"

    def close(self):
        self.http.close()

    def _request(self, method: str, url: str, *, sid: str | None = None, timeout=60, **kwargs):
        headers = {"x-agentcube-session-id": sid} if sid else {}
        try:
            response = self.http.request(method, url, headers=headers, timeout=(10, timeout), **kwargs)
        except requests.RequestException as error:
            if method == "POST" and url == self.manager and isinstance(error, requests.Timeout):
                raise PlatformError("AGENTCUBE_CREATE_REQUEST_TIMEOUT", uncertain=True) from error
            raise PlatformError(str(redact(str(error), self.config.auth_token)),
                                uncertain=method in {"POST", "DELETE"}) from error
        return response

    def _json(self, response, action: str) -> dict:
        if response.status_code != 200:
            raise PlatformError(f"{action}_HTTP_{response.status_code}: "
                                + str(redact(response.text[:500], self.config.auth_token)),
                                uncertain=response.status_code >= 500)
        try:
            payload = response.json()
        except ValueError as error:
            raise PlatformError(f"{action}_INVALID_JSON", uncertain=True) from error
        if not isinstance(payload, dict) or payload.get("code", 0) != 0:
            if action=="CREATE_SESSION" and "USER_QUOTA_NOT_ACTIVE" in str(payload):
                raise PlatformError("AgentCube 沙箱配额未生效（USER_QUOTA_NOT_ACTIVE）；请检查当前调用身份的有效配额规则。",platform_code="USER_QUOTA_NOT_ACTIVE")
            raise PlatformError(f"{action}_REJECTED: " + str(redact(payload, self.config.auth_token)))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise PlatformError(f"{action}_DATA_INVALID", uncertain=True)
        return data

    def create_session(self) -> str:
        response = self._request("POST", self.manager, timeout=self.config.create_timeout_seconds, json={
            "name": self.config.template, "namespace": self.config.namespace,
            "activeTTL": self.config.active_ttl, "expireTTL": self.config.expire_ttl})
        data = self._json(response, "CREATE_SESSION")
        if not isinstance(data.get("sessionId"), str) or not data["sessionId"]:
            raise PlatformError("CREATE_SESSION_ID_MISSING", uncertain=True)
        return data["sessionId"]

    def delete_session(self, sid: str) -> dict:
        response = self._request("DELETE", self.manager + "/sessions/" + quote(sid, safe=""), timeout=30)
        if response.status_code not in {200, 202, 204, 404}:
            raise PlatformError(f"DELETE_SESSION_HTTP_{response.status_code}", uncertain=True)
        body = response.json() if response.content and response.status_code == 200 else None
        if isinstance(body, dict) and body.get("code", 0) != 0:
            # The company manager reports an already-absent, exact session as
            # HTTP 200/code 10001. Other errors and identities remain uncertain.
            if (body.get("code") == 10001 and body.get("data") is None
                    and body.get("msg") == "sessionId " + sid + " not found"):
                return {"http_status": response.status_code, "response": body,
                        "confirmed": True, "disposition": "already_absent"}
            raise PlatformError("DELETE_SESSION_REJECTED", uncertain=True)
        return {"http_status": response.status_code, "response": redact(body, self.config.auth_token),
                "confirmed": response.status_code != 202}

    def confirm_session_absent(self, sid: str) -> dict:
        response = self._request("GET", self.config.workload_manager_url.rstrip("/")
                                 + "/v1/sandbox/sessions/" + quote(sid, safe=""), timeout=30)
        try:
            body = response.json()
        except ValueError as error:
            raise PlatformError("SESSION_ABSENCE_NOT_CONFIRMED") from error
        if (response.status_code != 200 or not isinstance(body, dict)
                or body.get("code") != 10001 or body.get("data") is not None
                or body.get("msg") != "sessionId " + sid + " not found"):
            raise PlatformError("SESSION_ABSENCE_NOT_CONFIRMED")
        return {"confirmed": True, "session_id": sid, "http_status": 200,
                "platform_code": 10001, "disposition": "already_absent"}

    def execute(self, sid: str, command: str, timeout=30) -> dict:
        response = self._request("POST", self.picod + "/execute", sid=sid, timeout=timeout + 5,
                                 json={"command": [command], "runtime": "bash", "mode": "oneshot",
                                       "env_id": None, "timeout": str(timeout)})
        return self._json(response, "EXECUTE")

    def checked(self, sid: str, command: str, timeout=30) -> str:
        result = self.execute(sid, command, timeout)
        if result.get("exit_code") != 0:
            raise PlatformError("REMOTE_COMMAND_FAILED: " + str(redact(
                (result.get("stderr") or result.get("stdout") or "")[-1000:], self.config.auth_token)))
        return result.get("stdout") or ""

    def upload(self, sid: str, remote: str, content: bytes, *, timeout=300):
        response = self._request("POST", self.picod + "/files", sid=sid, timeout=timeout,
                                 data={"path": remote, "mode": "0644"},
                                 files={"file": (remote.rsplit("/", 1)[-1], content)})
        self._json(response, "UPLOAD")

    def upload_private(self, sid: str, remote: str, content: bytes) -> None:
        response = self._request("POST", self.picod + "/files", sid=sid, timeout=30,
                                 data={"path": remote, "mode": "0600"},
                                 files={"file": (remote.rsplit("/", 1)[-1], content)})
        # Do not include a gateway error body in diagnostics for a credential upload.
        try:
            accepted = response.status_code == 200 and response.json().get("code", 0) == 0
        except (AttributeError, ValueError):
            accepted = False
        if not accepted:
            raise PlatformError("AGENTCUBE_PRIVATE_UPLOAD_FAILED",
                                uncertain=response.status_code >= 500)

    def download(self, sid: str, remote: str) -> bytes:
        response = self._request("GET", self.picod + "/files/" + quote(remote.lstrip("/"), safe="/"), sid=sid)
        if response.status_code == 404:
            raise FileNotFoundError(remote)
        if response.status_code != 200:
            raise PlatformError(f"DOWNLOAD_HTTP_{response.status_code}")
        return response.content

    def download_to(self, sid: str, remote: str, destination: Path):
        response = self._request("GET", self.picod + "/files/" + quote(remote.lstrip("/"), safe="/"),
                                 sid=sid, timeout=300, stream=True)
        temporary = destination.with_name("." + destination.name + ".part-" + uuid.uuid4().hex)
        try:
            if response.status_code != 200:
                raise PlatformError(f"DOWNLOAD_HTTP_{response.status_code}")
            with temporary.open("xb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    output.write(chunk)
            temporary.replace(destination)
        finally:
            response.close()
            temporary.unlink(missing_ok=True)

    def windows_execute(self, sid: str, command: str, timeout=60) -> dict:
        response = self._request("POST", self.windows + "/execute", sid=sid, timeout=timeout,
                                 json={"command": command, "shell": True})
        result = self._json(response, "WINDOWS_EXECUTE")
        if result.get("returncode") != 0:
            raise PlatformError("WINDOWS_COMMAND_FAILED: " + str(redact(result.get("error", "")[:1500], self.config.auth_token)))
        return result

    def windows_download(self, sid: str, path: str) -> bytes:
        response = self._request("POST", self.windows + "/file", sid=sid, data={"file_path": path}, timeout=120)
        if response.status_code == 404:
            raise FileNotFoundError(path)
        if response.status_code != 200:
            raise PlatformError(f"WINDOWS_DOWNLOAD_HTTP_{response.status_code}")
        if response.headers.get("Content-Type", "").startswith("application/json"):
            payload = response.json()
            if isinstance(payload, dict) and payload.get("code") == 10005:
                raise FileNotFoundError(path)
            if isinstance(payload, dict) and payload.get("code", 0) != 0:
                raise PlatformError("WINDOWS_DOWNLOAD_REJECTED: " + str(redact(payload, self.config.auth_token)))
        return response.content

    def submit_job(self, sid: str, job_id: str, command: str) -> dict:
        identifier(job_id, "job_id")
        directory = "/tmp/wcb-e2e-jobs/" + job_id
        quoted = shlex.quote(directory)
        encoded = base64.b64encode(command.encode()).decode()
        inner = f"bash {quoted}/command.sh; rc=$?; printf '%s' $rc > {quoted}/exit.tmp; mv {quoted}/exit.tmp {quoted}/exit_code"
        wrapper = (f"mkdir -p {quoted} && printf '%s' {shlex.quote(encoded)} | base64 -d > {quoted}/command.sh && "
                   f"{{ nohup setsid bash -c {shlex.quote(inner)} > {quoted}/stdout 2> {quoted}/stderr < /dev/null & "
                   f"echo $! > {quoted}/pid; }}")
        self.checked(sid, wrapper)
        return {"job_id": job_id, "remote_directory": directory}

    def poll_job(self, sid: str, job: dict) -> dict | None:
        root = job["remote_directory"]
        try:
            code = int(self.download(sid, root + "/exit_code").decode().strip())
        except FileNotFoundError:
            return None
        return {"exit_code": code, "stdout": self.download(sid, root + "/stdout").decode("utf-8", errors="replace"),
                "stderr": self.download(sid, root + "/stderr").decode("utf-8", errors="replace")}

    def await_job(self, sid: str, job: dict, *, control_timeout: float | None = None, heartbeat=None) -> dict:
        started = time.monotonic()
        interval = 1
        read_failures = 0
        while True:
            try:
                result = self.poll_job(sid, job)
                read_failures = 0
            except PlatformError as error:
                read_failures += 1
                if read_failures >= 5:
                    raise PlatformError("REMOTE_JOB_OBSERVATION_UNAVAILABLE: " + str(error), uncertain=True) from error
                result = None
            if result is not None:
                return result
            if heartbeat:
                heartbeat()
            if control_timeout is not None and time.monotonic() - started >= control_timeout:
                raise PlatformError("REMOTE_JOB_OBSERVATION_INCOMPLETE", uncertain=True)
            time.sleep(interval)
            interval = min(interval * 2, 16)
