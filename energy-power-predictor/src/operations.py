"""Bounded workers, request throttling and optional service bearer auth."""
from collections import defaultdict,deque
import hmac
import os
from http.server import HTTPServer
from socketserver import ThreadingMixIn
import threading
import time


class LimitedServer(ThreadingMixIn,HTTPServer):
    daemon_threads=True
    allow_reuse_address=True

    def __init__(self,*args,max_workers=8,**kwargs):
        self.slots=threading.BoundedSemaphore(max_workers)
        super().__init__(*args,**kwargs)

    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):
            try:request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:self.shutdown_request(request)
            return
        try:super().process_request(request,client_address)
        except BaseException:
            self.slots.release();raise

    def process_request_thread(self,*args):
        try:super().process_request_thread(*args)
        finally:self.slots.release()


class RateLimiter:
    def __init__(self,limit=240,period=60,max_clients=4096):
        self.limit=limit;self.period=period;self.max_clients=max_clients
        self.clients=defaultdict(deque);self.lock=threading.Lock()

    def allow(self,client):
        now=time.monotonic()
        with self.lock:
            if client not in self.clients and len(self.clients)>=self.max_clients:
                expired=[key for key,q in self.clients.items() if not q or now-q[-1]>=self.period]
                for key in expired:self.clients.pop(key,None)
                if len(self.clients)>=self.max_clients:return False
            queue=self.clients[client]
            while queue and now-queue[0]>=self.period:queue.popleft()
            if len(queue)>=self.limit:return False
            queue.append(now);return True


def authorized(headers):
    expected=os.environ.get('PREDICTION_API_TOKEN')
    if not expected:return True
    return hmac.compare_digest(headers.get('Authorization',''),'Bearer '+expected)
