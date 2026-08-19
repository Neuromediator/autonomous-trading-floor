import os
from dotenv import load_dotenv
import requests
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"

# Off by default: the tool still works for the agent (the summary lands in the
# activity log) but nothing is sent to a phone unless explicitly enabled.
push_enabled = os.getenv("PUSH_NOTIFICATIONS", "false").strip().lower() == "true"


mcp = FastMCP("push_server")


class PushModelArgs(BaseModel):
    message: str = Field(description="A brief message to push")


@mcp.tool()
def push(args: PushModelArgs):
    """Send a push notification with this brief message"""
    print(f"Push: {args.message}")
    if not (push_enabled and pushover_user and pushover_token):
        return "Push notification recorded (sending is disabled)"
    payload = {"user": pushover_user, "token": pushover_token, "message": args.message}
    requests.post(pushover_url, data=payload)
    return "Push notification sent"


if __name__ == "__main__":
    mcp.run(transport="stdio")
