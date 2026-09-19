import {
  COMPONENT_VERSION as DESKTOP_RUNTIME_VERSION,
  runCapture,
} from "../../../tools/report/e2e-shared/desktop-runtime/process.mjs";
import {
  COMPONENT_VERSION as DESKTOP_APP_DISCOVERY_VERSION,
  discoverDesktopApp,
  verifyDesktopAppPath,
} from "../../../tools/report/e2e-shared/desktop-app-discovery/index.mjs";
import {
  QWENWORK_APP_PROFILE,
} from "../../../tools/report/e2e-shared/desktop-app-discovery/profiles.mjs";
import {
  COMPONENT_VERSION as RESOURCE_METRICS_VERSION,
  createNativeResourceMetricParsers,
} from "../../../tools/report/e2e-shared/resource-metrics/native-parsers.mjs";
import {
  assertTraceWorkspace,
  isSafeNativeId,
  readTrace,
  sameNativePath,
} from "../../../tools/report/e2e-shared/resource-metrics/trace-io.mjs";

import { matchQwenWorkRuntimeProfile } from "./runtime-profile.mjs";

export const QWENWORK_SHARED_COMPONENTS = Object.freeze({
  "desktop-runtime": DESKTOP_RUNTIME_VERSION,
  "desktop-app-discovery": DESKTOP_APP_DISCOVERY_VERSION,
  "resource-metrics": RESOURCE_METRICS_VERSION,
});

export const QWENWORK_NATIVE_RESOURCE_PROFILE = Object.freeze({
  schemaVersion: "wildclawbench.general-e2e-qwenwork-resource-observation/v1",
  version: "0.1.0",
  scope: "primary-attempt",
  excludedScope: Object.freeze([
    "judge-usage",
    "control-usage",
    "unobserved-http-retries",
    "unlinked-child-agents",
    "client-background-services",
  ]),
});

export const qwenWorkNativeResourceParsers = createNativeResourceMetricParsers({
  ...QWENWORK_NATIVE_RESOURCE_PROFILE,
  resolveQwenProfile: matchQwenWorkRuntimeProfile,
});

export {
  QWENWORK_APP_PROFILE,
  assertTraceWorkspace,
  discoverDesktopApp,
  isSafeNativeId,
  readTrace,
  runCapture,
  sameNativePath,
  verifyDesktopAppPath,
};
