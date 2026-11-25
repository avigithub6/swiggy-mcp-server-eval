import re
from mcp.server.mcpserver import MCPServer
from database import get_connection, init_db
from vector_store import init_vector_store, semantic_search_food, semantic_search_instamart

# Ensure DB and Vector Store are ready when server boots
init_db()
init_vector_store()

mcp = MCPServer("Swiggy-MCP-Server")


def _validate_order_id(order_id: str):
    if not re.match(r"^SWG-\d{3}$", order_id):
        raise ValueError(f"Invalid order_id '{order_id}'. Expected format: SWG-XXX (e.g., SWG-101).")

# 1. Food Search (Vector RAG) - v2
@mcp.tool()
def search_food_dishes(query: str, max_price: int = 500, veg_only: bool = False) -> str:
    """
    Search for ready-to-eat, cooked restaurant dishes on Swiggy Food.
    - WHEN TO USE: Cooked meals, snacks, beverages, or dietary meal recommendations.
    - WHEN NOT TO USE: Do NOT use for raw groceries, uncooked ingredients, or medicines (use search_instamart_items).
    - EFFICIENCY RULE: Combine multiple requested dishes into ONE single search query; do NOT call this tool multiple times per turn.
    """
    results = semantic_search_food(query, max_price=max_price, veg_only=veg_only)
    if not results:
        return f"No dishes found matching '{query}' under ₹{max_price}."
    formatted = [f"- {r['name']} ({r['restaurant']}) - ₹{r['price']}" for r in results]
    return "Matching Swiggy Food dishes:\n" + "\n".join(formatted)


# 2. Instamart Search (Vector RAG) - v2
@mcp.tool()
def search_instamart_items(query: str, max_price: int = 500) -> str:
    """
    Search for raw groceries, dairy, vegetables, cooking ingredients, and pharmacy essentials on Swiggy Instamart.
    - WHEN TO USE: Uncooked food supplies, raw ingredients to cook/brew at home (e.g., tea leaves, raw paneer, pasta), milk, bread, or OTC medicines.
    - WHEN NOT TO USE: Do NOT use for cooked restaurant meals (use search_food_dishes).
    - EFFICIENCY RULE: Combine multiple grocery items into ONE single combined query; do NOT make separate tool calls for each item.
    """
    results = semantic_search_instamart(query, max_price=max_price)
    if not results:
        return f"No Instamart items found matching '{query}' under ₹{max_price}."
    formatted = [f"- {r['name']} [{r['category']}] - ₹{r['price']}" for r in results]
    return "Matching Instamart items:\n" + "\n".join(formatted)


# 3. Live Order Tracking (SQLite Read) - v2
@mcp.tool()
def track_live_order(order_id: str) -> str:
    """
    Check real-time delivery tracking and rider ETA for an active, in-transit Swiggy order.
    - WHEN TO USE: Checking live progress or ETA of orders currently Preparing, Out for delivery, or Delayed.
    - WHEN NOT TO USE: Do NOT use to inspect ordered items, check bills, or verify past/delivered orders (use get_order_details).
    """
    _validate_order_id(order_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return f"Order {order_id} not found."
    return f"Order {order_id} ({row['vertical']}): Status is '{row['status']}', ETA: {row['eta_mins']} mins."


# 4. Order Invoice & Items Details (SQLite Read) - v2
@mcp.tool()
def get_order_details(order_id: str) -> str:
    """
    Retrieve full order summary, ordered items, total bill amount, and delivery status for any active or past order.
    - WHEN TO USE: Verifying if an order is Delivered, checking items inside an order, or viewing receipts/totals.
    """
    _validate_order_id(order_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return f"Order {order_id} not found."
    return (
        f"Order {order_id} | Vertical: {row['vertical']} | Items: {row['items']} | "
        f"Total: ₹{row['total_amount']} | Status: {row['status']}"
    )


# 5. Cancel Active Order (SQLite Write + Guardrail) - v2
@mcp.tool()
def cancel_active_order(order_id: str, confirm: bool = False) -> str:
    """
    Cancel an active order that has NOT yet been delivered.
    - WHEN TO USE: Stopping an order currently in 'Preparing', 'Out for delivery', or 'Delayed' state.
    - WHEN NOT TO USE: Do NOT use for orders already marked 'Delivered' (use request_order_refund instead).
    - SAFETY GUARDRAIL: Requires confirm=True.
    """
    _validate_order_id(order_id)
    if not confirm:
        raise ValueError("Safety Guardrail: You must set confirm=True to cancel an order.")
    
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        return f"Order {order_id} not found."
    if row["status"] in ("Delivered", "Cancelled", "Refunded"):
        conn.close()
        raise ValueError(f"Cannot cancel order {order_id} because its status is already '{row['status']}'.")
    
    conn.execute("UPDATE orders SET status = 'Cancelled', eta_mins = 0 WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    return f"Order {order_id} has been successfully cancelled."


# 6. Request Refund for Delivered/Damaged Order (SQLite Write) - v2
@mcp.tool()
def request_order_refund(order_id: str, reason: str) -> str:
    """
    Initiate a monetary refund for an order that has already been Delivered (e.g., stale, spilled, or rotten items).
    - WHEN TO USE: Post-delivery complaints where the user wants their money back.
    - WHEN NOT TO USE: Do NOT use to stop an active in-transit order (use cancel_active_order).
    """
    _validate_order_id(order_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        return f"Order {order_id} not found."
    if row["status"] != "Delivered":
        conn.close()
        raise ValueError(f"Refunds are only eligible for 'Delivered' orders. Current status: '{row['status']}'.")
    
    conn.execute("UPDATE orders SET status = 'Refunded' WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    return f"Refund of ₹{row['total_amount']} initiated for Order {order_id}. Reason: {reason}."


# 7. Apply Promo Coupon (SQLite Read) - v2
@mcp.tool()
def apply_promo_coupon(coupon_code: str, cart_total: float) -> str:
    """
    Validate and calculate discount for a promotional coupon code against a given cart total in INR.
    """
    conn = get_connection()
    row = conn.execute("SELECT * FROM coupons WHERE code = ?", (coupon_code.upper(),)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Invalid coupon code '{coupon_code}'.")
    if cart_total < row["min_order"]:
        raise ValueError(f"Cart total ₹{cart_total} is below minimum order ₹{row['min_order']} for {coupon_code}.")
    
    discount = round(cart_total * (row["discount_percent"] / 100), 2)
    return f"Coupon '{row['code']}' applied! You saved ₹{discount}. Final payable: ₹{cart_total - discount}."


# 8. Contact Delivery Partner (SQLite Read) - v2
@mcp.tool()
def contact_delivery_partner(order_id: str, message: str) -> str:
    """
    Send delivery instructions or a direct message to the assigned delivery rider for an active order.
    """
    _validate_order_id(order_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return f"Order {order_id} not found."
    if row["status"] not in ("Preparing", "Out for delivery", "Delayed"):
        raise ValueError(f"Cannot contact rider because order {order_id} is '{row['status']}'.")
    
    return f"Message sent to rider {row['rider_name']} ({row['rider_phone']}) for {order_id}: '{message}'"

if __name__ == "__main__":
    mcp.run()
