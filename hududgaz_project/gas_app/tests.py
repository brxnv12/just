import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib.parse import urlencode

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from . import ai
from .models import Account, Appeal, Transaction

TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id=42, name="Ali", age=0):
    user = json.dumps({"id": user_id, "first_name": name, "username": "ali"}, separators=(",", ":"))
    data = {"auth_date": str(int(time.time()) - age), "user": user, "query_id": "AAA"}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


@override_settings(BOT_TOKEN=TOKEN, DEV_AUTH=False, DEMO_PAYMENTS=True, GAS_TARIFF=Decimal("1000"))
class ApiTests(TestCase):
    def H(self, **kw):
        return {"HTTP_X_TELEGRAM_INIT_DATA": make_init_data(**kw)}

    def test_auth_required_and_invalid(self):
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/me/", HTTP_X_TELEGRAM_INIT_DATA="hash=bad&user={}").status_code, 401)
        self.assertEqual(self.client.get("/api/me/", **self.H(age=10 * 86400)).status_code, 401)
        self.assertEqual(self.client.get("/api/me/", **self.H()).status_code, 200)

    def test_full_flow(self):
        H = self.H()
        r = self.client.post("/api/accounts/", json.dumps({"number": "12 345 678", "label": "Uy", "address": "Chilonzor", "lat": 41.3, "lng": 69.2}),
                             content_type="application/json", **H)
        self.assertEqual(r.status_code, 201, r.content)
        acc_id = r.json()["id"]
        dup = self.client.post("/api/accounts/", json.dumps({"number": "12345678"}), content_type="application/json", **H)
        self.assertEqual(dup.status_code, 400)

        def reading(v):
            return self.client.post("/api/readings/", {"account": acc_id, "value": v}, **H)

        self.assertEqual(reading("100").status_code, 201)       # boshlang'ich
        self.assertEqual(reading("130.5").status_code, 201)     # 30.5 * 1000
        self.assertEqual(reading("120").status_code, 400)       # kamayishi mumkin emas
        acc = Account.objects.get(pk=acc_id)
        self.assertEqual(acc.balance, Decimal("-30500.00"))

        t = self.client.post("/api/topup/", json.dumps({"account": acc_id, "amount": 100000, "provider": "payme"}),
                             content_type="application/json", **H)
        self.assertEqual(t.status_code, 201)
        self.assertEqual(Account.objects.get(pk=acc_id).balance, Decimal("69500.00"))

        d = self.client.get(f"/api/accounts/{acc_id}/dashboard/", **H).json()
        self.assertEqual(d["monthly"][-1]["volume"], 30.5)
        self.assertEqual(len(d["transactions"]), 2)

        img = SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg")
        a = self.client.post("/api/appeals/", {"category": "Boshqa", "text": "Muammo bor, iltimos ko'ring"}, **H)
        self.assertEqual(a.status_code, 201, a.content)
        self.assertEqual(len(self.client.get("/api/appeals/", **H).json()), 1)

        c = self.client.post("/api/chat/", json.dumps({"message": "balans qancha?", "account": acc_id}),
                             content_type="application/json", **H).json()
        self.assertIn("69", c["reply"])

    def test_isolation_between_users(self):
        H1, H2 = self.H(user_id=1), self.H(user_id=2)
        r = self.client.post("/api/accounts/", json.dumps({"number": "11111"}), content_type="application/json", **H1)
        acc_id = r.json()["id"]
        self.assertEqual(self.client.get(f"/api/accounts/{acc_id}/dashboard/", **H2).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/accounts/{acc_id}/", **H2).status_code, 404)
        self.assertEqual(self.client.post("/api/readings/", {"account": acc_id, "value": "5"}, **H2).status_code, 404)

    def test_phone(self):
        H = self.H()
        ok = self.client.patch("/api/me/", json.dumps({"phone": "90 123 45 67"}), content_type="application/json", **H)
        self.assertEqual(ok.json()["phone"], "+998901234567")
        bad = self.client.patch("/api/me/", json.dumps({"phone": "123"}), content_type="application/json", **H)
        self.assertEqual(bad.status_code, 400)

    @override_settings(DEMO_PAYMENTS=False)
    def test_topup_disabled(self):
        H = self.H()
        acc_id = self.client.post("/api/accounts/", json.dumps({"number": "22222"}), content_type="application/json", **H).json()["id"]
        r = self.client.post("/api/topup/", json.dumps({"account": acc_id, "amount": 5000}), content_type="application/json", **H)
        self.assertEqual(r.status_code, 403)


@override_settings(OPENAI_API_KEY="")
class AiTests(TestCase):
    def test_emergency_first(self):
        text, op = ai.answer("uyda gaz hidi kelyapti")
        self.assertIn("104", text)

    def test_fallback_operator(self):
        _, op = ai.answer("qanday ob-havo bugun")
        self.assertTrue(op)

    def test_index_page(self):
        self.assertEqual(self.client.get("/").status_code, 200)


import base64 as _b64
import io as _io

from PIL import Image as _Image


def _png(name="a.png"):
    buf = _io.BytesIO()
    _Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(BOT_TOKEN=TOKEN, DEV_AUTH=False, DEMO_PAYMENTS=True, GAS_TARIFF=Decimal("1000"))
class SecurityTests(TestCase):
    def H(self):
        return {"HTTP_X_TELEGRAM_INIT_DATA": make_init_data()}

    def _acc(self):
        r = self.client.post("/api/accounts/", json.dumps({"number": "99999"}), content_type="application/json", **self.H())
        return r.json()["id"]

    def test_fake_image_rejected(self):
        acc = self._acc()
        bad = SimpleUploadedFile("x.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        r = self.client.post("/api/readings/", {"account": acc, "value": "5", "photo": bad}, **self.H())
        self.assertEqual(r.status_code, 400)

    def test_signed_media(self):
        acc = self._acc()
        r = self.client.post("/api/readings/", {"account": acc, "value": "5", "photo": _png()}, **self.H())
        self.assertEqual(r.status_code, 201, r.content)
        url = r.json()["photo"]
        self.assertIn("?t=", url)
        self.assertTrue(url.split("?")[0].endswith(".png"))  # nom tasodifiy va kengaytma xavfsiz
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url.split("?")[0]).status_code, 404)        # tokensiz yopiq
        self.assertEqual(self.client.get(url.split("?")[0] + "?t=bad").status_code, 404)

    @override_settings(CHAT_PER_MINUTE=2, OPENAI_API_KEY="")
    def test_chat_rate_limit(self):
        codes = [self.client.post("/api/chat/", json.dumps({"message": "salom"}), content_type="application/json", **self.H()).status_code
                 for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


@override_settings(BOT_TOKEN=TOKEN, DEV_AUTH=False, PAYME_MERCHANT_ID="MERCH1", PAYME_KEY="secret", PAYME_TEST=True)
class PaymeTests(TestCase):
    AUTH = {"HTTP_AUTHORIZATION": "Basic " + _b64.b64encode(b"Paycom:secret").decode()}

    def rpc(self, method, params, auth=True):
        return self.client.post("/api/payme/", json.dumps({"id": 1, "method": method, "params": params}),
                                content_type="application/json", **(self.AUTH if auth else {})).json()

    def setUp(self):
        H = {"HTTP_X_TELEGRAM_INIT_DATA": make_init_data()}
        self.acc = self.client.post("/api/accounts/", json.dumps({"number": "77777"}), content_type="application/json", **H).json()["id"]
        self.H = H

    def test_checkout_link(self):
        r = self.client.post("/api/topup/", json.dumps({"account": self.acc, "amount": 50000, "provider": "payme"}),
                             content_type="application/json", **self.H).json()
        url = r["checkout_url"]
        self.assertTrue(url.startswith("https://test.paycom.uz/"))
        raw = _b64.b64decode(url.rsplit("/", 1)[1]).decode()
        self.assertIn(f"m=MERCH1;ac.account={self.acc};a=5000000", raw)
        self.assertEqual(Transaction.objects.count(), 0)  # to'lovdan oldin balans o'zgarmaydi

    def test_auth(self):
        self.assertEqual(self.rpc("CheckTransaction", {"id": "x"}, auth=False)["error"]["code"], -32504)

    def test_full_cycle(self):
        acct = {"account": str(self.acc)}
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": 10000, "account": acct})["error"]["code"], -31001)
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": 500000, "account": {"account": "999"}})["error"]["code"], -31050)
        self.assertTrue(self.rpc("CheckPerformTransaction", {"amount": 500000, "account": acct})["result"]["allow"])

        c = self.rpc("CreateTransaction", {"id": "pm1", "time": 1700000000000, "amount": 500000, "account": acct})["result"]
        self.assertEqual(c["state"], 1)
        again = self.rpc("CreateTransaction", {"id": "pm1", "time": 1700000000000, "amount": 500000, "account": acct})["result"]
        self.assertEqual(again["transaction"], c["transaction"])

        p = self.rpc("PerformTransaction", {"id": "pm1"})["result"]
        self.assertEqual(p["state"], 2)
        self.rpc("PerformTransaction", {"id": "pm1"})  # takroriy chaqiruv balansni ikkilantirmasligi kerak
        self.assertEqual(Account.objects.get(pk=self.acc).balance, Decimal("5000"))

        st = self.rpc("GetStatement", {"from": 1699999999999, "to": 1700000000001})["result"]["transactions"]
        self.assertEqual(len(st), 1)

        x = self.rpc("CancelTransaction", {"id": "pm1", "reason": 5})["result"]
        self.assertEqual(x["state"], -2)
        self.assertEqual(Account.objects.get(pk=self.acc).balance, Decimal("0"))
        self.assertEqual(self.rpc("CheckTransaction", {"id": "nope"})["error"]["code"], -31003)


class ProdGuardTests(TestCase):
    def test_dev_auth_blocked_in_production(self):
        import subprocess, sys, os
        env = {**os.environ, "DEBUG": "0", "DEV_AUTH": "1", "SECRET_KEY": "x" * 40, "DJANGO_SETTINGS_MODULE": "core.settings"}
        r = subprocess.run([sys.executable, "-c", "import django;django.setup()"], env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DEV_AUTH", r.stderr)
