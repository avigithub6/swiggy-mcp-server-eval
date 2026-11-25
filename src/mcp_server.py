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


# 1. Food Search (Vector RAG)
@mcp.tool()
def search_food_dishes(query: str, max_price: int = 500, veg_only: bool = False) -> str:
    """Search for dishes on Swiggy."""
    results = semantic_search_food(query, max_price=max_price, veg_only=veg_only)
    if not results:
        return f"No dishes found matching '{query}' under ₹{max_price}."
    formatted = [f"- {r['name']} ({r['restaurant']}) - ₹{r['price']}" for r in results]
    return "Matching Swiggy Food dishes:\n" + "\n".join(formatted)


# 2. Instamart Search (Vector RAG)
@mcp.tool()
def search_instamart_items(query: str, max_price: int = 500) -> str:
    """Search for items on Swiggy Instamart."""
    results = semantic_search_instamart(query, max_price=max_price)
    if not results:
        return f"No Instamart items found matching '{query}' under ₹{max_price}."
    formatted = [f"- {r['name']} [{r['category']}] - ₹{r['price']}" for r in results]
    return "Matching Instamart items:\n" + "\n".join(formatted)


# 3. Live Order Tracking (SQLite Read)
@mcp.tool()
def track_live_order(order_id: str) -> str:
    """Track an order."""
    _validate_order_id(order_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return f"Order {order_id} not found."
    return f"Order {order_id} ({row['vertical']}): Status is '{row['status']}', ETA: {row['eta_mins']} mins."


# 4. Order Invoice & Items Details (SQLite Read)
@mcp.tool()
def get_order_details(order_id: str) -> str:
    """Get details of an order."""
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


# 5. Cancel Active Order (SQLite Write + Guardrail)
@mcp.tool()
def cancel_active_order(order_id: str, confirm: bool = False) -> str:
    """Cancel an order."""
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


# 6. Request Refund for Delivered/Damaged Order (SQLite Write)
@mcp.tool()
def request_order_refund(order_id: str, reason: str) -> str:
    """Request a refund for an order."""
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


# 7. Apply Promo Coupon (SQLite Read)
@mcp.tool()
def apply_promo_coupon(coupon_code: str, cart_total: float) -> str:
    """Apply a coupon code."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM coupons WHERE code = ?", (coupon_code.upper(),)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Invalid coupon code '{coupon_code}'.")
    if cart_total < row["min_order"]:
        raise ValueError(f"Cart total ₹{cart_total} is below minimum order ₹{row['min_order']} for {coupon_code}.")
    
    discount = round(cart_total * (row["discount_percent"] / 100), 2)
    return f"Coupon '{row['code']}' applied! You saved ₹{discount}. Final payable: ₹{cart_total - discount}."


# 8. Contact Delivery Partner (SQLite Read)
@mcp.tool()
def contact_delivery_partner(order_id: str, message: str) -> str:
    """Contact the delivery partner."""
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
