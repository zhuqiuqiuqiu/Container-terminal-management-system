import requests

res = requests.get("http://127.0.0.1:5000/containers/4", json={
    "container_no": "A1001",

})

print("status:", res.status_code)
print("text:", res.text)