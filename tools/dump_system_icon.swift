// Ask macOS what icon it actually resolves for an app, and write it out.
//
// This is what Finder and the Dock draw, cache and all, as opposed to the
// .icns sitting in the bundle. When the two disagree, the cache is stale,
// and that distinction is the difference between a real icon bug and an
// afternoon spent rebuilding a file that was already correct.
//
//   swiftc -O tools/dump_system_icon.swift -o /tmp/dumpicon
//   /tmp/dumpicon /Applications/TubeClipper.app /tmp/out.png 1024

import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: dumpicon <app> <out.png> [size]\n".data(using: .utf8)!)
    exit(2)
}
let appPath = args[1]
let outPath = args[2]
let size = args.count > 3 ? Int(args[3]) ?? 1024 : 1024

let icon = NSWorkspace.shared.icon(forFile: appPath)
let target = NSSize(width: size, height: size)

let rep = NSBitmapImageRep(bitmapDataPlanes: nil,
                           pixelsWide: size, pixelsHigh: size,
                           bitsPerSample: 8, samplesPerPixel: 4,
                           hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB,
                           bytesPerRow: 0, bitsPerPixel: 0)!
rep.size = target

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.clear.set()
NSRect(origin: .zero, size: target).fill()
icon.draw(in: NSRect(origin: .zero, size: target),
          from: .zero, operation: .sourceOver, fraction: 1.0)
NSGraphicsContext.restoreGraphicsState()

guard let data = rep.representation(using: .png, properties: [:]) else {
    FileHandle.standardError.write("could not encode PNG\n".data(using: .utf8)!)
    exit(1)
}
try data.write(to: URL(fileURLWithPath: outPath))
print("wrote \(outPath) (\(size)px)")
