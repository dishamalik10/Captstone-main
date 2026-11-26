from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from main import app
from services.vision_service import vision_service


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), (200, 120, 150)).save(buffer, format="JPEG")
    return buffer.getvalue()


def account(client, name, email):
    response = client.post("/auth/signup", json={"full_name": name, "email": email, "password": "secure-pass-123"})
    assert response.status_code == 201, response.text
    return response.json()["user"]["id"], {"Authorization": f"Bearer {response.json()['token']}"}


def listing(client, auth, **extra):
    data = {"title": "Pink mini dress", "price": "1200", "category": "dresses", "condition": "like_new",
            "description": "Worn once", "size": "M", "brand": "Zara", **extra}
    files = [("files", ("a.jpg", jpeg(), "image/jpeg")), ("files", ("b.jpg", jpeg(), "image/jpeg"))]
    return client.post("/marketplace/listings", headers=auth, data=data, files=files)


def test_sell_chat_buy_ship_complete():
    with TestClient(app) as client:
        seller_id, seller = account(client, "Sana Seller", "mk-seller@example.com")
        buyer_id, buyer = account(client, "Bina Buyer", "mk-buyer@example.com")

        created = listing(client, seller)
        assert created.status_code == 201, created.text
        product = created.json()
        assert product["status"] == "active" and product["size"] == "M" and len(product["imageUrls"]) == 2
        assert client.get(product["imageUrls"][0]).status_code == 200  # public photo URL

        # Browse + search
        assert [p["id"] for p in client.get("/marketplace/products", params={"q": "zara"}).json()] == [product["id"]]
        assert client.get("/marketplace/products", params={"category": "shoes"}).json() == []

        # Buyer asks a question; seller sees it unread and replies.
        conversation = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        assert conversation["role"] == "buyer" and conversation["otherUser"]["name"] == "Sana Seller"
        again = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        assert again["id"] == conversation["id"]  # one thread per buyer per item
        sent = client.post(f"/marketplace/conversations/{conversation['id']}/messages", headers=buyer,
                           json={"body": "Is it still available? Can you do 1000?"})
        assert sent.status_code == 201
        inbox = client.get("/marketplace/conversations", headers=seller).json()
        assert inbox["unread"] == 1 and inbox["conversations"][0]["role"] == "seller"
        thread = client.get(f"/marketplace/conversations/{conversation['id']}", headers=seller).json()
        assert [m["body"] for m in thread["messages"]] == ["Is it still available? Can you do 1000?"]
        assert thread["messages"][0]["mine"] is False
        assert client.get("/marketplace/conversations", headers=seller).json()["unread"] == 0  # read now
        client.post(f"/marketplace/conversations/{conversation['id']}/messages", headers=seller, json={"body": "Yes, 1100 is fine"})

        # Seller lowers the price; outsiders cannot edit or read the chat.
        assert client.patch(f"/marketplace/listings/{product['id']}", headers=seller, json={"price": 1100}).json()["price"] == 1100
        assert client.patch(f"/marketplace/listings/{product['id']}", headers=buyer, json={"price": 1}).status_code == 404
        _, stranger = account(client, "Stranger", "mk-stranger@example.com")
        assert client.get(f"/marketplace/conversations/{conversation['id']}", headers=stranger).status_code == 404

        # Seller cannot buy their own item; buyer can.
        assert client.post("/marketplace/orders", headers=seller, json={"product_ids": [product["id"]]}).status_code == 409
        order = client.post("/marketplace/orders", headers=buyer, json={
            "product_ids": [product["id"]], "payment_method": "upi",
            "shipping_address": {"name": "Bina", "phone": "9999999999", "line1": "12 MG Road", "city": "Delhi", "pincode": "110001"},
        })
        assert order.status_code == 201, order.text
        order_id = order.json()["order_ids"][0]
        assert client.get(f"/marketplace/products/{product['id']}").json()["status"] == "sold"
        assert client.get("/marketplace/products").json() == []  # off the shop floor
        assert client.post("/marketplace/orders", headers=stranger, json={"product_ids": [product["id"]]}).status_code == 409

        dashboard = client.get("/marketplace/seller", headers=seller).json()
        assert dashboard["stats"]["pendingOrders"] == 1 and dashboard["stats"]["revenue"] == 0
        incoming = dashboard["orders"][0]
        assert incoming["buyer"]["name"] == "Bina Buyer" and incoming["shippingAddress"]["city"] == "Delhi"
        assert incoming["paymentMethod"] == "upi"

        # Buyer cannot mark it shipped; seller ships; buyer confirms receipt.
        assert client.post(f"/marketplace/orders/{order_id}/status", headers=buyer, json={"status": "shipped"}).status_code == 409
        assert client.post(f"/marketplace/orders/{order_id}/status", headers=seller, json={"status": "shipped"}).json()["status"] == "shipped"
        assert client.post(f"/marketplace/orders/{order_id}/status", headers=buyer, json={"status": "cancelled"}).status_code == 409
        done = client.post(f"/marketplace/orders/{order_id}/status", headers=buyer, json={"status": "completed"})
        assert done.json()["status"] == "completed"
        assert client.get("/marketplace/orders/mine", headers=buyer).json()[0]["status"] == "completed"
        stats = client.get("/marketplace/seller", headers=seller).json()["stats"]
        assert stats["totalSales"] == 1 and stats["revenue"] == 1100

        # The seller can open the thread with their buyer from the order.
        seller_thread = client.post("/marketplace/conversations", headers=seller,
                                    json={"product_id": product["id"], "buyer_id": buyer_id}).json()
        assert seller_thread["id"] == conversation["id"] and seller_thread["role"] == "seller"
        stranger_id = client.get("/auth/me", headers=stranger).json()["id"]
        assert client.post("/marketplace/conversations", headers=seller,
                           json={"product_id": product["id"], "buyer_id": stranger_id}).status_code == 409

        # Listings with orders cannot be deleted.
        assert client.delete(f"/marketplace/listings/{product['id']}", headers=seller).status_code == 409


