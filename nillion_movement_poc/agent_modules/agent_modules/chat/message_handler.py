import chainlit as cl

from typing import List, Union, cast
from collections import defaultdict
from agent_modules.chat.executor_response_formatter import (
    TransferResponseFormatter,
    BalanceResponseFormatter,
    GasEstimateFormatter,
    GasConfirmFormatter,
    SwapResponseFormatter,
    BalanceVerificationFormatter,
    PairPriceFormatter,
    YieldFormatter,
    TaxCalculatorFormatter,
    GetUserInfoFormatter,
    GetTransactionDataFormatter,
    TokenPriceFormatter
)

formatter_config_map = {
    "transfer_token": TransferResponseFormatter(),
    "get_wallet_balance_tool": BalanceResponseFormatter(),
    "estimate_total_gas_cost_transfer_tool": GasEstimateFormatter(),
    "estimate_total_gas_cost_swap_tool": GasEstimateFormatter(),
    "verify_balance_transfer": BalanceVerificationFormatter(),
    "verify_balance_swap": BalanceVerificationFormatter(),
    "swap_tokens": SwapResponseFormatter(),
    "calculate_pair_price": PairPriceFormatter(),
    "suggest_yields": YieldFormatter(),
    "get_user_information": GetUserInfoFormatter(),
    "get_transaction_data": GetTransactionDataFormatter(),
    "calculate_taxes": TaxCalculatorFormatter(),
    "check_single_token_price": TokenPriceFormatter()
}

class MessageHandler:
    def __init__(self) -> None:
        pass

    async def handle_message(self, message: cl.Message):
        try:
            app = cl.user_session.get("app_graph")
            uuid_value = cl.user_session.get("uuid")
            memory = cl.user_session.get("memory")
            chain = cl.user_session.get("current_chain")
            history_messages = cl.user_session.get("history_messages", [])

            config = {
                "configurable": { "thread_id": uuid_value },
                # "callbacks": [cl.LangchainCallbackHandler()], # Disable since this causes Trace coroutine error
                "recursion_limit": 50 # The recursion limit sets the number of supersteps that the graph is allowed to execute before it raises an error.
            }
            inputs = {
                "input":  message.content, 
                "chain": chain,
                "messages": history_messages
            }

            await self._start_chat_flow(app, config, inputs)

            while (len(app.get_state(config).next) != 0):
                messages = app.get_state(config)
                current_human_responses = messages.values.get("human_responses", [])

                if (messages.next[0] == "ask_user"):
                    question = messages.values['ask_human_question']
                    user_response = await cl.AskUserMessage(content=question, timeout=300).send()
                    if (user_response):
                        app.update_state(
                            config,
                            { 
                                "human_responses": current_human_responses + [(question, user_response['output'])],
                                "messages": [("user", user_response['output'])]
                            }
                        )

                        await self._start_chat_flow(app, config)

                elif (messages.next[0] == "confirm_gas"):
                    total_gas = messages.values["total_gas"]
                    formatted_gas = GasConfirmFormatter().format(total_gas)
                    
                    if "error" in total_gas:
                        await cl.Message(content=formatted_gas).send()
                        break

                    no_cost = True if total_gas["estimated_total_gas_cost"] == 0 else False
                    
                    if no_cost:
                        await self._start_chat_flow(app, config)
                    else:    
                        user_response = await cl.AskActionMessage(
                            content=formatted_gas,
                            actions=[
                                cl.Action(
                                    name="continue",
                                    payload={"action": "continue"},  
                                    label="✅ Continue"
                                ),
                                cl.Action(
                                    name="cancel",
                                    payload={"action": "cancel"},    
                                    label="❌ Cancel"
                                ),
                            ],
                            timeout=300
                        ).send()

                        if (user_response):
                            if (user_response["payload"]["action"] == "continue"):
                                await cl.Message(content="Great! I'll create a plan to execute your request. Please wait while I analyze the requirements and calculate the necessary steps.").send()
                                await self._start_chat_flow(app, config)
                                
                            else:
                                await cl.Message(content="Transaction cancelled. Feel free to try another trade or swap by sending a new message like:\n- 'Swap 0.1 MOVE to USDC'\n- 'Transfer 0.5 MOVE to 0x123...'").send()
                                break
            
            if (app.get_state(config).values.get('is_cancelled') == True):
                await cl.Message(content="Transaction cancelled. Feel free to try another trade or swap by sending a new message like:\n- 'Swap 0.1 MOVE to USDC'\n- 'Transfer 0.5 MOVE to 0x123...'").send()

            # Store message context
            self._store_message_context(app, config)

            memory.storage = defaultdict(lambda: defaultdict(dict))
            memory.writes = defaultdict(dict)
        except Exception as e:
            print(e)
            error_message = "I apologize, but I encountered an error processing your request. This could be due to:\n" \
                        "- A temporary system issue\n" \
                        "- Invalid input format\n" \
                        "- Connection problems\n\n" \
                        "Please try rephrasing your question or try again later. If the issue persists, contact support."
            await cl.Message(content=error_message, author="Error Handler").send()

    async def _start_chat_flow(self, app, config, inputs: dict = None):
        async for event in app.astream(inputs, config):
            formatted_events = self._format_langgraph_event(event)
            if (formatted_events):
                for element in formatted_events:
                    await element.send()

    def _store_message_context(self, app, config):
        messages = app.get_state(config).values["messages"]
        cl.user_session.set("history_messages", messages)

    def _format_langgraph_event(self, event) -> List[Union[cl.Message, cl.TaskList]]:
        event_keys = event.keys()
        if "dynamic_formatter" in event_keys:
            return [cl.Message(content=event["dynamic_formatter"]["response"], author="Mighty AI")]
        elif "planner" in event_keys:
            if (len(event["planner"]["plan"]) == 0):
                return [cl.Message(content="### Failed to create the plan", author="Mighty AI")]
            plan = "\n".join([f"- **Step {i + 1}**: {step}" for i, step in enumerate(event["planner"]["plan"])])
            return [cl.Message(content="### Successfully create the plan:\n" + plan, author="Mighty AI")]
        elif "blockchain_executor" in event_keys:
            if "past_steps" not in event["blockchain_executor"].keys():
                return None
            current_step = event["blockchain_executor"]["past_steps"][-1]
            formatted_response = self._format_executor_response(current_step[1])
            return [cl.Message(content=f"**Step**: {current_step[0]}\n**Response**: \n{formatted_response}", author="Mighty AI")]
        elif "sub_prompts_breaker" in event_keys:
            tasks = event["sub_prompts_breaker"]["tasks"]

            # TODO: Test
            return [
                cl.Message(content="Breaking down the prompt into smaller tasks...", author="Mighty AI"),
                cl.TaskList(tasks=tasks)
            ]
        elif "sub_prompts_checker" in event_keys:
            current_input = event["sub_prompts_checker"]["input"]
            tasks = event["sub_prompts_checker"]["tasks"]

            # If the input is empty, it means the agent already processed all the sub-prompts.
            if (current_input == ""):
                return None if len(tasks) == 0 else [cl.TaskList(tasks=tasks, status="Done")]
            else:
                return [
                    cl.Message(content=f"### Process prompt:\n**{current_input}**", author="Mighty AI"),
                    cl.TaskList(tasks=tasks)
                ]
        else:
            return None
        
    def _format_executor_response(self, executor_resopnse_dict: dict) -> str:
        formatter = formatter_config_map.get(executor_resopnse_dict['tool'], None)
        if not formatter:
            return str(executor_resopnse_dict)
        return formatter.format(executor_resopnse_dict)