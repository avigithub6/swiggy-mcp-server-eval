from pathlib import Path
import chromadb

CHROMA_PATH = str(Path(__file__).parent.parent / "chroma_db")

# Initialize persistent local ChromaDB client
client = chromadb.PersistentClient(path=CHROMA_PATH)

def init_vector_store():
    """Populate ChromaDB collections for Swiggy Food (cooked meals) and Instamart (raw groceries)."""
    food_col = client.get_or_create_collection(name="swiggy_food")
    insta_col = client.get_or_create_collection(name="swiggy_instamart")

    # Seed Swiggy Food Dishes (Cooked Restaurant Meals)
    if food_col.count() == 0:
        food_items = [
            ("f1", "Paneer Tikka Masala - Rich, spicy cottage cheese curry in smoky tomato gravy. Veg, North Indian.", {"name": "Paneer Tikka Masala", "restaurant": "Haldiram's", "price": 280, "is_veg": True}),
            ("f2", "Hyderabadi Chicken Biryani - Aromatic spicy basmati rice cooked with marinated chicken and saffron. Non-Veg.", {"name": "Hyderabadi Chicken Biryani", "restaurant": "Behrouz Biryani", "price": 360, "is_veg": False}),
            ("f3", "Moong Dal Khichdi - Light, comforting lentil and rice porridge, gentle on an upset stomach. Veg, Healthy.", {"name": "Moong Dal Khichdi", "restaurant": "EatFit", "price": 170, "is_veg": True}),
            ("f4", "Curd Rice - Cooling yogurt rice tempered with mustard seeds and curry leaves, light meal. Veg, South Indian.", {"name": "Curd Rice", "restaurant": "Sagar Ratna", "price": 150, "is_veg": True}),
            ("f5", "Spicy Veg Schezwan Noodles - Fiery Indo-Chinese stir-fried noodles tossed with crunchy vegetables. Veg.", {"name": "Spicy Veg Schezwan Noodles", "restaurant": "Wok Express", "price": 220, "is_veg": True}),
            ("f6", "Masala Dosa - Crispy fermented rice crepe stuffed with spiced potato filling, served with sambar. Veg.", {"name": "Masala Dosa", "restaurant": "Vaango", "price": 160, "is_veg": True}),
            ("f7", "Butter Chicken - Creamy, mildly spiced tomato-butter chicken curry. Non-Veg, North Indian.", {"name": "Butter Chicken", "restaurant": "Punjabi Angithi", "price": 340, "is_veg": False}),
            ("f8", "Grilled Chicken Salad - High-protein healthy salad with olive oil dressing, low calorie. Non-Veg.", {"name": "Grilled Chicken Salad", "restaurant": "Salad Days", "price": 290, "is_veg": False}),
        ]
        food_col.add(
            ids=[x[0] for x in food_items],
            documents=[x[1] for x in food_items],
            metadatas=[x[2] for x in food_items],
        )

    # Seed Swiggy Instamart Items (Raw Groceries & Daily Essentials)
    if insta_col.count() == 0:
        insta_items = [
            ("i1", "Fresh Malai Paneer Block 200g - Uncooked raw cottage cheese block for home cooking. Dairy.", {"name": "Amul Fresh Paneer (200g)", "category": "Dairy", "price": 95}),
            ("i2", "Assam Tea Leaves, Ginger & Cardamom Combo - Raw ingredients to brew homemade masala chai. Beverages.", {"name": "Masala Chai Essentials Pack", "category": "Groceries", "price": 140}),
            ("i3", "Fresh Farm Tomatoes 1kg & Coriander Bunch - Raw cooking vegetables for curry or salad.", {"name": "Tomatoes 1kg + Coriander", "category": "Vegetables", "price": 65}),
            ("i4", "Amul Taaza Toned Milk 1L & Brown Bread - Daily breakfast staples.", {"name": "Milk 1L + Brown Bread", "category": "Dairy & Bakery", "price": 110}),
            ("i5", "Durum Wheat Penne Pasta 500g & Arrabbiata Sauce Jar - Raw ingredients to cook Italian pasta at home.", {"name": "Pasta & Sauce Cooking Kit", "category": "Packaged Food", "price": 240}),
            ("i6", "Paracetamol 650mg Tablets & ORS Electrolyte Powder - Fever and hydration pharmacy essentials.", {"name": "Fever & Hydration Care Pack", "category": "Pharmacy", "price": 90}),
        ]
        insta_col.add(
            ids=[x[0] for x in insta_items],
            documents=[x[1] for x in insta_items],
            metadatas=[x[2] for x in insta_items],
        )

    return food_col, insta_col

def semantic_search_food(query: str, max_price: int = 500, veg_only: bool = False) -> list[dict]:
    food_col, _ = init_vector_store()
    where_filter = {"$and": [{"price": {"$lte": max_price}}, {"is_veg": True}]} if veg_only else {"price": {"$lte": max_price}}
    
    results = food_col.query(query_texts=[query], n_results=3, where=where_filter)
    return results["metadatas"][0] if results["metadatas"] else []

def semantic_search_instamart(query: str, max_price: int = 500) -> list[dict]:
    _, insta_col = init_vector_store()
    results = insta_col.query(query_texts=[query], n_results=3, where={"price": {"$lte": max_price}})
    return results["metadatas"][0] if results["metadatas"] else []

if __name__ == "__main__":
    init_vector_store()
    print("✅ Vector Store initialized!")
    print("Test Food Query ('light food for upset stomach'):", semantic_search_food("light food for upset stomach"))
    print("Test Instamart Query ('ingredients to make tea'):", semantic_search_instamart("ingredients to make tea"))
