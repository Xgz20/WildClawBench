#!/usr/bin/env swift

import AppKit
import ApplicationServices
import Foundation

private enum SelectionError: LocalizedError {
    case usage
    case accessibilityPermission
    case appNotRunning(String)
    case timeout(String)
    case missingElement(String)
    case actionFailed(String, AXError)

    var errorDescription: String? {
        switch self {
        case .usage: return "用法：select-folder.swift <bundle-id> <目录> <超时秒数>"
        case .accessibilityPermission: return "当前终端没有 macOS 辅助功能权限"
        case let .appNotRunning(bundleID): return "找不到正在运行的应用：\(bundleID)"
        case let .timeout(message): return "等待超时：\(message)"
        case let .missingElement(message): return "找不到原生文件夹选择器元素：\(message)"
        case let .actionFailed(action, error): return "原生文件夹选择器操作失败：\(action)（AXError=\(error.rawValue)）"
        }
    }
}

private func attribute(_ element: AXUIElement, _ name: String) -> AnyObject? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
    return value
}

private func stringAttribute(_ element: AXUIElement, _ name: String) -> String {
    guard let value = attribute(element, name) else { return "" }
    return String(describing: value)
}

private func boolAttribute(_ element: AXUIElement, _ name: String) -> Bool {
    guard let value = attribute(element, name) else { return false }
    return CFBooleanGetValue((value as! CFBoolean))
}

private func children(_ element: AXUIElement) -> [AXUIElement] {
    return attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
}

private func descendants(_ element: AXUIElement, role: String, maximumDepth: Int = 16, depth: Int = 0) -> [AXUIElement] {
    var matches: [AXUIElement] = []
    if stringAttribute(element, kAXRoleAttribute) == role { matches.append(element) }
    guard depth < maximumDepth else { return matches }
    for child in children(element) {
        matches.append(contentsOf: descendants(child, role: role, maximumDepth: maximumDepth, depth: depth + 1))
    }
    return matches
}

private func firstDescendant(_ element: AXUIElement, role: String) -> AXUIElement? {
    return descendants(element, role: role).first
}

private func firstNestedDescendant(_ element: AXUIElement, role: String) -> AXUIElement? {
    for child in children(element) {
        if let match = firstDescendant(child, role: role) { return match }
    }
    return nil
}

private func elementLabels(_ element: AXUIElement) -> Set<String> {
    let attributes = [
        kAXTitleAttribute,
        kAXDescriptionAttribute,
        kAXValueAttribute,
        kAXHelpAttribute,
    ]
    return Set(attributes.map { stringAttribute(element, $0) }.filter { !$0.isEmpty })
}

private func firstButton(_ element: AXUIElement, titles: Set<String>) -> AXUIElement? {
    return descendants(element, role: kAXButtonRole).first { !elementLabels($0).isDisjoint(with: titles) }
}

