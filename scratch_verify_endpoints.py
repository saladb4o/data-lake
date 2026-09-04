import urllib.request, json, time

endpoints = [
    'http://127.0.0.1:8000/api/quote/history?symbol=FPT&interval=1D&timeframe=ALL',
    'http://127.0.0.1:8000/api/company/overview?symbol=FPT',
    'http://127.0.0.1:8000/api/trading-board?group=VN30',
    'http://127.0.0.1:8000/api/indices-analytics'
]

for ep in endpoints:
    t0 = time.perf_counter()
    try:
        req = urllib.request.urlopen(ep, timeout=10)
        data = json.loads(req.read().decode('utf-8'))
        t1 = time.perf_counter()
        name = ep.split('/')[-1].split('?')[0]
        status = data.get('status')
        print(f"[{name}]: status={status} in {(t1-t0)*1000:.1f} ms")
    except Exception as e:
        print(f"[{ep}]: FAILED ({e})")
