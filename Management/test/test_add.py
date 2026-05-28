import requests

res = requests.post("http://127.0.0.1:5000/containers", json={
    "container_no": "A1001",
    "container_type": "20GP"
})

print("status:", res.status_code)
print("text:", res.text)