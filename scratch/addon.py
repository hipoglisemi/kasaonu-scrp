from mitmproxy import http

def request(flow: http.HTTPFlow) -> None:
    if "api" in flow.request.pretty_url:
        print(f"\n[{flow.request.method}] {flow.request.pretty_url}")
        if "guest-token" in flow.request.headers:
            print(f"GUEST-TOKEN FOUND: {flow.request.headers['guest-token']}")
        if "authorization" in flow.request.headers:
            print(f"AUTH-TOKEN FOUND: {flow.request.headers['authorization']}")

def response(flow: http.HTTPFlow) -> None:
    if "guest" in flow.request.pretty_url and flow.response.content:
        print(f"\nResponse from {flow.request.pretty_url}:")
        print(flow.response.content[:500])
