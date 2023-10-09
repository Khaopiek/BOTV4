import websocket
import ssl
import json
import pandas as pd
from datetime import datetime
from binance import Client

api_key = ''
api_secret = ''
client = Client(api_key, api_secret)


symbol = 'btcfdusd'
socket = f'wss://stream.binance.com:9443/ws/{symbol}@trade'

df = pd.DataFrame(columns=['timestamp', 'price'])

MA1_WINDOW = 5
MA2_WINDOW = 20
MA3_WINDOW = 50

last_printed_second = None
ready_to_trade = False
last_signal = None

def on_message(ws, message):
    global df, last_printed_second, ready_to_trade, last_signal

    data = json.loads(message)
    timestamp = datetime.fromtimestamp(data['T'] / 1000)
    price = float(data['p'])

    new_row = pd.DataFrame({'timestamp': [timestamp], 'price': [price]})
    df = pd.concat([df, new_row], ignore_index=True)

    ohlc = df.set_index('timestamp').resample('1S').agg({
        'price': ['first', 'max', 'min', 'last']
    })
    ohlc.columns = ['open', 'high', 'low', 'close']
    ohlc.fillna(method='ffill', inplace=True)
    ohlc.dropna(inplace=True)

    ohlc['MA1'] = ohlc['close'].rolling(window=MA1_WINDOW).mean()
    ohlc['MA2'] = ohlc['close'].rolling(window=MA2_WINDOW).mean()
    ohlc['MA3'] = ohlc['close'].rolling(window=MA3_WINDOW).mean()

    current_second = ohlc.index[-1].second
    if last_printed_second != current_second:
        latest_candle = ohlc.iloc[-1]
        print(f"Time: {ohlc.index[-1]}, Open: {latest_candle['open']}, High: {latest_candle['high']}, Low: {latest_candle['low']}, Close: {latest_candle['close']}, MA1: {latest_candle['MA1']}, MA2: {latest_candle['MA2']}, MA3: {latest_candle['MA3']}")

        signal = generate_signal(latest_candle['MA1'], latest_candle['MA2'], latest_candle['MA3'])
        print(f"Signal: {signal}")

        if signal != last_signal and signal in ["Buy", "Sell"]:
            place_order(client, signal)
            last_signal = signal

        last_printed_second = current_second

        if not ready_to_trade and signal != "Insufficient Data":
            ready_to_trade = True



def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("### closed ###")

def on_open(ws):
    print("Opened connection")

def get_margin_balance(client, asset="USDT"):
    account_info = client.get_margin_account()
    for balance in account_info['userAssets']:
        if balance['asset'] == asset:
            return float(balance['free'])
    return 0.0

def generate_signal(MA1, MA2, MA3):
    if pd.isna(MA1) or pd.isna(MA2) or pd.isna(MA3):
        return "Insufficient Data"

    A = 1 if MA1 > MA2 else 0
    B = 1 if MA2 > MA3 else 0
    C = 1 if MA1 > MA3 else 0

    AA = A + B + C

    if AA == 3:
        return "Buy"
    elif C == 0:
        return "Sell"
    else:
        return "No Signal"

def get_asset_precision(client, symbol="BTCFDUSD"):
    exchange_info = client.get_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            return s['baseAssetPrecision'], s['quoteAssetPrecision']
    return None, None

def place_order(client, signal, symbol="BTCFDUSD", percentage=1.0):
    global ready_to_trade

    if not ready_to_trade:
        print("Not ready to trade yet.")
        return

    # Fetch the latest price for the trading pair
    last_price = float(client.get_ticker(symbol=symbol)['lastPrice'])

    # Fetch the asset precision and the relevant filters from the exchange info
    exchange_info = client.get_exchange_info()
    lot_size_filter = {}
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            lot_size_filter = next(filter(lambda x: x['filterType'] == "LOT_SIZE", s['filters']), {})
            btc_precision = s['baseAssetPrecision']
            fdusd_precision = s['quoteAssetPrecision']

    # Determine precision based on the signal
    precision = fdusd_precision if signal == "Buy" else btc_precision

    asset_to_check = "FDUSD" if signal == "Buy" else "BTC"
    available_balance = get_margin_balance(client, asset=asset_to_check)
    
    if signal == "Buy":
        quantity = (available_balance / last_price) * percentage
    else:
        quantity = available_balance * percentage

    # Adjust the quantity according to the LOT_SIZE filter
    step_size = float(lot_size_filter.get('stepSize', 1))
    quantity = round(quantity - (quantity % step_size), precision)

    # Validate the quantity against the min and max allowed
    min_qty, max_qty = float(lot_size_filter.get('minQty', 0)), float(lot_size_filter.get('maxQty', float('inf')))
    quantity = min(max(quantity, min_qty), max_qty)

    order_type = Client.SIDE_BUY if signal == "Buy" else Client.SIDE_SELL

    # Before placing the order, print the order details for debugging purposes
    print(f"Attempting to {signal} with quantity: {quantity}")
    print(f"LOT_SIZE Filter: MinQty: {min_qty}, MaxQty: {max_qty}, StepSize: {step_size}")

    try:
        order_response = client.create_margin_order(
            symbol=symbol,
            side=order_type,
            type=Client.ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f"Order Response: {order_response}")
    except Exception as e:
        print(f"Error placing order: {str(e)}")


ws = websocket.WebSocketApp(socket,
                            on_open=on_open,
                            on_message=on_message,
                            on_error=on_error,
                            on_close=on_close)

ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