private func press(_ element: AXUIElement, action: String) throws {
    let result = AXUIElementPerformAction(element, kAXPressAction as CFString)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func setAttribute(_ element: AXUIElement, name: String, value: CFTypeRef, action: String) throws {
    let result = AXUIElementSetAttributeValue(element, name as CFString, value)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func waitUntil<T>(timeoutSeconds: Double, description: String, operation: () -> T?) throws -> T {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    repeat {
        if let value = operation() { return value }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    throw SelectionError.timeout(description)
}

private func postKey(virtualKey: CGKeyCode, flags: CGEventFlags = []) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: false) else {
        throw SelectionError.missingElement("无法创建键盘事件：\(virtualKey)")
    }
    keyDown.flags = flags
    keyUp.flags = flags
    keyDown.post(tap: .cghidEventTap)
    keyUp.post(tap: .cghidEventTap)
}

private func postGoToFolderShortcut() throws {
    try postKey(virtualKey: 5, flags: [.maskCommand, .maskShift])
}

private func cancelOuterPanelIfPresent(_ window: AXUIElement) {
    guard let outerSheet = descendants(window, role: kAXSheetRole).first,
          let cancelButton = firstButton(outerSheet, titles: ["取消", "Cancel"]) else { return }
    _ = AXUIElementPerformAction(cancelButton, kAXPressAction as CFString)
}

private func applicationWindows(_ application: AXUIElement) -> [AXUIElement] {
    return attribute(application, kAXWindowsAttribute) as? [AXUIElement] ?? []
}

private func selectFolder(bundleID: String, folderPath: String, timeoutSeconds: Double) throws {
    guard AXIsProcessTrusted() else { throw SelectionError.accessibilityPermission }
    let matchingApplications = NSWorkspace.shared.runningApplications.filter {
        $0.bundleIdentifier == bundleID && !$0.isTerminated
    }
    guard let application = matchingApplications.first(where: { $0.activationPolicy == .regular })
        ?? matchingApplications.first else {
        throw SelectionError.appNotRunning(bundleID)
    }
    application.activate(options: [.activateIgnoringOtherApps])
    RunLoop.current.run(until: Date().addingTimeInterval(0.3))
    let root = AXUIElementCreateApplication(application.processIdentifier)
    let _: [AXUIElement] = try waitUntil(timeoutSeconds: timeoutSeconds, description: "应用窗口") {
        let windows = applicationWindows(root)
        return windows.isEmpty ? nil : windows
    }
    do {
        let outerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板") {
            applicationWindows(root).lazy.compactMap {
                descendants($0, role: kAXSheetRole).first
            }.first
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        try postGoToFolderShortcut()
        let innerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板") {
            firstNestedDescendant(outerSheet, role: kAXSheetRole)
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        guard let pathField = firstDescendant(innerSheet, role: kAXTextFieldRole) else {
            throw SelectionError.missingElement("前往文件夹路径输入框")
        }
        try setAttribute(pathField, name: kAXValueAttribute, value: folderPath as CFString, action: "设置文件夹路径")
        try setAttribute(pathField, name: kAXFocusedAttribute, value: kCFBooleanTrue, action: "聚焦文件夹路径输入框")
        guard stringAttribute(pathField, kAXValueAttribute) == folderPath else {
            throw SelectionError.missingElement("前往文件夹路径回读不一致")
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        try postKey(virtualKey: 36)
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板关闭") {
            let currentRoot = AXUIElementCreateApplication(application.processIdentifier)
            return descendants(currentRoot, role: kAXSheetRole).count == 1 ? true : nil
        }
        let openButton: AXUIElement = try waitUntil(timeoutSeconds: timeoutSeconds, description: "已启用的打开按钮") {
            let currentRoot = AXUIElementCreateApplication(application.processIdentifier)
            guard let currentOuterSheet = descendants(currentRoot, role: kAXSheetRole).first,
                  let button = firstButton(currentOuterSheet, titles: ["打开", "Open"]),
                  boolAttribute(button, kAXEnabledAttribute) else { return nil }
            return button
        }
        try press(openButton, action: "选择目标目录")
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板关闭") {
            let currentRoot = AXUIElementCreateApplication(application.processIdentifier)
            return descendants(currentRoot, role: kAXSheetRole).isEmpty ? true : nil
        }
    } catch {
        for window in applicationWindows(root) {
            cancelOuterPanelIfPresent(window)
        }
        throw error
    }
}

do {
    guard CommandLine.arguments.count == 4 else { throw SelectionError.usage }
    let bundleID = CommandLine.arguments[1]
    let folderPath = CommandLine.arguments[2]
    guard let timeoutSeconds = Double(CommandLine.arguments[3]), timeoutSeconds > 0 else { throw SelectionError.usage }
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: folderPath, isDirectory: &isDirectory), isDirectory.boolValue else {
        throw SelectionError.missingElement("目录不存在：\(folderPath)")
    }
    try selectFolder(bundleID: bundleID, folderPath: folderPath, timeoutSeconds: timeoutSeconds)
    let output: [String: Any] = ["status": "selected", "method": "macos-accessibility", "folder": folderPath]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
    FileHandle.standardError.write(Data("\(message)\n".utf8))
    exit(1)
}
