// Native UI transport for the packaged Loomy client, which disables CDP.
// Requests arrive on stdin. Actions re-resolve and compare their AX target.
import Foundation
import AppKit
import ApplicationServices
import CryptoKit

enum Failure: Error { case invalid(String) }
func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else { return nil }
    return result
}
func string(_ element: AXUIElement, _ name: String) -> String {
    return attribute(element, name) as? String ?? ""
}
func children(_ element: AXUIElement) -> [AXUIElement] {
    return attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
}
func identity(_ element: AXUIElement) -> [String: String] {
    let role = string(element, kAXRoleAttribute)
    var result = ["role": role, "title": string(element, kAXTitleAttribute),
                  "description": string(element, kAXDescriptionAttribute),
                  "identifier": string(element, "AXIdentifier")]
    if role == "AXMenuItem" { result["menu_value"] = string(element, kAXValueAttribute) }
    return result
}
func checked(_ result: AXError, _ operation: String) throws {
    guard result == .success else { throw Failure.invalid("AX_\(operation)_FAILED:\(result.rawValue)") }
}
func resolve(_ root: AXUIElement, _ path: [Int]) throws -> AXUIElement {
    var target = root
    for index in path {
        let values = children(target)
        guard index >= 0 && index < values.count else { throw Failure.invalid("AX_TARGET_CHANGED") }
        target = values[index]
    }
    return target
}
func descendants(_ root: AXUIElement) throws -> [AXUIElement] {
    var pending = [root], result: [AXUIElement] = []
    while let element = pending.popLast() {
        if string(element, kAXRoleAttribute) == "AXMenuBar" { continue }
        guard result.count < 12000 else { throw Failure.invalid("AX_GUARD_BUDGET") }
        result.append(element)
        pending.append(contentsOf: children(element))
    }
    return result
}
func registeredWorkspace(_ nodes: [AXUIElement], _ folder: String) throws -> AXUIElement {
    var matches: [AXUIElement] = []
    for item in nodes where string(item, kAXRoleAttribute) == "AXMenuItem" {
        if try descendants(item).filter({ string($0, kAXHelpAttribute) == folder }).count == 1 {
            matches.append(item)
        }
    }
    guard matches.count == 1 else { throw Failure.invalid("AX_WORKSPACE_PATH_CHANGED_OR_AMBIGUOUS") }
    return matches[0]
}
func label(_ element: AXUIElement) -> String {
    let title = string(element, kAXTitleAttribute)
    return title.isEmpty ? string(element, kAXDescriptionAttribute) : title
}
func safeComposer(_ nodes: [AXUIElement], _ pid: Int32) -> Bool {
    return NSWorkspace.shared.frontmostApplication?.processIdentifier == pid
        && nodes.filter({ string($0, kAXRoleAttribute) == "AXWindow" }).count == 1
        && !nodes.contains(where: { element in
            let role = string(element, kAXRoleAttribute)
            return ["AXMenuItem", "AXSheet", "AXDialog"].contains(role)
                || string(element, kAXSubroleAttribute).hasSuffix("Dialog")
                || attribute(element, "AXModal") as? Bool == true
        })
}
func publicPermissionTarget(_ app: AXUIElement, _ pid: Int32, _ stage: String) throws -> AXUIElement {
    let nodes = try descendants(app)
    let dialogs = nodes.filter { string($0, kAXSubroleAttribute).hasSuffix("Dialog") }
    var surface: [AXUIElement]
    let expectedRole: String, expectedLabel: String
    switch stage {
    case "open":
        guard safeComposer(nodes, pid),
              nodes.filter({ string($0, kAXRoleAttribute) == "AXTextArea" })
                .map({ string($0, kAXValueAttribute) }) == [""] else {
            throw Failure.invalid("AX_PERMISSION_REQUIRES_EMPTY_COMPOSER")
        }
        surface = nodes
        expectedRole = "AXPopUpButton"
        expectedLabel = "默认权限"
    case "option", "confirm":
        let isMenu = stage == "option"
        let subrole = isMenu ? "AXApplicationDialog" : "AXApplicationAlertDialog"
        guard dialogs.count == 1, string(dialogs[0], kAXSubroleAttribute) == subrole,
              isMenu || label(dialogs[0]) == "开启完全访问？" else {
            throw Failure.invalid("AX_PERMISSION_SURFACE_CHANGED")
        }
        surface = try descendants(dialogs[0])
        let heading = isMenu ? "当前工作区权限" : "开启完全访问？"
        guard surface.contains(where: { string($0, kAXRoleAttribute) == "AXStaticText"
            && string($0, kAXValueAttribute) == heading }) else { throw Failure.invalid("AX_PERMISSION_HEADING_CHANGED") }
        expectedRole = "AXButton"
        expectedLabel = isMenu ? "完全访问 突破工作区边界；所有操作免询问。" : "我已了解风险，开启完全访问"
    default:
        throw Failure.invalid("AX_PERMISSION_ACTION_UNKNOWN")
    }
    let targets = surface.filter { string($0, kAXRoleAttribute) == expectedRole && label($0) == expectedLabel }
    guard targets.count == 1 else { throw Failure.invalid("AX_PERMISSION_TARGET_AMBIGUOUS") }
    return targets[0]
}
func guardedSend(_ app: AXUIElement, _ pid: Int32, _ guardValues: [String: String],
                 press: Bool) throws -> [String: Any] {
    guard let prompt = guardValues["prompt"], !prompt.isEmpty,
          let folder = guardValues["workspace"], folder.hasPrefix("/"),
          let model = guardValues["model_label"], model == "Spark-X2.6 正式版 高",
          guardValues["permission_label"] == "完全访问" else { throw Failure.invalid("AX_SEND_GUARD_REQUIRED") }
    func readComposer(_ nodes: [AXUIElement]) throws -> AXUIElement {
        let composers = nodes.filter { string($0, kAXRoleAttribute) == "AXTextArea" }
        let popups = nodes.filter { string($0, kAXRoleAttribute) == "AXPopUpButton" }
        let send = nodes.filter { string($0, kAXRoleAttribute) == "AXButton"
            && string($0, kAXDescriptionAttribute) == "发送消息"
            && attribute($0, kAXEnabledAttribute) as? Bool == true }
        guard safeComposer(nodes, pid), composers.count == 1,
              string(composers[0], kAXValueAttribute).utf8.elementsEqual(prompt.utf8),
              popups.filter({ label($0) == model }).count == 1,
              popups.filter({ ["完全访问", "默认权限", "询问模式"].contains(label($0)) }).map({ label($0) }) == ["完全访问"],
              send.count == 1 else { throw Failure.invalid("AX_SEND_CONFIGURATION_OR_PROMPT_CHANGED") }
        return send[0]
    }
    let before = try descendants(app)
    _ = try readComposer(before)
    let selector = before.filter { string($0, kAXRoleAttribute) == "AXPopUpButton"
        && string($0, kAXDescriptionAttribute) == "选择工作目录" }
    guard selector.count == 1 else { throw Failure.invalid("AX_SEND_WORKSPACE_SELECTOR_AMBIGUOUS") }
    try checked(AXUIElementPerformAction(selector[0], kAXPressAction as CFString), "OPEN_WORKSPACE_MENU")
    let menuDeadline = Date().addingTimeInterval(4)
    var item: AXUIElement?
    repeat {
        let menu = try descendants(app)
        if menu.contains(where: { string($0, kAXRoleAttribute) == "AXMenuItem" }) {
            item = try registeredWorkspace(menu, folder)
            break
        }
        Thread.sleep(forTimeInterval: 0.06)
    } while Date() < menuDeadline
    guard let item, NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else {
        throw Failure.invalid("AX_SEND_WORKSPACE_MENU_NOT_READY")
    }
    try checked(AXUIElementPerformAction(item, kAXPressAction as CFString), "SELECT_EXACT_WORKSPACE")
    let closeDeadline = Date().addingTimeInterval(4)
    repeat {
        let after = try descendants(app)
        if safeComposer(after, pid) {
            let send = try readComposer(after)
            if press { try checked(AXUIElementPerformAction(send, kAXPressAction as CFString), "PRESS") }
            let hash = SHA256.hash(data: Data(prompt.utf8)).map { String(format: "%02x", $0) }.joined()
            return ["status": "PASS", "pid": pid, "action": press ? "send" : "verify-send",
                    "workspace": folder, "model_label": model, "permission_label": "完全访问",
                    "prompt_sha256": hash, "workspace_selection": "guarded-native-exact-menu-path",
                    "dispatched": press]
        }
        Thread.sleep(forTimeInterval: 0.06)
    } while Date() < closeDeadline
    throw Failure.invalid("AX_SEND_WORKSPACE_SELECTION_NOT_CONFIRMED")
}
func main() throws -> [String: Any] {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard let request = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          let pid = request["pid"] as? Int32,
          let running = NSRunningApplication(processIdentifier: pid),
          running.bundleIdentifier == "com.loomy.desktop",
          running.executableURL?.lastPathComponent == "Loomy",
          !running.isTerminated else { throw Failure.invalid("LOOMY_PROCESS_IDENTITY_INVALID") }
    guard AXIsProcessTrusted() else { throw Failure.invalid("MACOS_ACCESSIBILITY_NOT_AUTHORIZED") }
    let app = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(app, 5)
    // Electron exposes a complete AX tree only after assistive access has been
    // activated. This changes the accessibility presentation, not task state.
    _ = AXUIElementSetAttributeValue(app, "AXManualAccessibility" as CFString, kCFBooleanTrue)
    _ = AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
    let action = request["action"] as? String ?? "snapshot"
    if action == "activate" {
        guard running.activate(options: [.activateIgnoringOtherApps]) else { throw Failure.invalid("LOOMY_ACTIVATION_FAILED") }
        return ["status": "PASS", "pid": pid]
    }
    if action == "snapshot" {
        var nodes: [[String: Any]] = []
        func visit(_ element: AXUIElement, _ path: [Int], _ depth: Int) throws {
            // App menus include macOS's unrelated Recent Items. They are not part
            // of the task UI, and are neither exported nor actionable here.
            if string(element, kAXRoleAttribute) == "AXMenuBar" { return }
            guard depth <= 60 && nodes.count < 12000 else { throw Failure.invalid("AX_SNAPSHOT_BUDGET_EXCEEDED") }
            var row: [String: Any] = identity(element)
            row["path"] = path
            row["help"] = string(element, kAXHelpAttribute)
            row["value"] = string(element, kAXValueAttribute)
            row["placeholder"] = string(element, "AXPlaceholderValue")
            row["url"] = (attribute(element, "AXURL") as? URL)?.absoluteString ?? string(element, "AXURL")
            row["document"] = string(element, "AXDocument")
            row["filename"] = string(element, "AXFilename")
            row["subrole"] = string(element, kAXSubroleAttribute)
            row["modal"] = attribute(element, "AXModal") as? Bool ?? false
            row["role_description"] = string(element, kAXRoleDescriptionAttribute)
            row["enabled"] = attribute(element, kAXEnabledAttribute) as? Bool ?? true
            row["focused"] = attribute(element, kAXFocusedAttribute) as? Bool ?? false
            row["selected"] = attribute(element, kAXSelectedAttribute) as? Bool ?? false
            var settable = DarwinBoolean(false)
            AXUIElementIsAttributeSettable(element, kAXValueAttribute as CFString, &settable)
            row["value_settable"] = settable.boolValue
            nodes.append(row)
            for (index, child) in children(element).enumerated() { try visit(child, path + [index], depth + 1) }
        }
        try visit(app, [], 0)
        return ["status": "PASS", "pid": pid, "bundle_id": running.bundleIdentifier!,
                "executable": running.executableURL!.path,
                "frontmost_pid": NSWorkspace.shared.frontmostApplication?.processIdentifier ?? 0,
                "nodes": nodes]
    }
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else { throw Failure.invalid("LOOMY_NOT_FRONTMOST") }
    if action == "send" || action == "verify-send" {
        guard let values = request["send_guard"] as? [String: String] else { throw Failure.invalid("AX_SEND_GUARD_REQUIRED") }
        return try guardedSend(app, pid, values, press: action == "send")
    }
    guard let path = request["path"] as? [Int], path.first == 0,
          let expected = request["expected"] as? [String: String] else {
        throw Failure.invalid("AX_ACTION_TARGET_REQUIRED")
    }
    let target: AXUIElement
    if action == "press", let folder = request["workspace_guard"] as? String {
        target = try registeredWorkspace(descendants(app), folder)
    } else if action == "press", let permissionStage = request["public_permission_guard"] as? String {
        target = try publicPermissionTarget(app, pid, permissionStage)
    } else {
        target = try resolve(app, path)
    }
    guard identity(target) == expected,
          (attribute(target, kAXEnabledAttribute) as? Bool ?? true) else { throw Failure.invalid("AX_TARGET_CHANGED_OR_DISABLED") }
    if action == "press" {
        if string(target, "AXIdentifier") == "OKButton" {
            guard let folder = request["folder_guard"] as? String, folder.hasPrefix("/") else {
                throw Failure.invalid("AX_FOLDER_CONFIRM_GUARD_REQUIRED")
            }
            var pending = [try resolve(app, [0])], selectedMatches = 0, count = 0
            while let element = pending.popLast() {
                count += 1
                guard count < 12000 else { throw Failure.invalid("AX_FOLDER_CONFIRM_BUDGET") }
                if string(element, kAXRoleAttribute) == "AXRow",
                   attribute(element, kAXSelectedAttribute) as? Bool == true {
                    var rowChildren = children(element), found = false
                    while let child = rowChildren.popLast() {
                        if let url = attribute(child, "AXURL") as? URL, url.isFileURL, url.path == folder { found = true }
                        rowChildren.append(contentsOf: children(child))
                    }
                    if found { selectedMatches += 1 }
                }
                pending.append(contentsOf: children(element))
            }
            guard selectedMatches == 1 else { throw Failure.invalid("AX_FOLDER_CONFIRM_SELECTION_CHANGED") }
        }
        if string(target, kAXDescriptionAttribute) == "发送消息" {
            throw Failure.invalid("AX_SEND_REQUIRES_GUARDED_ACTION")
        }
        try checked(AXUIElementPerformAction(target, kAXPressAction as CFString), "PRESS")
    } else if action == "set-value" {
        guard let value = request["value"] as? String else { throw Failure.invalid("AX_VALUE_REQUIRED") }
        try checked(AXUIElementSetAttributeValue(target, kAXFocusedAttribute as CFString, kCFBooleanTrue), "FOCUS")
        try checked(AXUIElementSetAttributeValue(target, kAXValueAttribute as CFString, value as CFString), "SET_VALUE")
    } else if action == "select-row" {
        guard string(target, kAXRoleAttribute) == "AXRow", let folder = request["folder"] as? String,
              folder.hasPrefix("/") else { throw Failure.invalid("AX_FOLDER_ROW_REQUIRED") }
        var pending = [target], matched = 0, count = 0
        while let element = pending.popLast() {
            count += 1
            guard count < 1000 else { throw Failure.invalid("AX_FOLDER_ROW_BUDGET") }
            if let url = attribute(element, "AXURL") as? URL, url.isFileURL, url.path == folder { matched += 1 }
            pending.append(contentsOf: children(element))
        }
        guard matched == 1 else { throw Failure.invalid("AX_FOLDER_ROW_URL_CHANGED") }
        try checked(AXUIElementSetAttributeValue(target, kAXSelectedAttribute as CFString, kCFBooleanTrue), "SELECT_ROW")
    } else if action == "key" {
        let keys: [String: (CGKeyCode, CGEventFlags)] = [
            "return": (36, []), "escape": (53, []), "go-to-folder": (5, [.maskCommand, .maskShift]),
            "select-all": (0, [.maskCommand]), "backspace": (51, [])
        ]
        guard let name = request["key"] as? String, let (code, flags) = keys[name] else { throw Failure.invalid("AX_KEY_UNSUPPORTED") }
        // Native Open panels do not accept postToPid on this macOS/Electron
        // combination. HID is permitted only inside its verified Open panel.
        let windows = attribute(app, kAXWindowsAttribute) as? [AXUIElement] ?? []
        guard windows.filter({ string($0, "AXIdentifier") == "open-panel" }).count == 1,
              string(try resolve(app, [0]), "AXIdentifier") == "open-panel" else {
            throw Failure.invalid("AX_OWNED_OPEN_PANEL_REQUIRED_FOR_KEY")
        }
        var focusSettable = DarwinBoolean(false)
        AXUIElementIsAttributeSettable(target, kAXFocusedAttribute as CFString, &focusSettable)
        if focusSettable.boolValue {
            try checked(AXUIElementSetAttributeValue(target, kAXFocusedAttribute as CFString, kCFBooleanTrue), "FOCUS")
        }
        let source = CGEventSource(stateID: .hidSystemState)
        for down in [true, false] {
            guard let event = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: down) else { throw Failure.invalid("AX_KEY_EVENT_FAILED") }
            event.flags = flags
            event.post(tap: .cghidEventTap)
            if down { Thread.sleep(forTimeInterval: 0.05) }
        }
    } else { throw Failure.invalid("AX_ACTION_UNSUPPORTED") }
    return ["status": "PASS", "pid": pid, "action": action]
}
do {
    let result = try main()
    let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    let message: String
    if case Failure.invalid(let value) = error { message = value } else { message = "AX_REQUEST_FAILED" }
    let data = try! JSONSerialization.data(withJSONObject: ["status": "FAIL", "error": message])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(1)
}
