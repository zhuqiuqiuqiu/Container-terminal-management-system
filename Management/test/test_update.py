import requests

res = requests.put("http://127.0.0.1:5000/containers/3", json={
    'is_full':1
})

print(res.text)
print(res.status_code)
