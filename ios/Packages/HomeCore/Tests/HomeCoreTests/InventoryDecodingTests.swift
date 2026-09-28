import XCTest
import HomeCore

final class InventoryDecodingTests: XCTestCase {
    func testLocalPackagesKeepDistinctIdsAndCloudMetadata() throws {
        let json = Data("""
        {"items":[
          {"id":1,"name":"Milk","barcode":"12345678","quantity":1,"unit":"pz","position":"fridge","expires_on":"2026-10-10"},
          {"id":2,"name":"Milk","barcode":"12345678","quantity":238,"unit":"g","position":"freezer","expires_on":null}
        ]}
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let result = try decoder.decode(FridgeInventory.self, from: json)
        XCTAssertEqual(result.items.map(\.id), [1, 2])
        XCTAssertEqual(result.items[1].unit, "g")
        XCTAssertEqual(result.items[1].position, "freezer")
        XCTAssertNil(result.items[1].expiresOn)
    }
}
