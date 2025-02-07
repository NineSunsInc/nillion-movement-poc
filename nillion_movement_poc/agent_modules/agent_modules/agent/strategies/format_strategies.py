import time
import csv
import chainlit as cl

from collections import defaultdict
from typing import List
from abc import ABC, abstractmethod

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from langgraph.store.base import BaseStore

from agent_modules.database.const.prompt import *
from agent_modules.database.types.search_result import SearchResult
from agent_modules.database.types.state import PlanExecute
from agent_modules.database.repositories.response_record_repository import ResponseRecordRepository
from agent_modules.agent.resources.agent_config import DEBUG, AgentConfig

class FormatStrategy(ABC):
    def __init__(self) -> None:
        self.response_record_repository = ResponseRecordRepository()

    def cache_response_record(self, state: PlanExecute, response):
        # TODO: Temporary remove this for caching the user's response
        return

        self.response_record_repository.insert_record(
            input = state["input"],
            response = response,
            past_steps = state["past_steps"],
            category = state.get("category", None),
            chain = state["chain"],
            expiration = int(time.time()) + 300 # Set the expiration for a response record 5 mins ~ 300 seconds
        )

    @abstractmethod
    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        pass

    @abstractmethod
    def add_prompt_to_node(self, node: BaseChatModel):
        pass

    def _remove_executed_sub_prompt(self, state: PlanExecute, response: str, is_failed: bool = False):
        sub_prompts = state.get("sub_prompts", [])
        tasks = state.get("tasks", [])
        processed_prompt = sub_prompts[0] if len(sub_prompts) > 0 else None
        
        if processed_prompt:
            updated_tasks = [task if task.title != processed_prompt else cl.Task(title=processed_prompt, status=cl.TaskStatus.DONE if not is_failed else cl.TaskStatus.FAILED) for task in tasks]
        else:
            updated_tasks = tasks

        return {
            "processed_sub_prompts": [(state.get("input", ""), response)] if len(sub_prompts) == 0 else [(sub_prompts[0], response)],
            "sub_prompts": sub_prompts[1:] if len(sub_prompts) > 0 else [],
            "tasks": updated_tasks
        }

