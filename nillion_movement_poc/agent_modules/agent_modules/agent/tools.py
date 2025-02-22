# Standard library imports
from functools import wraps
import os
import asyncio
# Third-party imports
from dotenv import load_dotenv
from typing import Annotated, Any, Callable
from langgraph.prebuilt import InjectedStore, InjectedState
from langgraph.store.base import BaseStore
from langchain_core.tools import tool
import chainlit as cl

# Local application imports
from agent_modules.database.const.common import unit_to_factor
from agent_modules.database.const.chain_config import ChainConfig, NetworkConfig
from agent_modules.database.const.tax import ordinary_income_brackets, long_term_gains_brackets, california_tax_brackets, standard_deduction_map, california_standard_deduction_map
from agent_modules.websearch.perser_service import PerserSearchService

def get_user_data_by_key(store: Annotated[BaseStore, InjectedStore()], key: str):
    value = store.get(("users", "1"), "user_data").value[key]
    if (not value):
        raise Exception(f"Cannot get the value of {key} from the key-value store.")
    return value

def get_network_config(store: Annotated[BaseStore, InjectedStore()]) -> NetworkConfig:
    network_env = get_user_data_by_key(store, "network_env")
    return ChainConfig.get_network_config(network_env.lower())

def retry_decorator(max_retries: int = 3, delay: float = 1.0):
    """
    A decorator that adds retry functionality to async functions.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        delay (float): Delay between retries in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))  # Exponential backoff
                        print(f"Retrying {func.__name__} due to {last_exception}")
                    continue
            return {
                "error": True,
                "trace": str(last_exception)
            }
        return wrapper
    return decorator

@retry_decorator()
async def estimate_total_gas_cost_transfer(store, decimal_amount, token_type, receiver_address):
    service = get_user_data_by_key(store, "blockchain_service")

    return await service.estimate_transfer_gas(receiver_address, token_type, decimal_amount)

@retry_decorator()
async def estimate_total_gas_cost_swap(store: Annotated[BaseStore, InjectedStore()], decimal_amount: float, src_token_type: str, des_token_type: str):
    service = get_user_data_by_key(store, "blockchain_service")
    print(service)
    print(f"Estimating total gas cost swap: {decimal_amount}, {src_token_type}, {des_token_type}")
    return await service.estimate_swap_gas(decimal_amount, src_token_type, des_token_type)

# @tool
@retry_decorator()
async def transfer_token(store: Annotated[BaseStore, InjectedStore()], token_type: str, receiver_address: str, decimal_amount: float):
    """
    Execute a token transfer transaction with precise decimal handling.

    Args:
        token_type (str): The type of the token to transfer which can be {available_tokens_formatted}
        receiver_address (str): The public key of the receiver's wallet.
        decimal_amount (float): The exact amount to transfer in decimal format. 
            - Ensure decimal precision is maintained as provided.
            - Examples: 20.01, 0.01, 0.222, 0.0001, 0.001231.
            - Do not round or alter the provided decimal value.
    """
    
    await cl.Message(
        content=f"Executing transfer of {decimal_amount} {token_type} to {receiver_address}",
        author="Tool"
    ).send()
    
    service = get_user_data_by_key(store, "blockchain_service")
    result = await service.transfer_token(receiver_address, token_type, decimal_amount)
    
    await cl.Message(
        content=f"Transfer result: {result}",
        author="Tool"
    ).send()
    
    return result

# @tool
@retry_decorator()
async def get_wallet_balance_tool(store: Annotated[BaseStore, InjectedStore()]):
    """
        Get the balance information of the given wallet address
    """
    service = get_user_data_by_key(store, "blockchain_service")
    config = get_network_config(store)

    current_token_info = get_user_data_by_key(store, "available_tokens")
    wallet_public_key = get_user_data_by_key(store, key=f"{config.config_keys[1]}_public_key")

    wallet_token_info = await service.retrieve_available_tokens(wallet_public_key)

    for key in wallet_token_info.keys():
        current_token_info[key] = wallet_token_info[key]

    return wallet_token_info

# @tool
@retry_decorator()
async def estimate_total_gas_cost_transfer_tool(decimal_amount: float, token_type: str, receiver_address: str, store: Annotated[BaseStore, InjectedStore()]):
    """
        Estimate total gas cost for the transaction with a decimal_amount of tokens

        Agrs:
            decimal_amount (float): the decimal number format. Example: 20.01, 0.01, 0.222, 0.0001, 0.001231
    """
    return await estimate_total_gas_cost_transfer(store, decimal_amount, token_type, receiver_address)

# @tool
@retry_decorator()
async def verify_balance_transfer(decimal_amount: float, token_type: str, receiver_address: str, store: Annotated[BaseStore, InjectedStore()]):
    """
        Verify the balance of the user's wallet to check if the user is able to do the action or not with a decimal amount of tokens.

        Agrs:
            decimal_amount (float): the decimal number format. Example: 20.01, 0.01, 0.222, 0.0001, 0.001231
            token_type (str): The type of the token to transfer which can be {available_tokens_formatted}
            receiver_address (str): The public key of the receiver's wallet.
    """
    service = get_user_data_by_key(store, "blockchain_service")
    config = get_network_config(store)

    wallet_public_key = get_user_data_by_key(store, key=f"{config.config_keys[1]}_public_key")
    
    gas_cost_native_token = await service.estimate_transfer_gas(receiver_address, token_type, decimal_amount)
    balance_native_token = await service.get_balance(wallet_public_key, config.token_type)

    if (float(gas_cost_native_token['estimated_total_gas_cost']) + decimal_amount  >= balance_native_token):
        needed_amount = (float(gas_cost_native_token['estimated_total_gas_cost']) + decimal_amount - balance_native_token)
        return {
            "error": True,
            "error_message": f"Your balance is not enough to execute the transaction. You need more than {needed_amount} {config.token_type} to execute the transaction.",
        }
    return {
        "is_wallet_balance_verified": True
    }

# @tool
@retry_decorator()
async def estimate_total_gas_cost_swap_tool(store: Annotated[BaseStore, InjectedStore()], decimal_amount: float, src_token_type: str, des_token_type: str):
    """
        Estimate total gas cost for the swap transaction
        Agrs:
            decimal_amount (float): the decimal number format. Example: 20.01, 0.01, 0.222
            src_token_type: The type of the source token which can be MOVE, USDC, USDT, WBTC, or WETH
            des_token_type: The type of the destination token which can be MOVE, USDC, USDT, WBTC, or WETH
        Return:
            estimated_total_gas_cost: float type, the estimated gas cost for transfering an amount of token
            currency: str type, the currency symbol of the amount
    """
    return await estimate_total_gas_cost_swap(store, decimal_amount, src_token_type, des_token_type)

# @tool
@retry_decorator()
async def verify_balance_swap(store: Annotated[BaseStore, InjectedStore()], decimal_amount: float, src_token_type: str, des_token_type: str):
    """
        Verify the user's wallet balance before executing the swap transaction
    """
    try:
        service = get_user_data_by_key(store, "blockchain_service")
        config = get_network_config(store)
        
        print("\n============ VERIFY BALANCE SWAP DEBUG ============")
        print(f"Input params: amount={decimal_amount}, src={src_token_type}, des={des_token_type}")
        print(f"Config: {config.__dict__}")
        
        wallet_public_key = get_user_data_by_key(store, key=f"{config.config_keys[1]}_public_key")
        print(f"Wallet public key: {wallet_public_key}")

        gas_cost_native_token = await service.estimate_swap_gas(decimal_amount, src_token_type, des_token_type)
        print(f"Gas cost estimation: {gas_cost_native_token}")
        
        balance_native_token = await service.get_balance(wallet_public_key, config.token_type)
        print(f"Native token balance: {balance_native_token}")
        
        balance_source_token = await service.get_balance(wallet_public_key, src_token_type)
        print(f"Source token balance: {balance_source_token}")

        is_gas_cost_verified = balance_native_token >= gas_cost_native_token["estimated_total_gas_cost"]
        is_source_token_balance_verified = balance_source_token >= decimal_amount if (src_token_type != config.token_type) else balance_native_token + gas_cost_native_token["estimated_total_gas_cost"] >= decimal_amount
        
        print(f"Gas cost verification: {is_gas_cost_verified}")
        print(f"Source token balance verification: {is_source_token_balance_verified}")
        print(f"Native token type: {config.token_type}")
        print(f"Comparison values:")
        print(f"- Native balance: {balance_native_token}")
        print(f"- Gas cost: {gas_cost_native_token['estimated_total_gas_cost']}")
        print(f"- Source balance: {balance_source_token}")
        print(f"- Required amount: {decimal_amount}")
        print("===============================================\n")

        if (is_gas_cost_verified and is_source_token_balance_verified):
            return {
                "is_wallet_balance_verified": True,
                "balances": {
                    "native": balance_native_token,
                    "source": balance_source_token
                }
            }
        
        error_message = ""
        if not is_source_token_balance_verified:
            error_message = f"Your balance is not enough to execute the transaction. You have {balance_source_token} {src_token_type} but need {decimal_amount}"
        else:
            error_message = f"Your balance is not enough to pay for the gas cost. You have {balance_native_token} {config.token_type} but need {gas_cost_native_token['estimated_total_gas_cost']}"
        
        return {
            "error": True,
            "error_message": error_message,
            "balances": {
                "native": balance_native_token,
                "source": balance_source_token
            }
        }
        
    except Exception as e:
        print("\n============ VERIFY BALANCE SWAP ERROR ============")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Full traceback:")
        print(traceback.format_exc())
        print("Store data:")
        print(f"- Config keys: {config.config_keys if 'config' in locals() else 'Not available'}")
        print(f"- Wallet key: {wallet_public_key if 'wallet_public_key' in locals() else 'Not available'}")
        print("================================================\n")
        return {
            "error": True,
            "error_message": f"An error occurred while verifying balance: {str(e)}",
            "debug_info": {
                "error_type": str(type(e)),
                "traceback": traceback.format_exc()
            }
        }

# @tool
@retry_decorator()
async def swap_tokens(store: Annotated[BaseStore, InjectedStore()], decimal_amount: float, src_type: str, des_type: str):
    """
        Transfer an amount of token in src_type to des_type.
        Args: 
            src_type: The type of the token (can be USDC, USDT, WBTC, WETH, MOVE)
            decimal_amount (float): the decimal number format. Example: 20.01, 0.01, 0.222
            des_type: The type of the token (can be USDC, USDT, WBTC, WETH, MOVE)
    """

    service = get_user_data_by_key(store, "blockchain_service")
    config = get_network_config(store)
    
    wallet_public_key = get_user_data_by_key(store, key=f"{config.config_keys[1]}_public_key")
    
    result = await service.swap_tokens(decimal_amount, src_type, des_type)
    
    if (result['success']):
        new_balance = await service.retrieve_available_tokens(wallet_public_key)
        current_balance = get_user_data_by_key(store, "available_tokens")

        return {
            "success": True,
            "transaction_hash": result['hash'],
            "src_type": src_type,
            "src_amount": f"{decimal_amount}",
            "des_type": des_type,
            "des_amount": f"{round(new_balance.get(des_type, 0) - current_balance.get(des_type, 0), 3)} tokens"
        }

    return {
        "success": False,
        "error": True
    }

# @tool
@retry_decorator()
async def calculate_pair_price(store: Annotated[BaseStore, InjectedStore()], src_type: str, des_type: str):
    """
        Calculate the pair price 
        Args: 
            src_type: The type of the token (can be USDC, USDT, WBTC, WETH, MOVE)
            des_type: The type of the token (can be USDC, USDT, WBTC, WETH, MOVE)
    """
    service = get_user_data_by_key(store, "blockchain_service")

    result = await service.calculate_price_of_pair(src_type, des_type)

    return {
        "price": result["price"],
        "pair": f"{src_type}/{des_type}"
    }

# @tool
@retry_decorator()
async def suggest_yields(store: Annotated[BaseStore, InjectedStore()], yield_type: str):
    """
        Suggest yields for a wallet address.

        This function retrieves potential yield opportunities for a given wallet address
        by interacting with the blockchain service. It leverages the service's capability
        to find yield opportunities based on the wallet's current holdings and the network's
        available yield strategies.

        Args:
            yield_type: The yield_type of the yield suggestion the user wants to get. Can only be `safe`, `moderate`, or `high`

        Returns:
            A list of potential yield opportunities with relevant details.
    """
    service = get_user_data_by_key(store, "blockchain_service")
    config = get_network_config(store)
    
    wallet_address = get_user_data_by_key(store, key=f"{config.config_keys[1]}_public_key")

    yields = service.find_yields_for_wallet(wallet_address, yield_type)

    return {"yields": yields}

# @tool
@retry_decorator()
async def get_user_information(**kwargs):
    """
        Retrieve the user information
    """

    return {
        "primary_address": "San Francisco, CA",
        "annualized_income": 250000,
        "marry_status": "single"
    }

# @tool
@retry_decorator()
async def get_transaction_data(**kwargs):
    """
        Retrieve transaction data for a user from the database.

        This function interacts with the blockchain service to fetch all transactions
        associated with the user's wallet address. It utilizes the stored state to
        determine the past steps and ensure that the transaction data is relevant to
        the user's current context.

        Returns:
            A list of transactions related to the user's wallet address, including
            details such as transaction ID, amount, date, and status.
    """

    transactions = [
        {
            "assets": "WBTC",
            "time_held": "LONG",
            "amount_before_trade": 2200121.00,
            "amount_after_trade": 200000.00
        },
        {
            "assets": "POL/MATIC",
            "time_held": "LONG",
            "amount_before_trade": 808999.00,
            "amount_after_trade": 0.00
        },
        {
            "assets": "WETH",
            "time_held": "LONG",
            "amount_before_trade": 1790299.12,
            "amount_after_trade": 0.00
        },
        {
            "assets": "USDC",
            "time_held": "",
            "amount_before_trade": 90000.00,
            "amount_after_trade": 2689298.12
        },
        {
            "assets": "USDT",
            "time_held": "",
            "amount_before_trade": 300000.00,
            "amount_after_trade": 1476900.00
        },
        {
            "assets": "PEPE",
            "time_held": "SHORT",
            "amount_before_trade": 315000.00,
            "amount_after_trade": 0.00
        },
        {
            "assets": "AAVE",
            "time_held": "SHORT",
            "amount_before_trade": 548900.00,
            "amount_after_trade": 0.00
        },
        {
            "assets": "LINK",
            "time_held": "LONG",
            "amount_before_trade": 313000.00,
            "amount_after_trade": 0.00
        }
    ]

    return {"transactions": transactions}

# @tool
@retry_decorator()
async def calculate_taxes(store: Annotated[BaseStore, InjectedStore], past_steps: Annotated[list, InjectedState("past_steps")]):
    """
        Calculate taxes of the user based on their transaction histories and information
    """
    def calculate_tax(income, brackets):
        tax = 0
        for lower, upper, rate in brackets:
            if income > lower:
                taxable_income = min(income, upper) - lower
                tax += taxable_income * rate
            else:
                break
        return tax
    
    # The last 2 steps are used to calculate the taxes
    past_steps = past_steps[-2:]

    # The first step is used to get the user's information
    user_info = past_steps[0][1]
    if user_info["tool"] != "get_user_information":
        raise Exception("The first step is not used to get the user's information")

    # The second step is used to get the transaction data
    transaction_data = past_steps[1][1]
    if transaction_data["tool"] != "get_transaction_data":
        raise Exception("The second step is not used to get the transaction data")
    
    # Calculate the long-term and short-term gains
    long_term_gains = []
    short_term_gains = []

    for transaction in transaction_data["transactions"]:
        gain = transaction["amount_before_trade"] - transaction["amount_after_trade"]
        if transaction["time_held"] == "LONG":
            long_term_gains.append(
                {
                    "assets": transaction["assets"],
                    "gain": gain
                }
            )
        elif transaction["time_held"] == "SHORT":
            short_term_gains.append(
                {
                    "assets": transaction["assets"],
                    "gain": gain
                }
            )

    # Find the deduction for the user
    # Assume user does not have any other deductions except the standard deduction
    standard_deduction = standard_deduction_map[user_info["marry_status"]]
    california_standard_deduction = california_standard_deduction_map[user_info["marry_status"]]

    # Calculate the total ordinary taxable income and the total capital gains income
    total_ordinary_income = sum([gain["gain"] for gain in short_term_gains]) + user_info["annualized_income"]
    total_capital_gains_income = sum([gain["gain"] for gain in long_term_gains])

    # Calculate the total taxable ordinary income and the total taxable capital gains income
    total_taxable_ordinary_income = total_ordinary_income - standard_deduction
    total_taxable_capital_gains_income = total_capital_gains_income - standard_deduction

    # Calculate the total california income
    total_california_income = total_ordinary_income + total_capital_gains_income
    total_taxable_california_income = total_california_income - california_standard_deduction

    ordinary_income_tax = calculate_tax(total_taxable_ordinary_income, ordinary_income_brackets[user_info["marry_status"]])
    long_term_income_tax = calculate_tax(total_taxable_capital_gains_income, long_term_gains_brackets[user_info["marry_status"]])
    california_income_tax = calculate_tax(total_taxable_california_income, california_tax_brackets[user_info["marry_status"]])

    return {
        "ordinary_income_tax_parameters": {
            "total_income": total_ordinary_income,
            "total_taxable_income": total_taxable_ordinary_income,
            "total_tax": ordinary_income_tax,
            "standard_deduction": standard_deduction
        },
        "long_term_income_tax_parameters": {
            "total_income": total_capital_gains_income,
            "total_taxable_income": total_taxable_capital_gains_income,
            "total_tax": long_term_income_tax,
            "standard_deduction": standard_deduction
        },
        "california_income_tax_parameters": {
            "total_income": total_california_income,
            "total_taxable_income": total_taxable_california_income,
            "total_tax": california_income_tax,
            "standard_deduction": california_standard_deduction
        },
        "total_taxes": ordinary_income_tax + long_term_income_tax + california_income_tax,
        "user_info": user_info
    }

# @tool
@retry_decorator()
async def check_single_token_price(store: Annotated[BaseStore, InjectedStore()], token_type: str):
    """
        Check the price of a single token
        Args:
            token_type: The type of the token (can be USDC, USDT, WBTC, WETH, MOVE, BTC, ETH, POL, ARB, etc.)
    """
    service = get_user_data_by_key(store, "blockchain_service")

    return service.check_single_token_price(token_type)

def search_with_perser(text: str) -> str:
    """
        Search a specific term 
        Args:
            text: The word need to be searched.
    """

    load_dotenv()
    api_key = os.getenv("SERPER_API_KEY")
    perser_service = PerserSearchService(api_key)

    return perser_service.search(text)