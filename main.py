import ccxt
import re
from telethon import TelegramClient, events
import json
import os

# Load the configuration file if running locally
# Get the directory of the current script
script_directory = os.path.dirname(os.path.abspath(__file__))

# Construct the full path for the config file
config_file_path = os.path.join(script_directory, 'config.json')

try:
    with open(config_file_path) as config_file:
        config = json.load(config_file)
    # Now 'config' contains the loaded JSON data
    print(config)
except FileNotFoundError:
    print(f"Error: Config file not found at {config_file_path}")
except json.JSONDecodeError as e:
    print(f"Error decoding JSON in config file: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
###################################

# Load the configuration file if running Docker
#config_file_path = '/app/config.json'
#with open(config_file_path) as config_file:
#    config = json.load(config_file)

# Connect to Binance
exchange = ccxt.binanceusdm({
    'apiKey': config["exchange"]["apiKey"],
    'secret': config["exchange"]["secret"],
    'enableRateLimit': config["exchange"]["enableRateLimit"],
    'options': config["exchange"]["options"]
})

# Set sandbox mode
#exchange.set_sandbox_mode(True)

# Connect to Telegram
appid = config["telegram"]["appid"]
apihash = config["telegram"]["apihash"]
apiname = config["telegram"]["apiname"]
channel_ID = config["telegram"]["channel_ID"]

# Trade settings
default_leverage = config["tradeSettings"]["default_leverage"]
override_leverage = config["tradeSettings"]["override_leverage"]
leverage_override = config["tradeSettings"]["leverage_override"]
leverage_on_spot_order = config["tradeSettings"]["leverage_on_spot_order"]
margin_mode = config["tradeSettings"]["margin_mode"]
risk_persentage = config["tradeSettings"]["risk_persentage"]
max_cost_limit = config["tradeSettings"]["max_cost_limit"]
use_fixed_cost = config["tradeSettings"]["use_fixed_cost"]
fixed_cost = config["tradeSettings"]["fixed_cost"]
keep_balance = config["tradeSettings"]["keep_balance"]

##### gets balance Function #####
def get_futures_balance():
    try:
        # Fetch balance for futures account
        balance = exchange.fetch_balance()
        balance = balance['free']
        balance = balance['USDT']

        # Print the entire balance response for inspection
        print(f"Futures Balance Response: {balance}")

        return balance

    except Exception as e:
        print(f"Error fetching futures balance: {e}")
        return None
###################################
    

##### Calculates size Function #####
def calc_trade_size(symbol, leverage):
    # Load the time difference
    exchange.load_time_difference()

    # Fetch the futures balance
    balance = get_futures_balance()

    # Calculate the cost based on the risk percentage
    cost = balance * (risk_persentage / 100)

    # Check if the balance is valid
    if (balance - cost) <= keep_balance:
        print(f"Balance is less than {keep_balance}. Signal NOT executed")
        return False

    # Check if the cost exceeds the maximum cost limit
    if cost > max_cost_limit and max_cost_limit != 0:
        cost = max_cost_limit

    # Check if fixed cost is enabled
    if use_fixed_cost == True:
        cost = fixed_cost

    # Fetch the current price of the symbol
    ticker = exchange.fetch_ticker(symbol)
    current_price = ticker['last']

    # Calculate the trade size based on the cost, current price, and leverage
    size = (cost / current_price) * leverage

    print(f"Size: {round(size, 5)}")
    return round(size, 5)
###################################


##### checks leverage Function #####
def calc_leverage(symbol, leverage, is_spot, margin_mode):
    # Load the time difference
    exchange.load_time_difference()
    
    if is_spot:
        leverage = leverage_on_spot_order
        exchange.set_leverage(leverage, symbol)
        exchange.setMarginMode (margin_mode, symbol)
        print(f"Spot order. Using leverage of {leverage} for symbol {symbol}")
        return leverage

    if override_leverage:
        leverage = leverage_override
        print(f"Leverage override enabled. Using leverage of {leverage} for symbol {symbol}")
        exchange.set_leverage(leverage, symbol)
        return leverage
    else:
        print(f"Leverage override disabled. Using leverage of {leverage} for symbol {symbol}")
        exchange.set_leverage(leverage, symbol)
        return leverage
###################################


##### Clear Telegram Formatting Function #####
def clear_telegram_formatting(message):
    # Remove bold formatting
    message = re.sub(r'\*\*|\_\_', '', message)
    
    # Remove italic formatting
    message = re.sub(r'\*|\_', '', message)
    
    # Remove code formatting
    message = re.sub(r'`', '', message)
    
    # Remove inline links
    message = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\1 (\2)', message)
    
    # Remove newline characters and consecutive spaces
    message = re.sub(r'\n', ' ', message)
    message = re.sub(r' {2,}', ' ', message)
    
    return message
###################################

            
##### Parsing Function #####
def parse_telegram_message(message):
    if message is None or not hasattr(message, 'text') or not isinstance(message.text, str):
        print('Not a valid signal from start')
        return False  # Message is not valid

    # Clear the formatting
    message.text = clear_telegram_formatting(message.text)
    # Define the regular expressions
    symbol_regex = re.compile(r'Trading Pair: (\w+)/(\w+)')
    entry_regex = re.compile(r'Averaging \(DCA\): ([\d.]+)(?:, ([\d.]+))?')
    take_profit_regex = re.compile(r'Targets: ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)')
    position_type_regex = re.compile(r'OPEN — (LONG|SHORT)')
    stop_loss_regex = re.compile(r'(?:Stop loss|SL): ([\d.]+)')
    spot_regex = re.compile(r'\(SPOT\)')

    # Parse the message
    try:
        symbol_match = re.search(symbol_regex, message.text)
        if symbol_match is None:
            raise ValueError("Symbol not found in message")

        entry_match = re.search(entry_regex, message.text)
        if entry_match is None:
            raise ValueError("Entry not found in message")

        take_profit_match = re.search(take_profit_regex, message.text)
        if take_profit_match is None:
            raise ValueError("Take profit not found in message")

        stop_loss_match = re.search(stop_loss_regex, message.text)
        if stop_loss_match is None and not spot_regex.search(message.text):
            raise ValueError("Stop loss not found in message")
        elif spot_regex.search(message.text):
            print("Stop loss not found in message, but it's a spot order. Not setting stop loss")

        position_type_match = re.search(position_type_regex, message.text)
        if position_type_match is None:
            raise ValueError("Position type not found in message")

        spot_match = re.search(spot_regex, message.text)
    except ValueError as e:
        print(str(e))
        print(f"Invalid message: {message.text}" + "\n")
        return False

    # Extract the values
    symbol = symbol_match.group(1) + symbol_match.group(2)

    # Handle multiple values for "Averaging (DCA)"
    entry_values = [float(value) if value is not None else None for value in entry_match.groups()] if entry_match else [None, None]
    entry = tuple(entry_values)

    take_profit_matches = take_profit_match.groups()
    take_profit = [float(group) for group in take_profit_matches if group is not None]

    position_type = position_type_match.group(1) if position_type_match else None

    # Check if "(SPOT)" is present in the message
    spot_present = spot_match is not None

    if spot_present:
        stop_loss = "spot"
    else:
        stop_loss = float(stop_loss_match.group(1)) if stop_loss_match else None

    # Return the values
    return symbol, entry, take_profit, stop_loss, position_type, spot_present

###################################


##### Open Trade Function #####
def open_trade(symbol, leverage, entry, take_profit, stop_loss, position_type,is_spot, size, margin_mode):
    # Load the time difference
    exchange.load_time_difference()

    # Define additional parameters, including leverage
    additional_params = {}
    calc_leverage(symbol, leverage, is_spot, margin_mode)

    # Determine the position side based on the order type
    if position_type == 'LONG':
        additional_params['positionSide'] = 'LONG'
    elif position_type == 'SHORT':
        additional_params['positionSide'] = 'SHORT'
    else:
        print(f"Invalid position_type: {position_type}")
        return None

    # Assuming 'size' is the total size you want to trade
    total_size = size

    # Calculate the size for each order (1 market and 2 limit orders)
    market_order_size = total_size * 0.2  # Adjust the distribution as needed
    limit_order_size = total_size * 0.4  # Adjust the distribution as needed

    # Place market order
    market_order = exchange.create_order(
        symbol=symbol,
        type='market',
        side='buy' if position_type == 'LONG' else 'sell',
        amount=market_order_size,
        params=additional_params,
    )
    position_info = market_order
    print("Market Order information:")
    print(str(position_info) + "\n")

    # Place Limit orders
    i = 1
    for entries in entry:
            if entries is not None:    
                limit_order = exchange.create_order(
                    symbol=symbol,
                    type='limit',
                    side='buy' if position_type == 'LONG' else 'sell',
                    amount=limit_order_size,
                    price=entries,
                    params=additional_params,
                )
                position_info = limit_order
                print("Limit Order: " + str(i) + " information:")
                print(str(position_info) + "\n")
                i += 1

    # Add stopPrice to additional_params
    additional_params['stopPrice'] = stop_loss

    # Place stop loss order
    if stop_loss != "spot":
        stop_loss_order = exchange.create_order(
            symbol=symbol,
            type='STOP_MARKET',
            side='sell' if position_type == 'LONG' else 'buy',
            amount=size,
            price=stop_loss,  
            params=additional_params,
        )

        position_info = stop_loss_order
        print("Stop Loss information:")
        print(str(position_info) + "\n")
    else:
        print("Stop Loss not set for spot order" + "\n")

    size = size/5  # Split the size into 5 take profit orders
    i = 1
    for tp in take_profit:
        # Add stopPrice to additional_params
        additional_params['stopPrice'] = tp
        # Place take profit order
        take_profit_order = exchange.create_order(
            symbol=symbol,
            type='TAKE_PROFIT_MARKET',
            side='sell' if position_type == 'LONG' else 'buy',
            amount=size,
            price=tp,  # This is the take profit price
            params=additional_params,
        )

        position_info = take_profit_order
        print('Take Profit: ' + str(i) + ' information:')
        print(str(position_info) + "\n")
        i += 1
###################################


##### Main function Function #####
def auto_andrew_signals():
    client = TelegramClient(apiname, appid, apihash)
    client.start()

    @client.on(events.NewMessage(chats=channel_ID))#, reply_to=topic_ID
    async def handler(event):
        msg = event.message
        orderDetails = parse_telegram_message(msg)
        print(orderDetails)
        if orderDetails != False:
            symbol = orderDetails[0]
            leverage = default_leverage
            entry = orderDetails[1]
            take_profit = orderDetails[2]
            stop_loss = orderDetails[3]
            position_type = orderDetails[4]
            is_spot = orderDetails[5]
            size = calc_trade_size(symbol, default_leverage)
            if size is not False:
                open_trade(symbol, leverage, entry, take_profit, stop_loss, position_type, is_spot, size, margin_mode)
            else:
                print(f'Not a valid signal for symbol {symbol}, no action taken')
        else:
            print('Not a valid signal, no action taken')
        
    client.run_until_disconnected()
###################################

def __main__(): 
    auto_andrew_signals()

__main__()
