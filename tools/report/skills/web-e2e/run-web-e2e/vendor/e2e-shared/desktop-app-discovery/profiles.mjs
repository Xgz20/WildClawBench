export const ASTRONSTUDIO_APP_PROFILE = Object.freeze({
  id: "astronstudio",
  displayName: "AstronStudio",
  macos: Object.freeze({
    bundleIds: Object.freeze(["cn.xfyun.acode"]),
    appNames: Object.freeze(["AStudio.app", "AstronStudio.app", "Acode.app"]),
    executableNames: Object.freeze(["AStudio", "AstronStudio", "Acode"]),
    requiredRelativePaths: Object.freeze(["Contents/Resources/app.asar"]),
    standardPaths: Object.freeze([
      "/Applications/AStudio.app",
      "/Applications/AstronStudio.app",
      "/Applications/Acode.app",
      "{home}/Applications/AStudio.app",
      "{home}/Applications/AstronStudio.app",
      "{home}/Applications/Acode.app",
    ]),
  }),
  windows: Object.freeze({
    executableNames: Object.freeze(["AStudio.exe", "AstronStudio.exe", "Acode.exe"]),
    requiredRelativePaths: Object.freeze(["resources/app.asar"]),
    productRegistryKeys: Object.freeze([
      Object.freeze({ key: "HKCU\\Software\\AStudio", value: "InstallLocation" }),
      Object.freeze({ key: "HKCU\\Software\\AstronStudio", value: "InstallLocation" }),
      Object.freeze({ key: "HKCU\\Software\\Acode", value: "InstallLocation" }),
      Object.freeze({ key: "HKLM\\Software\\AStudio", value: "InstallLocation" }),
      Object.freeze({ key: "HKLM\\Software\\AstronStudio", value: "InstallLocation" }),
      Object.freeze({ key: "HKLM\\Software\\Acode", value: "InstallLocation" }),
    ]),
    uninstallDisplayNamePattern: "^(?:AStudio|AstronStudio|Acode)(?:\\s|$)",
    standardPaths: Object.freeze([
      "{localAppData}/Programs/AStudio",
      "{localAppData}/Programs/AstronStudio",
      "{localAppData}/Programs/Acode",
      "{programFiles}/AStudio",
      "{programFiles}/AstronStudio",
    ]),
  }),
});

export const WORKBUDDY_APP_PROFILE = Object.freeze({
  id: "workbuddy",
  displayName: "WorkBuddy",
  macos: Object.freeze({
    bundleIds: Object.freeze(["com.tencent.workbuddy.mac"]),
    appNames: Object.freeze(["WorkBuddy.app", "CodeBuddy.app"]),
    // WorkBuddy 5.5.x macOS bundles declare the generic Electron runtime in
    // Info.plist. The bundle ID and required app.asar still gate discovery.
    executableNames: Object.freeze(["WorkBuddy", "CodeBuddy", "Electron"]),
    requiredRelativePaths: Object.freeze(["Contents/Resources/app.asar"]),
    standardPaths: Object.freeze([
      "/Applications/WorkBuddy.app",
      "/Applications/CodeBuddy.app",
      "{home}/Applications/WorkBuddy.app",
      "{home}/Applications/CodeBuddy.app",
    ]),
  }),
  windows: Object.freeze({
    executableNames: Object.freeze(["WorkBuddy.exe", "CodeBuddy.exe"]),
    requiredRelativePaths: Object.freeze(["resources/app.asar"]),
    uninstallDisplayNamePattern: "^WorkBuddy(?:\\s|$)",
    standardPaths: Object.freeze([
      "{localAppData}/Programs/WorkBuddy",
      "{programFiles}/WorkBuddy",
    ]),
  }),
});

