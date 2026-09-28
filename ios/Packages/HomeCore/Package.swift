// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HomeCore",
    platforms: [.iOS("26.0"), .macOS("15.0")],
    products: [.library(name: "HomeCore", targets: ["HomeCore"])],
    targets: [
        .target(name: "HomeCore"),
        .testTarget(name: "HomeCoreTests", dependencies: ["HomeCore"]),
    ]
)
