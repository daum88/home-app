import XCTest
import HomeCore

final class ResumeDecisionTests: XCTestCase {
    func testResumeWorksWhenBackendRespondsAfterPlayerBecomesReady() {
        var decision = ResumeDecision()
        XCTAssertNil(decision.receiveDuration(120))
        XCTAssertEqual(decision.receivePosition(42), 42)
        XCTAssertNil(decision.receiveDuration(120))
        XCTAssertTrue(decision.didSeek)
    }

    func testResumeWorksWhenBackendRespondsFirst() {
        var decision = ResumeDecision()
        XCTAssertNil(decision.receivePosition(42))
        XCTAssertNil(decision.receiveDuration(.nan))
        XCTAssertEqual(decision.receiveDuration(120), 42)
        XCTAssertNil(decision.receivePosition(50))
    }

    func testNearEndOrInvalidPositionsDoNotSeek() {
        for position in [0.0, 5.0, 115.0, .nan, .infinity] {
            var decision = ResumeDecision()
            XCTAssertNil(decision.receivePosition(position))
            XCTAssertNil(decision.receiveDuration(120))
            XCTAssertFalse(decision.didSeek)
        }
    }
}
