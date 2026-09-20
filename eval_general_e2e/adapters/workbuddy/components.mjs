import {
  COMPONENT_VERSION as DESKTOP_APP_DISCOVERY_VERSION,
  discoverDesktopApp,
  inspectMacDesktopAppProcess,
  verifyDesktopAppPath,
} from "../../../tools/report/e2e-shared/desktop-app-discovery/index.mjs";
import {
  WORKBUDDY_APP_PROFILE,
} from "../../../tools/report/e2e-shared/desktop-app-discovery/profiles.mjs";

export const WORKBUDDY_MACOS_APP_PROFILE = Object.freeze({
  ...WORKBUDDY_APP_PROFILE,
  id: "workbuddy-macos",
  macos: Object.freeze({
    ...WORKBUDDY_APP_PROFILE.macos,
    // WorkBuddy 5.5.x uses the generic Electron binary declared by
    // CFBundleExecutable. Keep this client-specific variant outside the
    // shared profile until COMMON decides whether it is generally valid.
    executableNames: Object.freeze([
      ...WORKBUDDY_APP_PROFILE.macos.executableNames,
      "Electron",
    ]),
  }),
});

export const WORKBUDDY_MACOS_INSTALLATION_VARIANTS = Object.freeze([
  Object.freeze({
    id: "workbuddy-macos-electron",
    // This list is observed compatibility metadata, not a version gate.
    client_versions: Object.freeze(["5.5.3", "5.5.6"]),
    executable_name: "Electron",
  }),
]);

export const WORKBUDDY_SHARED_COMPONENTS = Object.freeze({
  "desktop-app-discovery": DESKTOP_APP_DISCOVERY_VERSION,
  "general-contracts": "1.2.0",
});

export {
  discoverDesktopApp,
  inspectMacDesktopAppProcess,
  verifyDesktopAppPath,
  WORKBUDDY_APP_PROFILE,
};