def test_cancelled_order_relists_and_wardrobe_listing(monkeypatch):
    monkeypatch.setattr(vision_service, "predict", lambda _: {
        "product_type": {"label": "Jacket", "confidence": 0.9, "top_3": []},
        "garment_group": {"label": "Outdoor", "confidence": 0.9, "top_3": []},
        "color_group": {"label": "Black", "confidence": 0.9, "top_3": []},
        "category": "Outerwear",
    })
    import main as main_module
    monkeypatch.setattr(main_module, "cutout_garment", lambda image: None)
    with TestClient(app) as client:
        seller_id, seller = account(client, "Wardrobe Seller", "mk-ws@example.com")
        _, buyer = account(client, "Second Buyer", "mk-b2@example.com")
        item = client.post("/wardrobe/upload", headers=seller, data={"user_id": seller_id},
                           files={"file": ("j.jpg", jpeg(), "image/jpeg")}).json()

        created = client.post("/marketplace/listings", headers=seller, data={
            "title": "Black jacket", "price": "900", "category": "outerwear", "condition": "good",
            "wardrobe_item_id": item["item_id"]})
        assert created.status_code == 201, created.text
        product = created.json()
        assert product["wardrobeItemId"] == item["item_id"] and len(product["imageUrls"]) == 1

        # Paused listings disappear from the shop.
        client.patch(f"/marketplace/listings/{product['id']}", headers=seller, json={"status": "paused"})
        assert client.get("/marketplace/products").json() == []
        client.patch(f"/marketplace/listings/{product['id']}", headers=seller, json={"status": "active"})

        order_id = client.post("/marketplace/orders", headers=buyer, json={"product_ids": [product["id"]]}).json()["order_ids"][0]
        client.post(f"/marketplace/orders/{order_id}/status", headers=buyer, json={"status": "cancelled"})
        assert client.get(f"/marketplace/products/{product['id']}").json()["status"] == "active"  # back on sale

        order_id = client.post("/marketplace/orders", headers=buyer, json={"product_ids": [product["id"]]}).json()["order_ids"][0]
        client.post(f"/marketplace/orders/{order_id}/status", headers=seller, json={"status": "shipped"})
        wardrobe = client.get(f"/wardrobe/{seller_id}", headers=seller).json()
        assert next(i for i in wardrobe if i["item_id"] == item["item_id"])["available"] is False


def test_listing_validation_and_delete():
    with TestClient(app) as client:
        _, seller = account(client, "Val Seller", "mk-val@example.com")
        no_photo = client.post("/marketplace/listings", headers=seller, data={
            "title": "X", "price": "10", "category": "tops", "condition": "good"})
        assert no_photo.status_code == 422 and "photo" in no_photo.json()["detail"]
        bad_category = listing(client, seller, category="spaceships")
        assert bad_category.status_code == 422
        product = listing(client, seller).json()
        assert client.delete(f"/marketplace/listings/{product['id']}", headers=seller).status_code == 204
        assert client.get(f"/marketplace/products/{product['id']}").status_code == 404
        assert client.get(product["imageUrls"][0]).status_code == 404  # photos cleaned up
        assert client.get("/marketplace/images/..%2Faura.db").status_code == 404
