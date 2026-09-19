#!/usr/bin/env swift

import AppKit
import ApplicationServices
import Foundation

private enum SelectionError: LocalizedError {
    case usage
    case accessibilityPermission
    case appNotRunning(String)
    case ambiguousApp(Int)
    case timeout(String)
    case missingElement(String)
    case unsafePath(String)
    case actionFailed(String, AXError)

    var errorDescription: String? {
        switch self {
        case .usage: return "用法：select-folder.swift <bundle-id> <绝对目录> <超时秒数>"
        case .accessibilityPermission: return "当前终端没有 macOS 辅助功能权限"
        case let .appNotRunning(bundleID): return "找不到正在运行的应用：\(bundleID)"
        case let .ambiguousApp(count): return "发现 \(count) 个可控制的 DoubaoWork 主应用，拒绝猜测目标"
        case let .timeout(message): return "等待超时：\(message)"
        case let .missingElement(message): return "找不到原生文件夹选择器元素：\(message)"
        case let .unsafePath(message): return "目录路径不安全：\(message)"
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

private func descendants(
    _ element: AXUIElement,
    role: String,
    maximumDepth: Int = 16,
    depth: Int = 0
) -> [AXUIElement] {
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
    return descendants(element, role: kAXButtonRole).first {
        titles.contains(stringAttribute($0, kAXTitleAttribute))
    }
}

private func press(_ element: AXUIElement, action: String) throws {
    let result = AXUIElementPerformAction(element, kAXPressAction as CFString)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func setAttribute(_ element: AXUIElement, name: String, value: CFTypeRef, action: String) throws {
    let result = AXUIElementSetAttributeValue(element, name as CFString, value)
    guard result == .success else { throw SelectionError.actionFailed(action, result) }
}

private func waitUntil<T>(
    timeoutSeconds: Double,
    description: String,
    operation: () -> T?
) throws -> T {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    repeat {
        if let value = operation() { return value }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    throw SelectionError.timeout(description)
}

private func postShortcut(
    processIdentifier: pid_t,
    key: CGKeyCode,
    flags: CGEventFlags = [],
    global: Bool = false
) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: key, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: key, keyDown: false) else {
        throw SelectionError.missingElement("无法创建键盘事件")
    }
    keyDown.flags = flags
    keyUp.flags = flags
    if global {
        keyDown.post(tap: .cghidEventTap)
        keyUp.post(tap: .cghidEventTap)
    } else {
        keyDown.postToPid(processIdentifier)
        keyUp.postToPid(processIdentifier)
    }
}

private func focusPathField(_ field: AXUIElement, application: NSRunningApplication) throws {
    application.activate(options: [])
    RunLoop.current.run(until: Date().addingTimeInterval(0.2))
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == application.processIdentifier else {
        throw SelectionError.missingElement("DoubaoWork 未处于前台，拒绝发送全局按键")
    }
    guard let position = attribute(field, kAXPositionAttribute),
          let size = attribute(field, kAXSizeAttribute) else {
        throw SelectionError.missingElement("路径框位置")
    }
    var point = CGPoint.zero
    var dimensions = CGSize.zero
    guard AXValueGetValue(position as! AXValue, .cgPoint, &point),
          AXValueGetValue(size as! AXValue, .cgSize, &dimensions) else {
        throw SelectionError.missingElement("路径框坐标")
    }
    point.x += dimensions.width / 2
    point.y += dimensions.height / 2
    for kind: CGEventType in [.leftMouseDown, .leftMouseUp] {
        CGEvent(
            mouseEventSource: nil,
            mouseType: kind,
            mouseCursorPosition: point,
            mouseButton: .left
        )?.post(tap: .cghidEventTap)
    }
    RunLoop.current.run(until: Date().addingTimeInterval(0.2))
}

private func cancelOuterPanelIfPresent(_ window: AXUIElement) {
    guard let outerSheet = descendants(window, role: kAXSheetRole).first,
          let cancelButton = firstButton(outerSheet, titles: ["取消", "Cancel"]) else { return }
    _ = AXUIElementPerformAction(cancelButton, kAXPressAction as CFString)
}

private func validateFolderPath(_ folderPath: String) throws -> String {
    guard folderPath.hasPrefix("/") && !folderPath.contains("\n") && !folderPath.contains("\0") else {
        throw SelectionError.unsafePath("必须提供不含换行或 NUL 的绝对路径")
    }
    let requested = URL(fileURLWithPath: folderPath).standardizedFileURL.path
    let canonical = URL(fileURLWithPath: requested).resolvingSymlinksInPath().standardizedFileURL.path
    guard requested == canonical else {
        throw SelectionError.unsafePath("目标路径包含符号链接，无法证明客户端回读与真实目录唯一对应")
    }
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: canonical, isDirectory: &isDirectory), isDirectory.boolValue else {
        throw SelectionError.missingElement("目录不存在：\(canonical)")
    }
    return canonical
}

private func selectFolder(bundleID: String, folderPath: String, timeoutSeconds: Double) throws {
    guard AXIsProcessTrusted() else { throw SelectionError.accessibilityPermission }
    let matchingApplications = NSWorkspace.shared.runningApplications.filter {
        $0.bundleIdentifier == bundleID && !$0.isTerminated && $0.activationPolicy == .regular
    }
    guard !matchingApplications.isEmpty else { throw SelectionError.appNotRunning(bundleID) }
    guard matchingApplications.count == 1 else { throw SelectionError.ambiguousApp(matchingApplications.count) }
    let application = matchingApplications[0]

    application.activate(options: [])
    RunLoop.current.run(until: Date().addingTimeInterval(0.3))
    let root = AXUIElementCreateApplication(application.processIdentifier)
    let window = try waitUntil(timeoutSeconds: timeoutSeconds, description: "DoubaoWork 主窗口") {
        (attribute(root, kAXWindowsAttribute) as? [AXUIElement])?.first
    }
    do {
        let outerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板") {
            descendants(window, role: kAXSheetRole).first
        }
        try postShortcut(
            processIdentifier: application.processIdentifier,
            key: 5,
            flags: [.maskCommand, .maskShift]
        )
        let innerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板") {
            descendants(outerSheet, role: kAXSheetRole).first
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        guard let pathField = firstDescendant(innerSheet, role: kAXTextFieldRole) else {
            throw SelectionError.missingElement("前往文件夹路径输入框")
        }
        try setAttribute(
            pathField,
            name: kAXFocusedAttribute,
            value: kCFBooleanTrue,
            action: "聚焦文件夹路径输入框"
        )
        try focusPathField(pathField, application: application)

        let pasteboard = NSPasteboard.general
        let savedItems = pasteboard.pasteboardItems?.map { item in
            Dictionary(uniqueKeysWithValues: item.types.compactMap { type in
                item.data(forType: type).map { (type, $0) }
            })
        } ?? []
        defer {
            pasteboard.clearContents()
            let restored = savedItems.map { values in
                let item = NSPasteboardItem()
                for (type, data) in values { item.setData(data, forType: type) }
                return item
            }
            if !restored.isEmpty { pasteboard.writeObjects(restored) }
        }
        pasteboard.clearContents()
        pasteboard.setString(folderPath, forType: .string)
        try postShortcut(
            processIdentifier: application.processIdentifier,
            key: 0,
            flags: [.maskCommand],
            global: true
        )
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        try postShortcut(
            processIdentifier: application.processIdentifier,
            key: 9,
            flags: [.maskCommand],
            global: true
        )
        RunLoop.current.run(until: Date().addingTimeInterval(0.5))

        let currentRoot = AXUIElementCreateApplication(application.processIdentifier)
        let currentSheets = descendants(currentRoot, role: kAXSheetRole)
        if currentSheets.count > 1 {
            guard let freshField = currentSheets.last.flatMap({ firstDescendant($0, role: kAXTextFieldRole) }),
                  stringAttribute(freshField, kAXValueAttribute) == folderPath else {
                throw SelectionError.missingElement("目标文件夹完整路径回读不一致")
            }
            try postShortcut(processIdentifier: application.processIdentifier, key: 36, global: true)
        }
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹面板关闭") {
            let freshRoot = AXUIElementCreateApplication(application.processIdentifier)
            return descendants(freshRoot, role: kAXSheetRole).count == 1 ? true : nil
        }
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "目标目录位置回读") {
            let freshRoot = AXUIElementCreateApplication(application.processIdentifier)
            guard let currentSheet = descendants(freshRoot, role: kAXSheetRole).first else { return nil }
            let expectedName = URL(fileURLWithPath: folderPath).lastPathComponent
            return descendants(currentSheet, role: kAXPopUpButtonRole).contains {
                stringAttribute($0, kAXValueAttribute) == expectedName
            } ? true : nil
        }
        let openButton: AXUIElement = try waitUntil(
            timeoutSeconds: timeoutSeconds,
            description: "已启用的选择按钮"
        ) {
            let freshRoot = AXUIElementCreateApplication(application.processIdentifier)
            guard let currentOuterSheet = descendants(freshRoot, role: kAXSheetRole).first,
                  let button = firstButton(
                    currentOuterSheet,
                    titles: ["选择", "Choose", "选取", "Select", "打开", "Open"]
                  ),
                  boolAttribute(button, kAXEnabledAttribute) else { return nil }
            return button
        }
        try press(openButton, action: "选择目标目录")
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板关闭") {
            let freshRoot = AXUIElementCreateApplication(application.processIdentifier)
            return descendants(freshRoot, role: kAXSheetRole).isEmpty ? true : nil
        }
    } catch {
        cancelOuterPanelIfPresent(window)
        throw error
    }
}

do {
    guard CommandLine.arguments.count == 4 else { throw SelectionError.usage }
    let bundleID = CommandLine.arguments[1]
    guard bundleID == "com.work.pc.doubao" else { throw SelectionError.usage }
    let folderPath = try validateFolderPath(CommandLine.arguments[2])
    guard let timeoutSeconds = Double(CommandLine.arguments[3]), timeoutSeconds > 0 else {
        throw SelectionError.usage
    }
    try selectFolder(bundleID: bundleID, folderPath: folderPath, timeoutSeconds: timeoutSeconds)
    let output: [String: Any] = [
        "status": "selected",
        "method": "macos-accessibility",
        "folder": folderPath,
        "requires_client_full_path_readback": true,
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
    FileHandle.standardError.write(Data("\(message)\n".utf8))
    exit(1)
}

