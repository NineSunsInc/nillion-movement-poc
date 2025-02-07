from abc import ABC, abstractmethod
from typing import Any, Dict
from agent_modules.database.const.chain_config import ChainConfig
import chainlit as cl

class ResponseFormatter(ABC):
    @abstractmethod
    def format(self, response: Dict[str, Any]) -> str:
        pass
    
    def _get_transaction_link(self, tx_hash: str) -> str:
        # Get the current chain config
        chain_config = ChainConfig.get_network_config(cl.user_session.get("current_chain"))
        # Generate the explorer URL
        return chain_config.explorer.get_transaction_url(tx_hash)

class TransferResponseFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Transaction Failed: {response.get('trace', 'Unknown error')}"
        
        # Get the current chain config
        tx_hash = response.get("transaction_hash", "N/A")
        
        # Generate the explorer URL
        explorer_url = self._get_transaction_link(tx_hash)
        
        return (
            "✅ Transfer Successful!\n"
            f"Transaction Hash: [{tx_hash}]({explorer_url})\n"
            f"Amount Transferred: {response.get('amount', 'N/A')}"
        )

class BalanceResponseFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to fetch balance: {response.get('trace', 'Unknown error')}"
        
        balance_info = "💰 Your Wallet Balance:\n"
        for token, amount in response.items():
            if (token != "tool"):
                balance_info += f"• {token}: {amount}\n"
        return balance_info

class GasEstimateFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Gas estimation failed: {response.get('trace', 'Unknown error')}"
        
        return (
            "⛽ Gas Estimate:\n"
            f"• Estimated Cost: {response.get('estimated_total_gas_cost', 'N/A')} "
            f"{response.get('currency', 'tokens')}"
        )
    
class GasConfirmFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Gas estimation failed. Please check your wallet balance and try again."
        
        return (
            "⛽ This is the estimated gas cost for all your actions, please confirm to proceed:\n"
            f"• Estimated Cost: {response.get('estimated_total_gas_cost', 'N/A')} "
            f"{response.get('currency', 'tokens')}"
        )

class SwapResponseFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if not response.get("success"):
            return f"❌ Swap Failed: {response.get('trace', 'Unknown error')}"
        
        tx_hash = response.get("transaction_hash", "N/A")
        explorer_url = self._get_transaction_link(tx_hash)
        
        return (
            "🔄 Swap Successful!\n"
            f"• Transaction Hash: [{tx_hash}]({explorer_url})\n"
            f"• From: {response.get('src_type', 'N/A')}\n"
            f"• To: {response.get('des_type', 'N/A')}"
        )

class BalanceVerificationFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"⚠️ {response.get('error_message', 'Insufficient balance')}"
        return "✅ Balance verified! You have sufficient funds for this transaction."
    
class PairPriceFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to calculate pair price: {response.get('trace', 'Unknown error')}"
        
        price = response.get("price")
        pair = response.get("pair")
        
        # Format price with appropriate decimal places
        formatted_price = f"{float(price):.6f}" if float(price) < 0.01 else f"{float(price):.4f}"
        
        return (
            "💱 Token Pair Price:\n"
            f"• Price: {formatted_price}\n"
            f"• Pair: {pair}"
        )

class TokenPriceFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to retrieve token price: {response.get('trace', 'Unknown error')}"
        
        return f"💱 Token Price (based on CoinGecko API): ${response.get('price', 'N/A'):,.2f}"

class YieldFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to retrieve yield information: {response.get('trace', 'Unknown error')}"

        yields = response.get("yields", {})
        if not yields:
            return "ℹ️ No yield opportunities available."

        formatted_yields = []

        formatted_yields.append("| Token Symbol | Name | Symbol | Price | Platform | Liquidity | APY | Base APY | Volume USD (1d) | Volume USD (7d) |")
        formatted_yields.append("|--------------|------|--------|-------|----------|-----------|-----|----------|-----------------|-----------------|")

        for token_symbol, yield_info_list in yields.items():
            for yield_info in yield_info_list:
                formatted_yields.append(
                    f"| {token_symbol} | {yield_info['name']} | {yield_info['symbol']} | ${yield_info['price']:,.2f} | {yield_info['platform']} | ${yield_info['liquidity']:,.2f} | {yield_info['metrics']['apy']:,.2f}% | {yield_info['metrics']['base_apy']:,.2f}% | ${yield_info['metrics']['volume_usd_1d']:,.2f} | ${yield_info['metrics']['volume_usd_7d']:,.2f} |"
                )

        return "📈 Yield opportunities based on your top 3 assets with the highest USD balance (if yield options exist):\n" + "\n".join(formatted_yields)

class GetUserInfoFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to get user info: {response.get('trace', 'Unknown error')}"
        
        address = response.get("primary_address", "N/A")
        income = response.get("annualized_income", 0)
        marry_status = response.get("marry_status", "N/A")

        return (
            f"📊 **User Info:**\n"
            f"• Address: **{address}**\n"
            f"• Annualized Income: **${income:,.2f}**\n"
            f"• Marital Status: **{marry_status}**"
        )
    
class GetTransactionDataFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to get transaction data: {response.get('trace', 'Unknown error')}"
        
        transaction_data = response.get("transactions", {})
        if not transaction_data:
            return "ℹ️ No transaction data available."

        formatted_transactions = []

        formatted_transactions.append("| Asset | Time Held | Amount Before Trade | Amount After Trade |")
        formatted_transactions.append("|-------|-----------|---------------------|--------------------|")

        for transaction in transaction_data:
            formatted_transactions.append(
                f"| {transaction['assets']} | {transaction['time_held']} | ${transaction['amount_before_trade']:,.2f} | ${transaction['amount_after_trade']:,.2f} |"
            )

        return "📊 Transaction Data:\n" + "\n".join(formatted_transactions)

class TaxCalculatorFormatter(ResponseFormatter):
    def format(self, response: Dict[str, Any]) -> str:
        if response.get("error"):
            return f"❌ Failed to calculate tax: {response.get('trace', 'Unknown error')}"
        
        ordinary_income_tax_parameters = response.get("ordinary_income_tax_parameters", {})
        long_term_income_tax_parameters = response.get("long_term_income_tax_parameters", {})
        california_income_tax_parameters = response.get("california_income_tax_parameters", {})

        def format_tax_table(tax_parameters: Dict[str, Any], tax_type: str) -> str:
            if not tax_parameters:
                return ""
            
            additional_info = {
                "Ordinary Income": "This tax is applied to your regular earnings such as wages, salaries, and bonuses, including short-term gains from assets held for less than a year.",
                "Long Term Income": "This tax, also called Capital Gains, is applied to profits from assets held for more than a year.",
                "California Income": "This tax is specific to income earned within the state of California."
            }
            
            return (
                f"### {tax_type} Tax\n"
                f"{additional_info.get(tax_type, '')}\n"
                "| Description | Amount |\n"
                "|-------------|--------|\n"
                f"| Total Income | ${tax_parameters.get('total_income', 0):,.2f} |\n"
                f"| Standard Deduction | ${tax_parameters.get('standard_deduction', 0):,.2f} |\n"
                f"| Total Taxable Income | ${tax_parameters.get('total_taxable_income', 0):,.2f} |\n"
                f"| Total Tax | ${tax_parameters.get('total_tax', 0):,.2f} |\n"
            )

        ordinary_income_tax_table = format_tax_table(ordinary_income_tax_parameters, "Ordinary Income")
        long_term_income_tax_table = format_tax_table(long_term_income_tax_parameters, "Long Term Income")
        california_income_tax_table = format_tax_table(california_income_tax_parameters, "California Income")

        total_taxes = response.get("total_taxes", 0)
        total_taxes_table = (
            "### Total Taxes\n"
            "| Description | Amount |\n"
            "|-------------|--------|\n"
            f"| Total Taxes | ${total_taxes:,.2f} |\n"
        )


        user_info = response.get("user_info", {})
        address = user_info.get("primary_address", "N/A")
        income = user_info.get("annualized_income", 0)
        marry_status = user_info.get("marry_status", "N/A")

        description = (
            f"Based on your primary address location pulled from the vault in **{address}** and "
            f"your annualized income of **${income:,.2f}**, "
            f"**{marry_status}** marital status, your activities showed you have an estimated tax burden of **${total_taxes:,.2f}**. "
            f"The brackets information are retrieved from this link: https://smartasset.com/investing/california-capital-gains-tax. "
            f"Details are provided below."
        )

        disclaimer = (
            "***Disclaimer:*** "
            "*The above calculation is a highly simplified, hypothetical estimation based solely on the provided numbers and assumptions that do not reflect real-world complexity. "
            "It applies uniform top-tier tax rates rather than progressive brackets, assumes a zero or negligible cost basis, and ignores potential deductions, credits, exemptions, "
            "tax-loss harvesting strategies, or other tax planning opportunities. It also excludes income sources outside of these specific transactions and any changes in tax laws or thresholds. "
            "The resulting figures are not accurate tax advice, financial guidance, or recommendations. Every individual's tax situation is unique, and this rough estimate should not be relied upon "
            "as a substitute for professional guidance. For an accurate assessment of your tax liability, consult a qualified tax professional or attorney who can review your complete financial situation "
            "and advise you according to current tax regulations.*"
        )


        return (
            f"{description}\n\n"
            "📊 Tax Calculation Results:\n\n"
            f"{ordinary_income_tax_table}\n"
            f"{long_term_income_tax_table}\n"
            f"{california_income_tax_table}\n"
            f"{total_taxes_table}\n"
            f"{disclaimer}"
        )