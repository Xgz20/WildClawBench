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

private func elementCenter(_ element: AXUIElement) throws -> CGPoint {
    guard let positionValue = attribute(element, kAXPositionAttribute),
          let sizeValue = attribute(element, kAXSizeAttribute) else {
        throw SelectionError.missingElement("控件坐标或尺寸")
    }
    var position = CGPoint.zero
    var size = CGSize.zero
    guard AXValueGetValue(positionValue as! AXValue, .cgPoint, &position),
          AXValueGetValue(sizeValue as! AXValue, .cgSize, &size) else {
        throw SelectionError.missingElement("控件坐标或尺寸回读")
    }
    return CGPoint(x: position.x + size.width / 2, y: position.y + size.height / 2)
}

private func click(_ element: AXUIElement) throws {
    let point = try elementCenter(element)
    guard let mouseDown = CGEvent(
        mouseEventSource: nil,
        mouseType: .leftMouseDown,
        mouseCursorPosition: point,
        mouseButton: .left
    ), let mouseUp = CGEvent(
        mouseEventSource: nil,
        mouseType: .leftMouseUp,
        mouseCursorPosition: point,
        mouseButton: .left
    ) else {
        throw SelectionError.missingElement("无法创建鼠标点击事件")
    }
    mouseDown.post(tap: .cghidEventTap)
    mouseUp.post(tap: .cghidEventTap)
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
    keyDown.postToPid(processIdentifier)
    keyUp.postToPid(processIdentifier)
}

