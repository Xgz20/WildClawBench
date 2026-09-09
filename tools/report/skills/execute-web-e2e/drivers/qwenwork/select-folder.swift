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

private func waitUntil<T>(timeoutSeconds: Double, description: String, operation: () -> T?) throws -> T {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    repeat {
        if let value = operation() { return value }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    throw SelectionError.timeout(description)
}

private func postShortcut(processIdentifier: pid_t, virtualKey: CGKeyCode, flags: CGEventFlags = []) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: false) else {
        throw SelectionError.missingElement("无法创建键盘事件")
    }
    keyDown.flags = flags
    keyUp.flags = flags
    keyDown.post(tap: .cghidEventTap)
    keyUp.post(tap: .cghidEventTap)
}

private func postText(processIdentifier: pid_t, text: String) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: false) else {
        throw SelectionError.missingElement("无法创建文本输入事件")
    }
    let characters = Array(text.utf16)
    characters.withUnsafeBufferPointer { buffer in
        keyDown.keyboardSetUnicodeString(stringLength: buffer.count, unicodeString: buffer.baseAddress!)
        keyUp.keyboardSetUnicodeString(stringLength: 0, unicodeString: nil)
    }
    keyDown.post(tap: .cghidEventTap)
    keyUp.post(tap: .cghidEventTap)
}

private typealias PasteboardSnapshot = [[NSPasteboard.PasteboardType: Data]]

private func snapshotPasteboard(_ pasteboard: NSPasteboard) -> PasteboardSnapshot {
    return pasteboard.pasteboardItems?.map { item in
        var values: [NSPasteboard.PasteboardType: Data] = [:]
        for type in item.types {
            if let data = item.data(forType: type) { values[type] = data }
        }
        return values
    } ?? []
}

private func restorePasteboard(_ pasteboard: NSPasteboard, snapshot: PasteboardSnapshot) {
    pasteboard.clearContents()
    let items: [NSPasteboardItem] = snapshot.map { values in
        let item = NSPasteboardItem()
        for (type, data) in values { item.setData(data, forType: type) }
        return item
    }
    if !items.isEmpty { pasteboard.writeObjects(items) }
}

private struct OpenPanelContext {
    let processIdentifier: pid_t
    let root: AXUIElement
    let window: AXUIElement
}

private func openPanelProcessIdentifiers() -> [pid_t] {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
    process.arguments = ["-f", "/com.apple.appkit.xpc.openAndSavePanelService$"]
    process.standardOutput = pipe
    process.standardError = FileHandle.nullDevice
    do {
        try process.run()
        process.waitUntilExit()
    } catch {
        return []
    }
    let output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    return output.split(whereSeparator: \.isNewline).compactMap { pid_t($0) }
}

private func currentOpenPanel() -> OpenPanelContext? {
    for processIdentifier in openPanelProcessIdentifiers().reversed() {
        let root = AXUIElementCreateApplication(processIdentifier)
        let windows = attribute(root, kAXWindowsAttribute) as? [AXUIElement] ?? []
        if let window = windows.first(where: { candidate in
            firstButton(candidate, titles: ["取消", "Cancel"]) != nil
                && firstButton(candidate, titles: ["打开", "Open"]) != nil
        }) {
            return OpenPanelContext(processIdentifier: processIdentifier, root: root, window: window)
        }
    }
    return nil
}

private func cancelOpenPanelIfPresent(_ panel: OpenPanelContext) {
    guard let cancelButton = firstButton(panel.window, titles: ["取消", "Cancel"]) else { return }
    _ = AXUIElementPerformAction(cancelButton, kAXPressAction as CFString)
}

