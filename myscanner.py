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

headers = {
    'accept': "application/json",
    'Authorization': "Bearer " + myscanner_tokens.TOKENS['ACCESS_TOKEN'],
}

stock_params = {
    'symbols': None,
    'fields': "quote",
}

options_params = {
    'symbol': None,
    'contractType': "CALL",
    'strike': None,
}

ticker = None
rescan_rate = 180
strikes = [0.5, 1.0, 1.5, 2.0]


def compare_prices(stock_bid, stock_ask, opt_quotes):
    for expiration, opt_data in opt_quotes['callExpDateMap'].items():
        for strike, strike_data in opt_data.items():
            opt_bid = strike_data[0]['bid']
            opt_ask = strike_data[0]['ask']
            opt_mid = round((opt_bid + opt_ask) / 2. * 1000.) / 1000.
            opt_price = opt_mid + options_params['strike']
            if opt_price < stock_bid:
                diff = round(stock_bid*100.-round(opt_price*100.))
                if diff > 2.99:
                    print(f"+++++BTO: {expiration} {strike} C @"
                          f"{round(opt_mid*100.)/100.} and sell {ticker} @"
                          f"{stock_bid} - difference: $ {diff}, then exercise")
            elif opt_price > stock_ask:
                diff = round(math.trunc(opt_price*100.)-stock_ask*100.)
                if diff > 2.99:
                    parts = expiration.split(":")
                    if int(parts[1]) < 21:
                        print(f"-----STO: {expiration} {strike} C @"
                              f"{math.trunc(opt_mid*100.)/100.} and buy "
                              f"{ticker} @{stock_ask} - difference: $ {diff}")


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
        response = requests.post(API_TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        j = response.json()
        with open("myscanner_tokens.py", "w") as f:
            f.write("TOKENS = {\n")
            f.write(f"""    'ACCESS_TOKEN': "{j['access_token']}",\n""")
            f.write(f"""    'REFRESH_TOKEN': "{j['refresh_token']}",\n""")
            f.write("}\n")

        print("Access tokens successfully refreshed.")
        if 'exit' in kwargs and kwargs['exit']:
            sys.exit(0)


    except Exception as err:
        print(f"Token refresh error: '{err}'")
        sys.exit(1)


del sys.argv[0]
while len(sys.argv) > 0:
    if sys.argv[0] == "--rescan-rate":
        del sys.argv[0]
        rescan_rate = int(sys.argv[0])
        del sys.argv[0]
    elif sys.argv[0] == "--auth-code":
        del sys.argv[0]
        create_token(sys.argv[0])
    elif sys.argv[0] == "--refresh-token":
        refresh_token(exit=True)
    elif sys.argv[0] == "--ticker":
        del sys.argv[0]
        ticker = sys.argv[0]
        del sys.argv[0]
    else:
        print(f"Unrecognized option '{sys.argv[0]}'")
        sys.exit(1)

if ticker is None:
    print("Error - no ticker specified.")
    sys.exit(1)

stock_params['symbols'] = ticker
options_params['symbol'] = ticker
while True:
    token_refreshed = False
    try:
        print(f"\nScanning at {datetime.now()}...")
        # stock quote
        response = requests.get(os.path.join(API_URL_BASE, "quotes"),
                                headers=headers, params=stock_params)
        response.raise_for_status()
        j = response.json()
        stock_bid = j[ticker]['quote']['bidPrice']
        stock_ask = j[ticker]['quote']['askPrice']
        for strike in strikes:
            options_params['strike'] = strike
            response = requests.get(os.path.join(API_URL_BASE, "chains"),
                                    headers=headers,
                                    params=options_params)
            response.raise_for_status()
            j = response.json()
            compare_prices(stock_bid, stock_ask, j)

    except Exception as err:
        print(f"Error: '{err}'")
        if str(err).find("401 Client Error") == 0:
            print(f"Re-authenticate at {API_AUTH_URL}?response_type=code"
                  f"&client_id={myscanner_secrets.SECRETS['CLIENT_ID']}"
                  "&redirect_uri=https://127.0.0.1 and then replace TOKEN")
            refresh_token()
            token_refreshed = True
        else:
            sys.exit(1)

    if not token_refreshed:
        time.sleep(rescan_rate)
