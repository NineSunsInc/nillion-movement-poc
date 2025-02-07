import functools
import json
import chainlit as cl

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.graph import StateGraph
from langgraph.store.memory import BaseStore

from typing import List, Literal, Optional
from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute, ExecutorState
from agent_modules.database.const.prompt import BLOCKCHAIN_TOOL_CONVERTER_PROMPT
from agent_modules.agent.resources.agent_config import DEBUG
from agent_modules.agent.tools import get_user_information, get_transaction_data

class ExecutorNode(BaseNode):
    """Node for executing specific tasks with tools"""
    
    def __init__(self, prompt: str, llm: BaseChatModel, tools, tool_retries: int = 1) -> None:
        self.llm = llm
        self.prompt = prompt
        self.tool_retries = tool_retries
        self.agent = self._create_exact_tool_agent(llm)
        self.tools = tools

    def get_step(self):
        return functools.partial(self._task_executor_node, self.agent)
        
    async def _task_executor_node(self, agent, state: PlanExecute, store: BaseStore):
        print("\n############## TASK EXECUTOR ##############")
        if not state['plan']:
            return None
            
        current_task = state['plan'][0]
        previous_steps = self._format_previous_steps(state)
        executor_prompt = self._build_executor_prompt(state, previous_steps)

        async with cl.Step(name="Executing Task") as step:
            result = await self._execute_task(agent, executor_prompt, current_task, state["past_steps"], store)
            await step.stream_token(str(result))

        if DEBUG:
            print("Current state:", state)
            print("Result:", result)

        # return self._process_result(result, current_task, state)

        # TODO: [2025-01-14] For integrating with Arbitrum
        return self._process_exact_match_result(result, current_task, state)
    
    def _format_previous_steps(self, state: PlanExecute) -> str:
        if "past_steps" not in state:
            return ""
            
        return "\n".join(
            f"\tTASK {i + 1}: {step[0]}\n\tRESPONSE of TASK {i + 1}: {step[1]}"
            for i, step in enumerate(state["past_steps"])
        )
    
    def _build_executor_prompt(self, state: PlanExecute, previous_steps: str) -> str:
        return f"""
            # User's requirement:
                {state['input']}

            # Previous task output:
                {previous_steps}
        """
    
    async def _execute_task(self, agent, executor_prompt: str, current_task: str, past_steps: list, store: BaseStore):
        # If the current task is to calculate taxes, ensure past_steps contains the user info and transaction data.
        if "calculate_taxes" in current_task.lower():
            # Only update past_steps if we don't already have two entries.
            if not past_steps or len(past_steps) < 2:
                user_info_response = await get_user_information(store)
                transaction_data_response = await get_transaction_data(store)
                past_steps = [
                    ("get_user_information", user_info_response),
                    ("get_transaction_data", transaction_data_response)
                ]
        
        attention_prompt = ""
        result = await agent.ainvoke({
            "messages": [
                ("user", current_task + attention_prompt)
            ],
            "tool_retries": self.tool_retries,
            "past_steps": past_steps
        })

        json_result = json.loads(result.content)

        # Get function name and correct common misspellings
        function_name = json_result.get("name", "")
        function_name_corrections = {
            "swap_okens": "swap_tokens",
            "swaptokens": "swap_tokens",
            "swap_token": "swap_tokens"
        }
        function_name = function_name_corrections.get(function_name, function_name)
        
        params = json_result.get("params", {})
        available_tools = dict(map(lambda tool: (tool.__name__, tool), self.tools))

        if function_name in available_tools:
            function_to_call = available_tools[function_name]
            try:
                # Pass past_steps for calculate_taxes; all others remain unchanged.
                if function_name == "calculate_taxes":
                    result = await function_to_call(store=store, past_steps=past_steps, **params)
                else:
                    result = await function_to_call(store=store, **params)
            except Exception as e:
                result = {"error": str(e)}
        else:
            available_functions = ", ".join(available_tools.keys())
            result = {
                "error": f"Function {function_name} not found. Available functions: {available_functions}"
            }
        
        return {"tool": function_name, **result}
    
    def _process_exact_match_result(self, result, current_task: str, state: PlanExecute):
        return  {
            "messages": [
                ("assistant", current_task),
            ],
            "past_steps": state["past_steps"] + [(current_task, result)],
            "plan": state['plan'][1:],
            "error_message": result.get("error", None)
        }


    def _process_result(self, result, current_task: str, state: PlanExecute):
        # Remove the AI response, just get the Tool response.
        result["messages"].pop()

        tool_message = result["messages"][-1]
        if DEBUG:
            print("Current tool message:", tool_message)

        if type(tool_message) is tuple:
            # If we cannot get the tool message here, it means the AI fail to call tool -> we won't modify the state yet.

            return {
                "plan": state['plan']
            }
        else:
            error = self._check_for_errors(result)
            
            return {
                "messages": [
                    ("assistant", current_task),
                    # ("tool", tool_message.content) # Temporary remove, because it can the agent throw error tool_call_id
                ],
                "past_steps": state["past_steps"] + [(current_task, {"tool": tool_message.name, **json.loads(tool_message.content)})],
                "plan": state['plan'][1:],
                "error_message": error
            }
    
    def _check_for_errors(self, result) -> Optional[str]:
        error_keywords = ["ERROR", "error", "Error"]
        for word in error_keywords:
            if word in result["messages"][-1].content:
                return result["messages"][-1].content
        return None
    
    def _create_exact_tool_agent(self, model):
        full_prompt = ChatPromptTemplate([
            ("system", BLOCKCHAIN_TOOL_CONVERTER_PROMPT),
            ("placeholder", "{messages}")
        ])
        model = full_prompt | model

        return model

    def _create_react_agent(self, model, tools):
        full_prompt = ChatPromptTemplate([
            ("system", self.prompt),
            ("placeholder", "{messages}")
        ])
        tool_node = ToolNode(tools)
        model = full_prompt | model.bind_tools(tools)

        def _call_model(state, config):
            response = model.invoke(state, config)

            return {"messages": [response], "tool_retries": state['tool_retries'] - 1}

        def _should_continue(state) -> Literal["tools", "__end__"]:
            last_message = state["messages"][-1]
            # If there is no function call, then we finish
            if not last_message.tool_calls or state['tool_retries'] < 0:
                return "__end__"
            # Otherwise if there is, we continue
            else:
                return "tools"
            
        workflow = StateGraph(ExecutorState)

        # Define the two nodes we will cycle between
        workflow.add_node("agent", _call_model)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            _should_continue
        )

        workflow.add_edge("tools", "agent")

        graph = workflow.compile()

        return graph