private func selectFolder(bundleID: String, folderPath: String, timeoutSeconds: Double) throws -> String {
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
    let window = try waitUntil(timeoutSeconds: timeoutSeconds, description: "QwenWork 主窗口") {
        (attribute(root, kAXWindowsAttribute) as? [AXUIElement])?.first
    }
    let outerSheet = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板") {
        descendants(window, role: kAXSheetRole).first
    }
    do {
        try postShortcut(
            processIdentifier: application.processIdentifier,
            virtualKey: 5,
            flags: [.maskCommand, .maskShift]
        )
        let pathField: AXUIElement = try waitUntil(timeoutSeconds: timeoutSeconds, description: "前往文件夹路径输入框") {
            return descendants(outerSheet, role: kAXTextFieldRole).first { field in
                boolAttribute(field, kAXFocusedAttribute)
            }
        }
        try setAttribute(pathField, name: kAXFocusedAttribute, value: kCFBooleanTrue, action: "聚焦文件夹路径输入框")
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 0, flags: [.maskCommand])
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        let pasteboard = NSPasteboard.general
        let pasteboardSnapshot = snapshotPasteboard(pasteboard)
        defer { restorePasteboard(pasteboard, snapshot: pasteboardSnapshot) }
        let navigationPath = (folderPath as NSString).deletingLastPathComponent
        pasteboard.clearContents()
        pasteboard.setString(navigationPath, forType: .string)
        try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 9, flags: [.maskCommand])
        let inputDeadline = Date().addingTimeInterval(min(timeoutSeconds, 5))
        while stringAttribute(pathField, kAXValueAttribute) != navigationPath && Date() < inputDeadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        guard stringAttribute(pathField, kAXValueAttribute) == navigationPath else {
            throw SelectionError.missingElement(
                "文件夹路径输入回读；实际值=\(stringAttribute(pathField, kAXValueAttribute))；属性=\(elementTexts(pathField).joined(separator: "|"))"
            )
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))

        var confirmMethod = "go-button"
        let innerButtons = descendants(outerSheet, role: kAXButtonRole)
        let innerConfirmButton = firstButton(outerSheet, titles: ["前往", "Go"])
            ?? innerButtons.first { button in
                boolAttribute(button, kAXEnabledAttribute)
                    && stringAttribute(button, kAXSubroleAttribute) == "AXDefaultButton"
            }
        if let goButton = innerConfirmButton {
            confirmMethod = stringAttribute(goButton, kAXTitleAttribute).isEmpty ? "default-button" : "go-button"
            try press(goButton, action: "前往目标目录")
        } else {
            confirmMethod = "return-key"
            try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 36)
        }
        let folderName = (folderPath as NSString).lastPathComponent
        let rowDeadline = Date().addingTimeInterval(min(timeoutSeconds, 5))
        var targetRow: AXUIElement?
        var observedRows: [String] = []
        repeat {
            let rows = descendants(outerSheet, role: kAXRowRole)
            observedRows = rows.map { row in
                Array(Set(descendantElements(row).flatMap(elementTexts))).sorted().joined(separator: "|")
            }
            targetRow = rows.first { row in
                descendantElements(row).flatMap(elementTexts).contains(folderName)
            }
            if targetRow == nil { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        } while targetRow == nil && Date() < rowDeadline
        guard let confirmedRow = targetRow else {
            throw SelectionError.missingElement("父目录中的目标文件夹行；观察到：\(observedRows.joined(separator: ", "))")
        }
        try setAttribute(confirmedRow, name: kAXSelectedAttribute, value: kCFBooleanTrue, action: "选择目标文件夹行")
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        let openButtonTitles: Set<String> = ["打开", "Open", "选择", "Choose", "选取", "Select", "确定", "OK"]
        let buttonDeadline = Date().addingTimeInterval(timeoutSeconds)
        var openButton: AXUIElement?
        var observedButtons: [String] = []
        repeat {
            let buttons = descendants(outerSheet, role: kAXButtonRole)
            observedButtons = buttons.map { button in
                let title = stringAttribute(button, kAXTitleAttribute)
                let subrole = stringAttribute(button, kAXSubroleAttribute)
                return "\(title.isEmpty ? "<空>" : title){\(subrole.isEmpty ? "无子角色" : subrole),enabled=\(boolAttribute(button, kAXEnabledAttribute))}"
            }
            openButton = buttons.first { button in
                let title = stringAttribute(button, kAXTitleAttribute)
                let subrole = stringAttribute(button, kAXSubroleAttribute)
                return boolAttribute(button, kAXEnabledAttribute)
                    && (openButtonTitles.contains(title) || subrole == "AXDefaultButton")
            }
            if openButton == nil { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        } while openButton == nil && Date() < buttonDeadline
        guard let confirmedButton = openButton else {
            throw SelectionError.missingElement("已启用的目录确认按钮；观察到：\(observedButtons.joined(separator: ", "))")
        }
        try press(confirmedButton, action: "选择目标目录")
        let _: Bool = try waitUntil(timeoutSeconds: timeoutSeconds, description: "外层打开文件夹面板关闭") {
            let currentRoot = AXUIElementCreateApplication(application.processIdentifier)
            guard let currentWindow = (attribute(currentRoot, kAXWindowsAttribute) as? [AXUIElement])?.first else { return nil }
            return descendants(currentWindow, role: kAXSheetRole).isEmpty ? true : nil
        }
        return confirmMethod
    } catch {
        if let cancelButton = firstButton(outerSheet, titles: ["取消", "Cancel"]) {
            _ = AXUIElementPerformAction(cancelButton, kAXPressAction as CFString)
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
