import requests

res = requests.delete("http://127.0.0.1:5000/containers/1")

print("status:", res.status_code)
print("text:", res.text)