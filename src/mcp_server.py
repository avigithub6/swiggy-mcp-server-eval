from mcp.server.mcpserver import MCPServer

# Initialize the MCP Server
mcp = MCPServer("Swiggy-MCP-Server")

# Simple in-memory data just for Step 1 testing
ORDERS = {
    "SWG-101": {"item": "Paneer Tikka Masala", "status": "Out for delivery", "eta": "10 mins"},
    "SWG-102": {"item": "Veg Biryani", "status": "Preparing", "eta": "25 mins"},
}

@mcp.tool()
def search_food_dishes(query: str, max_price: int = 500) -> str:
    """Search for cooked restaurant dishes on Swiggy Food."""
    return f"Found 2 dishes matching '{query}' under ₹{max_price}: Paneer Tikka (₹260) and Dal Makhani (₹220)."

@mcp.tool()
def track_live_order(order_id: str) -> str:
    """Check the live delivery status and ETA of an active Swiggy order."""
    if not order_id.startswith("SWG-"):
        raise ValueError("Invalid Order ID. Must start with 'SWG-'.")
    
    order = ORDERS.get(order_id)
    if not order:
        return f"Order {order_id} not found."
    
    return f"Order {order_id} ({order['item']}) is {order['status']}. ETA: {order['eta']}."

if __name__ == "__main__":
    mcp.run()