import requests

headers = {
    "User-Agent": "Oliz/5.12.1 (Android; Android 14; Mobile)",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTA4ZGQtZTIzYWI5ZTIwZTFjIiwianRpIjoiNWQyZTliNjQtNGZjOS00MWNlLWJkZTAtNDEwNjI1MjU1ZWJhIiwiaHR0cDovL3NjaGVtYXMueG1sc29hcC5vcmcvd3MvMjAwNS8wNS9pZGVudGl0eS9jbGFpbXMvZW1haWxhZGRyZXNzIjoiNTU0MTgxODQwNEBhcmNlbGlrcGx1cy5jb20iLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9tb2JpbGVwaG9uZSI6IjU1NDE4MTg0MDQiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9naXZlbm5hbWUiOiJPxJ91eiIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL3N1cm5hbWUiOiJLQVJBRVZMxLAiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9hdXRoZW50aWNhdGlvbiI6IjIwMjUtMDgtMjNUMTE6NDY6NTYuMDM0MjYyNSIsImh0dHA6Ly9zY2hlbWFzLm1pY3Jvc29mdC5jb20vd3MvMjAwOC8wNi9pZGVudGl0eS9jbGFpbXMvcm9sZSI6Ik1lbWJlciBSb2xlIiwiZXhwIjoxNzg0NTg4NjIwLCJpc3MiOiJodHRwOi8vYXV0aGVudGljYXRpb24iLCJhdWQiOiJodHRwOi8vYXV0aGVudGljYXRpb24ifQ.TdS8Jw_6QF-0F7MK792K0R_6BYKEJfSAos79RbsjlIg"
}

endpoints = [
    "/api/member/get-promotions",
    "/api/promotion/get-all-promotions",
    "/api/promotions/get-all",
    "/api/member/get-all-promotions",
    "/api/promotions",
    "/api/promotion/all"
]

for ep in endpoints:
    url = f"https://prodapi.oliz.com.tr{ep}"
    print(f"\n--- GET {ep} ---")
    r_get = requests.get(url, headers=headers, verify=False)
    print(r_get.status_code, r_get.text[:100])
    
    print(f"--- POST {ep} ---")
    r_post = requests.post(url, headers=headers, json={}, verify=False)
    print(r_post.status_code, r_post.text[:100])
