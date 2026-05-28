import requests

res = requests.put("http://127.0.0.1:5000/containers/3/next_status")

print(res.text)
print(res.status_code)