class ConcreteFormatStrategyAction(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()

    def add_prompt_to_node(self, node: BaseChatModel):
        prompt = ChatPromptTemplate([
            ("system", FORMATTER_PROMPT),
            ("placeholder", "{messages}")
        ])

        return (prompt | node)

    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## RESPONSE FORMATTER ##############")
        updated_node = self.add_prompt_to_node(node)
        
        trace = ""
        if (len(state["past_steps"]) == 0):
            trace = "Fail to do the action. Please check your input"
        else:
            for i, step in enumerate(state["past_steps"]):
                trace += f"Step {i}: {step[0]}\nAgent Response: {step[1]}\n\n"
        
        # Debug
        if (DEBUG):
            print("Current State", state["past_steps"])
            print("Trace:", trace)

        is_failed = 'error_message' in state.keys() and state['error_message'] not in ["", None]
        if (is_failed):
            trace += f"\nError: {state['error_message']}"
        
        output = updated_node.invoke(
            {
                'input': state["input"],
                'trace': trace,
                'messages': [("user","")]
            }
        )

        self.cache_response_record(state, output.content)

        return {
            "messages": [("assistant", output.content)],
            'response': output.content,
            **self._remove_executed_sub_prompt(state, output.content, is_failed)
        }

class ConcreteFormatStrategyUserData(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()

    def add_prompt_to_node(self, node: BaseChatModel, user_information: str):
        prompt = ChatPromptTemplate([
            ("system", USER_DATA_ANSWERER_PROMPT),
            ("placeholder", "{messages}"),

            # Add data to the history for the agent to answer
            ("user", "### USER_INFORMATION\n" + user_information),
        ])

        return (prompt | node)
    
    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## USER DATA ANSWERER ##############")
        user_data = state["user_data"]
        updated_node = self.add_prompt_to_node(node, user_information=user_data)

        # Debug
        if (DEBUG):
            print("User data", state['user_data'])

        output = updated_node.invoke(
            {
                "messages": state["messages"]
            }
        )

        self.cache_response_record(state, output.content)
        
        return {
            "messages": [("assistant", output.content)],
            "response": output.content,
            **self._remove_executed_sub_prompt(state, output.content)
        }

class ConcreteFormatStrategyWeb3Info(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()

    def add_prompt_to_node(self, node: BaseChatModel, search_context: str):
        updated_prompt = WEB3_INFO_ANSWERER_PROMPT.format(search_context=search_context)

        prompt = ChatPromptTemplate([
            ("system", updated_prompt),
            ("placeholder", "{messages}"),
        ])

        return (prompt | node)
    
    def _categorize_retrieved_data(self, retrieved_data: List[SearchResult]):
        result_set = defaultdict(list)

        for doc in retrieved_data:
            result_set[doc.source].append(doc.text)

        return result_set

    def _summarize_retrieved_data(self, result_set: dict, summarize_node: BaseChatModel):
        summarized_result_set = {}

        for source, docs in result_set.items():
            combined_text = "\n\n".join([doc for doc in docs])
            output = summarize_node.invoke(
                {
                    "messages": [("user", "Create a summary of the following data: \n---\n" + combined_text)]
                }
            )

            summarized_result_set[source] = output.content

        return summarized_result_set

    def _process_json_data(self, text: str):
        return text.replace("{", "{{").replace("}", "}}")

    def _get_summarize_node(self, node: BaseChatModel):
        prompt = ChatPromptTemplate([
            ("system", SUMMARIZE_PROMPT),
            ("placeholder", "{messages}"),
        ])

        return (prompt | node)
    
    def _make_response(self, search_context: str, output: str):
        response = f"## Retrieved Data:\n{search_context}\n\n---\n"
        response += f"## Answer:\n{output}"
        return response

    def _build_search_context(self, retrieved_data: List[SearchResult], base_node: BaseChatModel):
        result_set = self._categorize_retrieved_data(retrieved_data)
        summarized_result_set = self._summarize_retrieved_data(result_set, self._get_summarize_node(base_node))
        search_context = "\n\n---\n".join([f"### Source: {source}\n### Summary: \n{self._process_json_data(content)}" for source, content in summarized_result_set.items()])
        return search_context

    def _log_to_csv(self, user_input: str, search_context: str, output: str):
        with open(f"web3_info_formatter.csv", "a", newline='') as f:
            writer = csv.writer(f)
            if f.tell() == 0:  # Check if the file is empty
                writer.writerow(["Query", "Context", "Answer"])
            writer.writerow([user_input, search_context, output])

    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## WEB3 INFORMATION ANSWERER ##############")
        retrieved_data = state['retrieved_data']

        if retrieved_data:
            search_context = self._build_search_context(retrieved_data, node)
        else:
            # No retrieved data
            search_context = ""

        if search_context == "":
            response = "I don't know, can you provide more information"
        else:
            updated_node = self.add_prompt_to_node(node, search_context=search_context)
            output = updated_node.invoke(
                {
                    "messages": state["messages"][-AgentConfig.context_window:-1] + [("user", state['input'] + "\n" + "Answer in THREE sentences")]
                }
            )

            response = output.content

        # Debug
        # if (DEBUG):
        #     self._log_to_csv(state['input'], search_context, response)

        self.cache_response_record(state, response)

        return {
            "messages": [("assistant", response)],
            "response": self._make_response(search_context, response),
            **self._remove_executed_sub_prompt(state, response)
        }

class ConcreteFormatterStrategyReject(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()
        self.reason_map = {
            "unsafe_content": "Unsafe content",
            "out_of_domain": "Out of domain"
        }

    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## REJECTION FORMATTER ##############")

        reason = self.reason_map[state['rejected_reason']]
        rejection_response = f"Your request '{state['input']}' was rejected due to the following reason: {reason}"
        
        return {
            "messages": [("assistant", rejection_response)],
            "response": rejection_response,
            **self._remove_executed_sub_prompt(state, rejection_response, is_failed=True)
        }

    
    def add_prompt_to_node(self, node: BaseChatModel):
        pass

class ConcreteFormatStrategyClarify(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()

    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## CLARIFICATION FORMATTER ##############")
        clarification_response = f"Your request '{state['input']}' needs clarification. Please provide more details so I can assist you better. Here is a question to help guide you: {state['ask_human_question']}"
        
        return {
            "messages": [("assistant", clarification_response)],
            "response": clarification_response,
            **self._remove_executed_sub_prompt(state, clarification_response)
        }
    
    def add_prompt_to_node(self, node: BaseChatModel):
        pass

# This is the final response formatter
class ConcreteFormatStrategyFinalResponse(FormatStrategy):
    def __init__(self) -> None:
        super().__init__()

    def format(self, node: BaseChatModel, state: PlanExecute, store: BaseStore):
        print("\n############## FINAL RESPONSE FORMATTER ##############")
        processed_sub_prompts = state.get("processed_sub_prompts", [])
        ai_input = "\n---\n".join([
            f"Prompt {i + 1}: {sub_prompt[0]}\nResponse {i + 1}: {sub_prompt[1]}"
            for i, sub_prompt in enumerate(processed_sub_prompts)
        ])

        updated_node = self.add_prompt_to_node(node)
        final_response = updated_node.invoke(
            {
                "trace": ai_input,
                "messages": [("user", "")]
            }
        )

        return {
            "messages": [("system", "Previous context:\n" + final_response.content)],
            "response": final_response.content,
        }

    def add_prompt_to_node(self, node: BaseChatModel):
        prompt = ChatPromptTemplate([
            ("system", FINAL_RESPONSE_FORMATTER_PROMPT),
            ("placeholder", "{messages}"),
        ])
        return (prompt | node)
    