export const QWENWORK_APP_PROFILE = Object.freeze({
  id: "qwenwork",
  displayName: "QwenWork",
  macos: Object.freeze({
    bundleIds: Object.freeze(["cn.qwenwork.desktop.mac"]),
    appNames: Object.freeze(["QwenWorkCN.app", "QwenWork.app"]),
    executableNames: Object.freeze(["QwenWorkCN", "QwenWork"]),
    requiredRelativePaths: Object.freeze(["Contents/Resources/app.asar"]),
    standardPaths: Object.freeze([
      "/Applications/QwenWorkCN.app",
      "/Applications/QwenWork.app",
      "{home}/Applications/QwenWorkCN.app",
      "{home}/Applications/QwenWork.app",
    ]),
  }),
  windows: Object.freeze({
    executableNames: Object.freeze(["QwenWorkCN.exe", "QwenWork.exe"]),
    requiredRelativePaths: Object.freeze(["resources/app.asar"]),
    uninstallDisplayNamePattern: "^(?:千问办公|QwenWorkCN|QwenWork)(?:\\s|$)",
    allowVersionSubdirectories: true,
    standardPaths: Object.freeze([
      "{localAppData}/Programs/QwenWorkCN",
      "{localAppData}/Programs/QwenWork",
      "{programFiles}/QwenWorkCN",
      "{programFiles}/QwenWork",
    ]),
  }),
});

// DoubaoWork macOS has a native application bundle with an embedded browser.
// Discovery verifies this layout; the Driver separately verifies its CDP owner
// and supported runtime. There is no inferred Electron/app.asar requirement.
export const DOUBAOWORK_APP_PROFILE = Object.freeze({
  id: "doubaowork",
  displayName: "DoubaoWork",
  macos: Object.freeze({
    bundleIds: Object.freeze(["com.work.pc.doubao"]),
    appNames: Object.freeze(["DoubaoWork.app"]),
    executableNames: Object.freeze(["DoubaoWork"]),
    requiredRelativePaths: Object.freeze([
      "Contents/Info.plist",
      "Contents/MacOS/DoubaoWork",
      "Contents/Helpers/DoubaoWork Browser.app/Contents/MacOS/DoubaoWork Browser",
    ]),
    standardPaths: Object.freeze([
      "/Applications/DoubaoWork.app",
      "{home}/Applications/DoubaoWork.app",
    ]),
  }),
});

export const CODEX_DESKTOP_APP_PROFILE = Object.freeze({
  id: "codex-desktop",
  displayName: "Codex Desktop",
  macos: Object.freeze({
    bundleIds: Object.freeze(["com.openai.codex"]),
    appNames: Object.freeze(["ChatGPT.app", "Codex.app"]),
    executableNames: Object.freeze(["ChatGPT", "Codex"]),
    requiredRelativePaths: Object.freeze(["Contents/Info.plist"]),
    standardPaths: Object.freeze([
      "/Applications/ChatGPT.app",
      "/Applications/Codex.app",
      "{home}/Applications/ChatGPT.app",
      "{home}/Applications/Codex.app",
    ]),
  }),
  windows: Object.freeze({
    executableNames: Object.freeze(["ChatGPT.exe", "Codex.exe"]),
    requiredRelativePaths: Object.freeze([]),
    uninstallDisplayNamePattern: "^(?:ChatGPT|Codex)(?:\\s|$)",
    standardPaths: Object.freeze([
      "{localAppData}/Programs/ChatGPT",
      "{localAppData}/Programs/Codex",
      "{programFiles}/ChatGPT",
      "{programFiles}/Codex",
    ]),
  }),
});

export const BUILTIN_DESKTOP_APP_PROFILES = Object.freeze({
  astronstudio: ASTRONSTUDIO_APP_PROFILE,
  workbuddy: WORKBUDDY_APP_PROFILE,
  qwenwork: QWENWORK_APP_PROFILE,
  doubaowork: DOUBAOWORK_APP_PROFILE,
  codex: CODEX_DESKTOP_APP_PROFILE,
  "codex-desktop": CODEX_DESKTOP_APP_PROFILE,
});
