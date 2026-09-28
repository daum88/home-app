import Foundation

public struct FridgeItem: Decodable, Identifiable, Hashable {
    public var id: Int
    public var name: String
    public var barcode: String?
    public var brands: String?
    public var category: String?
    public var quantity: Double?
    public var unit: String?
    public var expiresOn: String?
    public var position: String?

    public init(id: Int, name: String, barcode: String? = nil, brands: String? = nil,
                category: String? = nil, quantity: Double? = nil, unit: String? = nil,
                expiresOn: String? = nil, position: String? = nil) {
        self.id = id
        self.name = name
        self.barcode = barcode
        self.brands = brands
        self.category = category
        self.quantity = quantity
        self.unit = unit
        self.expiresOn = expiresOn
        self.position = position
    }
}

public struct FridgeInventory: Decodable {
    public var items: [FridgeItem]

    public init(items: [FridgeItem]) {
        self.items = items
    }
}
