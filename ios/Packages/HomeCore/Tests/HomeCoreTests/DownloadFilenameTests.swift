import XCTest
@testable import HomeCore

final class DownloadFilenameTests: XCTestCase {
    func testTranscodedDownloadUsesServerMp4Name() {
        XCTAssertEqual(DownloadFilename.resolved(source: "Movie.mkv", suggested: "Movie.mp4"), "Movie.mp4")
    }

    func testRawDownloadKeepsSourceNameWithoutContentDisposition() {
        XCTAssertEqual(DownloadFilename.resolved(source: "Movie.mkv", suggested: nil), "Movie.mkv")
    }

    func testServerNameCannotEscapeDownloadsDirectory() {
        XCTAssertEqual(DownloadFilename.resolved(source: "Movie.mkv", suggested: "../../Movie.mp4"), "Movie.mp4")
        XCTAssertEqual(DownloadFilename.resolved(source: "Movie.mkv", suggested: ".."), "Movie.mkv")
    }
}
