from mitmproxy import http

def request(flow: http.HTTPFlow) -> None:
    if "oliz" in flow.request.pretty_url or "api" in flow.request.pretty_url:
        with open("scratch/oliz_tokens.txt", "a") as f:
            f.write(f"[{flow.request.method}] {flow.request.pretty_url}\n")
            if "authorization" in flow.request.headers:
                f.write(f"AUTH: {flow.request.headers['authorization']}\n")
            if "guest-token" in flow.request.headers:
                f.write(f"GUEST: {flow.request.headers['guest-token']}\n")
