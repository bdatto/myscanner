import base64
import math
import myscanner_secrets
import myscanner_tokens
import os
import requests
import sys
import time

from datetime import datetime


API_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"

API_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

API_URL_BASE = "https://api.schwabapi.com/marketdata/v1"

SCAN_HEADERS = {
    'accept': "application/json",
    'Authorization': "Bearer " + myscanner_tokens.TOKENS['ACCESS_TOKEN'],
}

STOCK_PARAMS = {
    'symbols': None,
    'fields': "quote",
}

OPTIONS_PARAMS = {
    'symbol': None,
    'contractType': "CALL",
    'strike': None,
}

TICKER = None
RESCAN_RATE = None
STRIKES = [0.5, 1.0, 1.5, 2.0]


def compare_prices(stock_bid, stock_ask, opt_quotes):
    for expiration, opt_data in opt_quotes['callExpDateMap'].items():
        for strike, strike_data in opt_data.items():
            opt_bid = strike_data[0]['bid']
            opt_ask = strike_data[0]['ask']
            opt_mid = round((opt_bid + opt_ask) / 2. * 1000.) / 1000.
            opt_price = opt_mid + OPTIONS_PARAMS['strike']
            if opt_price < stock_bid:
                buy_price = round(round((opt_mid+0.001)*100.)/100.-0.001, 2)
                diff = (stock_bid - (buy_price + float(strike))) * 100.
                if diff > 2.99:
                    print(f">>> BTO: {expiration} {strike} C @{buy_price} "
                          f"and sell {TICKER} @{stock_bid} - difference: $ "
                          f"{round(diff)}, then exercise")
            elif opt_price > stock_ask:
                diff = round(math.trunc(opt_price*100.)-stock_ask*100.)
                if diff > 2.99:
                    parts = expiration.split(":")
                    if int(parts[1]) <= 14:
                        print(f"<<< STO: {expiration} {strike} C @"
                              f"{math.trunc(opt_mid*100.)/100.} and buy "
                              f"{TICKER} @{stock_ask} - difference: $ {diff}")

            if WITH_SPREADS and (opt_mid - opt_bid) > 0.2:
                print(f"            *** Wide spread: {expiration} {strike} "
                      f"{opt_bid} {opt_mid} {opt_ask}")


def create_token(code):
    auth = (f"{myscanner_secrets.SECRETS['CLIENT_ID']}:"
            f"{myscanner_secrets.SECRETS['CLIENT_SECRET']}")
    b64_auth = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
    headers = {
        'Authorization': f"Basic {b64_auth}",
        'Content-Type': "application/x-www-form-urlencoded",
    }
    data = {
        'grant_type': "authorization_code",
        'code': code,
        'redirect_uri': "https://127.0.0.1",
    }
    try:
        response = requests.post(API_TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        j = response.json()
        with open("myscanner_tokens.py", "w") as f:
            f.write("TOKENS = {\n")
            f.write(f"""    'ACCESS_TOKEN': "{j['access_token']}",\n""")
            f.write(f"""    'REFRESH_TOKEN': "{j['refresh_token']}",\n""")
            f.write("}\n")

        print("Tokens successfully saved.")
        sys.exit(0)
    except Exception as err:
        print(f"Token creation error: '{err}'")
        sys.exit(1)


def refresh_token(**kwargs):
    auth = (f"{myscanner_secrets.SECRETS['CLIENT_ID']}:"
            f"{myscanner_secrets.SECRETS['CLIENT_SECRET']}")
    b64_auth = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
    headers = {
        'Authorization': f"Basic {b64_auth}",
        'Content-Type': "application/x-www-form-urlencoded",
    }
    data = {
        'grant_type': "refresh_token",
        'refresh_token': myscanner_tokens.TOKENS['REFRESH_TOKEN'],
    }
    try:
        print(f"OLD header auth {SCAN_HEADERS['Authorization']} "
              f"{myscanner_tokens.TOKENS['ACCESS_TOKEN']}")
        response = requests.post(API_TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        j = response.json()
        with open("myscanner_tokens.py", "w") as f:
            f.write("TOKENS = {\n")
            f.write(f"""    'ACCESS_TOKEN': "{j['access_token']}",\n""")
            f.write(f"""    'REFRESH_TOKEN': "{j['refresh_token']}",\n""")
            f.write("}\n")

        SCAN_HEADERS['Authorization'] = "Bearer " + j['access_token']
        print(f"NEW header auth {SCAN_HEADERS['Authorization']} "
              f"{j['access_token']}")
        print("Access tokens successfully refreshed.")
        if 'exit' in kwargs and kwargs['exit']:
            sys.exit(0)

    except Exception as err:
        print(f"Token refresh error: '{err}'")
        sys.exit(1)


WITH_SPREADS = False

del sys.argv[0]
while len(sys.argv) > 0:
    if sys.argv[0] == "--rescan-rate":
        del sys.argv[0]
        RESCAN_RATE = int(sys.argv[0])
        del sys.argv[0]
    elif sys.argv[0] == "--auth-code":
        del sys.argv[0]
        create_token(sys.argv[0])
    elif sys.argv[0] == "--refresh-token":
        refresh_token(exit=True)
    elif sys.argv[0] == "--ticker":
        del sys.argv[0]
        TICKER = sys.argv[0]
        del sys.argv[0]
    elif sys.argv[0] == "--with-spreads":
        WITH_SPREADS = True
    else:
        print(f"Unrecognized option '{sys.argv[0]}'")
        sys.exit(1)

if TICKER is None:
    print("Error - no ticker specified.")
    sys.exit(1)

STOCK_PARAMS['symbols'] = TICKER
OPTIONS_PARAMS['symbol'] = TICKER
nfail = 0
while True:
    token_refreshed = False
    try:
        print(f"\nScanning at {datetime.now()}...")
        # stock quote
        response = requests.get(os.path.join(API_URL_BASE, "quotes"),
                                headers=SCAN_HEADERS, params=STOCK_PARAMS)
        response.raise_for_status()
        j = response.json()
        stock_bid = j[TICKER]['quote']['bidPrice']
        stock_ask = j[TICKER]['quote']['askPrice']
        for strike in STRIKES:
            OPTIONS_PARAMS['strike'] = strike
            response = requests.get(os.path.join(API_URL_BASE, "chains"),
                                    headers=SCAN_HEADERS,
                                    params=OPTIONS_PARAMS)
            response.raise_for_status()
            j = response.json()
            compare_prices(stock_bid, stock_ask, j)

        print("...done.")
        nfail = 0
    except Exception as err:
        nfail += 1
        print(f"Error: '{err}'")
        if nfail > 2:
            sys.exit(1)

        if str(err).find("401 Client Error") == 0:
            print(f"Re-authenticate at {API_AUTH_URL}?response_type=code"
                  f"&client_id={myscanner_secrets.SECRETS['CLIENT_ID']}"
                  "&redirect_uri=https://127.0.0.1 and then replace TOKEN")
            refresh_token()
            token_refreshed = True
        else:
            sys.exit(1)

    if RESCAN_RATE is None:
        sys.exit(0)

    if not token_refreshed:
        time.sleep(RESCAN_RATE)
