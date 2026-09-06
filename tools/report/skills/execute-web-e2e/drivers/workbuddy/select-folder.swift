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

private func firstButton(_ element: AXUIElement, titles: Set<String>) -> AXUIElement? {
    return descendants(element, role: kAXButtonRole).first { titles.contains(stringAttribute($0, kAXTitleAttribute)) }
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

private func postGoToFolderShortcut(processIdentifier: pid_t) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: 5, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: 5, keyDown: false) else {
        throw SelectionError.missingElement("无法创建 Cmd+Shift+G 键盘事件")
    }
    keyDown.flags = [.maskCommand, .maskShift]
    keyUp.flags = [.maskCommand, .maskShift]
    // Codex/终端发起自动化时，宿主可能立即夺回前台焦点。将快捷键直接
    // 投递给 WorkBuddy 主进程，避免把 Cmd+Shift+G 发到错误的应用。
    keyDown.postToPid(processIdentifier)
    keyUp.postToPid(processIdentifier)
}

private func cancelOuterPanelIfPresent(_ window: AXUIElement) {
    guard let outerSheet = descendants(window, role: kAXSheetRole).first,
          let cancelButton = firstButton(outerSheet, titles: ["取消", "Cancel"]) else { return }
    _ = AXUIElementPerformAction(cancelButton, kAXPressAction as CFString)
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
    let window = try waitUntil(timeoutSeconds: timeoutSeconds, description: "WorkBuddy 主窗口") {
        (attribute(root, kAXWindowsAttribute) as? [AXUIElement])?.first
    }
    do {
        let outerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板") {
            descendants(window, role: kAXSheetRole).first
        }
        try postGoToFolderShortcut(processIdentifier: application.processIdentifier)
        let innerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板") {
            descendants(outerSheet, role: kAXSheetRole).first
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        guard let pathField = firstDescendant(innerSheet, role: kAXTextFieldRole) else {
            throw SelectionError.missingElement("前往文件夹路径输入框")
        }
        try setAttribute(pathField, name: kAXValueAttribute, value: folderPath as CFString, action: "设置文件夹路径")
        try setAttribute(pathField, name: kAXFocusedAttribute, value: kCFBooleanTrue, action: "聚焦文件夹路径输入框")
        RunLoop.current.run(until: Date().addingTimeInterval(2.0))
        let refreshedRoot = AXUIElementCreateApplication(application.processIdentifier)
        let goButton = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往按钮") {
            firstButton(refreshedRoot, titles: ["前往", "Go"])
        }
        try press(goButton, action: "前往目标目录")
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
        cancelOuterPanelIfPresent(window)
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
