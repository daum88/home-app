import XCTest
@testable import HomeCore

final class DownloadCompletionTests: XCTestCase {
    private enum Failure: Error { case disk, network }

    func testFileFinishesBeforeTaskCompletion() throws {
        var completion = DownloadCompletion()
        XCTAssertNil(completion.fileFinished(.success(())))
        XCTAssertNotNil(try completion.networkFinished(error: nil)?.get())
    }

    func testTaskCompletesBeforeFileResultIsDelivered() throws {
        var completion = DownloadCompletion()
        XCTAssertNil(completion.networkFinished(error: nil))
        XCTAssertNotNil(try completion.fileFinished(.success(()))?.get())
    }

    func testFileMoveFailureIsNotReportedAsSuccess() {
        var completion = DownloadCompletion()
        XCTAssertNil(completion.networkFinished(error: nil))
        XCTAssertThrowsError(try completion.fileFinished(.failure(Failure.disk))?.get())
    }

    func testNetworkErrorWinsEvenWhenFileWasMoved() {
        var completion = DownloadCompletion()
        XCTAssertNil(completion.fileFinished(.success(())))
        XCTAssertThrowsError(try completion.networkFinished(error: Failure.network)?.get())
    }
}
