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

private func unique(_ elements: [AXUIElement], _ label: String) throws -> AXUIElement? {
    guard elements.count <= 1 else { throw SelectionError.missingElement("歧义控件：\(label)，数量=\(elements.count)") }
    return elements.first
}

private func sheetDescendants(_ element: AXUIElement) -> [AXUIElement] {
    descendants(element, role: kAXSheetRole).filter { !CFEqual($0, element) }
}

private func uniqueButton(_ element: AXUIElement, titles: Set<String>) throws -> AXUIElement? {
    try unique(descendants(element, role: kAXButtonRole).filter {
        titles.contains(stringAttribute($0, kAXTitleAttribute)) && boolAttribute($0, kAXEnabledAttribute)
    }, "button")
}

private func elementTexts(_ element: AXUIElement) -> [String] {
    return [
        stringAttribute(element, kAXTitleAttribute),
        stringAttribute(element, kAXValueAttribute),
        stringAttribute(element, kAXDescriptionAttribute),
    ].filter { !$0.isEmpty }
}

private func descendantElements(_ element: AXUIElement, maximumDepth: Int = 10, depth: Int = 0) -> [AXUIElement] {
    var values = [element]
    guard depth < maximumDepth else { return values }
    for child in children(element) {
        values.append(contentsOf: descendantElements(child, maximumDepth: maximumDepth, depth: depth + 1))
    }
    return values
}

private func press(_ element: AXUIElement, action: String) throws {
    let result = AXUIElementPerformAction(element, kAXPressAction as CFString)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func setAttribute(_ element: AXUIElement, name: String, value: CFTypeRef, action: String) throws {
    let result = AXUIElementSetAttributeValue(element, name as CFString, value)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func waitUntil<T>(timeoutSeconds: Double, description: String, operation: () throws -> T?) throws -> T {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    repeat {
        if let value = try operation() { return value }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    throw SelectionError.timeout(description)
}

// Native Open panels ignore postToPid on this macOS/Electron combination.
// Before HID delivery, require the expected foreground process and its single
// live file-picker sheet; no lookup or input targets another application's UI.
private func postShortcut(processIdentifier: pid_t, virtualKey: CGKeyCode, flags: CGEventFlags = []) throws {
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == processIdentifier else {
        throw SelectionError.missingElement("QwenWork 已失去前台焦点，停止键盘输入")
    }
    let root = AXUIElementCreateApplication(processIdentifier)
    let windows = attribute(root, kAXWindowsAttribute) as? [AXUIElement] ?? []
    let panels = windows.flatMap { children($0).filter { stringAttribute($0, kAXRoleAttribute) == kAXSheetRole } }
    guard panels.count == 1 else { throw SelectionError.missingElement("QwenWork 唯一文件选择面板") }
    let source = CGEventSource(stateID: .hidSystemState)
    guard let keyDown = CGEvent(keyboardEventSource: source, virtualKey: virtualKey, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: source, virtualKey: virtualKey, keyDown: false) else {
        throw SelectionError.missingElement("无法创建键盘事件")
    }
    keyDown.flags = flags
    keyUp.flags = flags
    keyDown.post(tap: .cghidEventTap)
    keyUp.post(tap: .cghidEventTap)
}

private func selectFolder(bundleID: String, folderPath: String, timeoutSeconds: Double) throws -> String {
    guard AXIsProcessTrusted() else { throw SelectionError.accessibilityPermission }
    let apps = NSWorkspace.shared.runningApplications.filter {
        $0.bundleIdentifier == bundleID && !$0.isTerminated && $0.activationPolicy == .regular
    }
    guard apps.count == 1, let application = apps.first else { throw SelectionError.appNotRunning(bundleID) }
    application.activate(options: [])
    let root = AXUIElementCreateApplication(application.processIdentifier)
    let outerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "QwenWork 唯一文件选择面板") {
        let windows = attribute(root, kAXWindowsAttribute) as? [AXUIElement] ?? []
        return try unique(windows.flatMap { children($0).filter { stringAttribute($0, kAXRoleAttribute) == kAXSheetRole } }, "outer-sheet")
    }
    do {
        if sheetDescendants(outerSheet).isEmpty {
            try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 5, flags: [.maskCommand, .maskShift])
        }
        let innerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板") {
            try unique(sheetDescendants(outerSheet), "go-to-folder-sheet")
        }
        let pathField = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹路径输入框") {
            try unique(descendants(innerSheet, role: kAXTextFieldRole).filter {
                boolAttribute($0, kAXFocusedAttribute)
            }, "focused-path-field")
        }
        let navigationPath = (folderPath as NSString).deletingLastPathComponent
        try setAttribute(pathField, name: kAXValueAttribute, value: navigationPath as CFString, action: "设置父目录路径")
        guard stringAttribute(pathField, kAXValueAttribute) == navigationPath else {
            throw SelectionError.missingElement("路径回读不一致")
        }
        try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 36)
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板关闭") {
            sheetDescendants(outerSheet).isEmpty ? true : nil
        }
        let folderName = (folderPath as NSString).lastPathComponent
        let targetRow = try waitUntil(timeoutSeconds: timeoutSeconds, description: "目标文件夹行") {
            try unique(descendants(outerSheet, role: kAXRowRole).filter { row in
                descendantElements(row).flatMap(elementTexts).contains(folderName)
            }, "target-folder-row")
        }
        try setAttribute(targetRow, name: kAXSelectedAttribute, value: kCFBooleanTrue, action: "选择目标文件夹")
        guard boolAttribute(targetRow, kAXSelectedAttribute) else { throw SelectionError.missingElement("目标行未选中") }
        let openButton = try waitUntil(timeoutSeconds: timeoutSeconds, description: "打开按钮") {
            try uniqueButton(outerSheet, titles: ["打开", "Open", "选择", "Choose", "选取", "Select"])
        }
        try press(openButton, action: "确认目标目录")
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "文件选择面板关闭") {
            let windows = attribute(root, kAXWindowsAttribute) as? [AXUIElement] ?? []
            return windows.flatMap { descendants($0, role: kAXSheetRole) }.isEmpty ? true : nil
        }
        return "foreground-owner-guarded-hid+unique-ax-row"
    } catch {
        // Cancel only the innermost panel belonging to the verified QwenWork sheet.
        let nested = sheetDescendants(outerSheet)
        let scope = nested.count == 1 ? nested[0] : outerSheet
        if let cancel = try? uniqueButton(scope, titles: ["取消", "Cancel"]) {
            _ = AXUIElementPerformAction(cancel, kAXPressAction as CFString)
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
    let confirmMethod = try selectFolder(bundleID: bundleID, folderPath: folderPath, timeoutSeconds: timeoutSeconds)
    let output: [String: Any] = [
        "status": "selected",
        "method": "macos-accessibility",
        "owner_binding": "qwen-application-ax-sheet-descendant-only",
        "confirm_method": confirmMethod,
        "folder": folderPath,
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
    FileHandle.standardError.write(Data("\(message)\n".utf8))
    exit(1)
}