private func postShortcutGlobally(virtualKey: CGKeyCode, flags: CGEventFlags = []) throws {
    guard let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: true),
          let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: virtualKey, keyDown: false) else {
        throw SelectionError.missingElement("无法创建全局键盘事件")
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
        let pathFieldDeadline = Date().addingTimeInterval(timeoutSeconds)
        var detectedPathField: AXUIElement?
        var shortcutAttempt = 0
        repeat {
            shortcutAttempt += 1
            application.activate(options: [.activateIgnoringOtherApps])
            _ = AXUIElementSetAttributeValue(root, kAXFrontmostAttribute as CFString, kCFBooleanTrue)
            let panelContext = currentOpenPanel()
            if let panelContext = panelContext {
                _ = AXUIElementSetAttributeValue(
                    panelContext.root,
                    kAXFrontmostAttribute as CFString,
                    kCFBooleanTrue
                )
                _ = AXUIElementSetAttributeValue(
                    panelContext.window,
                    kAXFocusedAttribute as CFString,
                    kCFBooleanTrue
                )
            }
            switch shortcutAttempt % 3 {
            case 1:
                try postShortcut(
                    processIdentifier: panelContext?.processIdentifier ?? application.processIdentifier,
                    virtualKey: 5,
                    flags: [.maskCommand, .maskShift]
                )
            case 2:
                try postShortcut(
                    processIdentifier: application.processIdentifier,
                    virtualKey: 5,
                    flags: [.maskCommand, .maskShift]
                )
            default:
                try postShortcutGlobally(virtualKey: 5, flags: [.maskCommand, .maskShift])
            }
            let attemptDeadline = min(pathFieldDeadline, Date().addingTimeInterval(2))
            repeat {
                let roots = [outerSheet] + (currentOpenPanel().map { [$0.window] } ?? [])
                detectedPathField = roots.lazy.compactMap { controlRoot in
                    descendants(controlRoot, role: kAXTextFieldRole).first { field in
                        boolAttribute(field, kAXFocusedAttribute)
                    }
                }.first
                if detectedPathField == nil {
                    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
                }
            } while detectedPathField == nil && Date() < attemptDeadline
        } while detectedPathField == nil && Date() < pathFieldDeadline
        guard let pathField = detectedPathField else {
            throw SelectionError.timeout("前往文件夹路径输入框")
        }
        try setAttribute(pathField, name: kAXFocusedAttribute, value: kCFBooleanTrue, action: "聚焦文件夹路径输入框")
        try click(pathField)
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        let navigationPath = (folderPath as NSString).deletingLastPathComponent
        let pasteboard = NSPasteboard.general
        let pasteboardSnapshot = snapshotPasteboard(pasteboard)
        defer { restorePasteboard(pasteboard, snapshot: pasteboardSnapshot) }
        pasteboard.clearContents()
        pasteboard.setString(navigationPath, forType: .string)
        try postShortcutGlobally(virtualKey: 0, flags: [.maskCommand])
        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        try postShortcutGlobally(virtualKey: 9, flags: [.maskCommand])
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        if stringAttribute(pathField, kAXValueAttribute) != navigationPath {
            let directSetResult = AXUIElementSetAttributeValue(
                pathField,
                kAXValueAttribute as CFString,
                navigationPath as CFString
            )
            guard directSetResult == .success else {
                throw SelectionError.actionFailed("写入文件夹路径", directSetResult)
            }
        }
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

        let navigationRoots = (currentOpenPanel().map { [$0.window] } ?? []) + [outerSheet]
        let navigationButtonDescriptions = navigationRoots.flatMap { controlRoot in
            descendants(controlRoot, role: kAXButtonRole).map { button -> String in
                let title = stringAttribute(button, kAXTitleAttribute)
                let description = stringAttribute(button, kAXDescriptionAttribute)
                let subrole = stringAttribute(button, kAXSubroleAttribute)
                return "\(title.isEmpty ? "<空>" : title){description=\(description.isEmpty ? "<空>" : description),subrole=\(subrole.isEmpty ? "<空>" : subrole),enabled=\(boolAttribute(button, kAXEnabledAttribute))}"
            }
        }
        let folderName = (folderPath as NSString).lastPathComponent
        var observedRows: [String] = []
        func findTargetRow() -> AXUIElement? {
            let roots = (currentOpenPanel().map { [$0.window] } ?? []) + [outerSheet]
            let rows = roots.flatMap { descendants($0, role: kAXRowRole) }
            observedRows = rows.map { row in
                Array(Set(descendantElements(row).flatMap(elementTexts))).sorted().joined(separator: "|")
            }
            return rows.first { row in
                descendantElements(row).flatMap(elementTexts).contains(folderName)
            }
        }
        func waitForTargetRow(seconds: Double) -> AXUIElement? {
            let deadline = Date().addingTimeInterval(seconds)
            repeat {
                if let row = findTargetRow() { return row }
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            } while Date() < deadline
            return nil
        }

        var confirmMethod = "unconfirmed"
        var confirmAttempts: [String] = []
        var targetRow: AXUIElement?
        try postShortcutGlobally(virtualKey: 36)
        confirmAttempts.append("focused-global-return")
        targetRow = waitForTargetRow(seconds: 1.5)
        if targetRow != nil { confirmMethod = "focused-global-return" }
        if targetRow == nil {
            let fieldConfirmResult = AXUIElementPerformAction(pathField, kAXConfirmAction as CFString)
            confirmAttempts.append("text-field-confirm=\(fieldConfirmResult.rawValue)")
            if fieldConfirmResult == .success {
                targetRow = waitForTargetRow(seconds: 1.5)
                if targetRow != nil { confirmMethod = "text-field-confirm" }
            }
        }
        if targetRow == nil {
            let innerConfirmButton = navigationRoots.lazy.compactMap { controlRoot in
                firstButton(controlRoot, titles: ["前往", "Go"])
            }.first
            if let goButton = innerConfirmButton {
                try press(goButton, action: "前往目标目录")
                confirmAttempts.append("go-button")
                targetRow = waitForTargetRow(seconds: 1.5)
                if targetRow != nil { confirmMethod = "go-button" }
            }
        }
        if targetRow == nil, let panelProcessIdentifier = currentOpenPanel()?.processIdentifier {
            try postShortcut(processIdentifier: panelProcessIdentifier, virtualKey: 36)
            confirmAttempts.append("open-panel-return")
            targetRow = waitForTargetRow(seconds: 1.5)
            if targetRow != nil { confirmMethod = "open-panel-return" }
        }
        if targetRow == nil {
            try postShortcut(processIdentifier: application.processIdentifier, virtualKey: 36)
            confirmAttempts.append("application-return")
            targetRow = waitForTargetRow(seconds: 1.5)
            if targetRow != nil { confirmMethod = "application-return" }
        }
        if targetRow == nil {
            try postShortcutGlobally(virtualKey: 36)
            confirmAttempts.append("global-return")
            targetRow = waitForTargetRow(seconds: 2)
            if targetRow != nil { confirmMethod = "global-return" }
        }
        guard let confirmedRow = targetRow else {
            throw SelectionError.missingElement(
                "父目录中的目标文件夹行；确认尝试=\(confirmAttempts.joined(separator: ", "))；导航按钮=\(navigationButtonDescriptions.joined(separator: ", "))；观察到：\(observedRows.joined(separator: ", "))"
            )
        }
        try setAttribute(confirmedRow, name: kAXSelectedAttribute, value: kCFBooleanTrue, action: "选择目标文件夹行")
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        let openButtonTitles: Set<String> = ["打开", "Open", "选择", "Choose", "选取", "Select", "确定", "OK"]
        let buttonDeadline = Date().addingTimeInterval(timeoutSeconds)
        var openButton: AXUIElement?
        var observedButtons: [String] = []
        repeat {
            let selectionRoots = (currentOpenPanel().map { [$0.window] } ?? []) + [outerSheet]
            let buttons = selectionRoots.flatMap { descendants($0, role: kAXButtonRole) }
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
