bind = "0.0.0.0:10000"
workers = 2
timeout = 300        # 5 min — allows large PDF uploads to complete
worker_class = "sync"
max_requests = 1000
max_requests_jitter = 100
