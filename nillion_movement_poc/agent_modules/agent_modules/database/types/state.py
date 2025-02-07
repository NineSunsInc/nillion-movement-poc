import operator
import chainlit as cl

from langchain_core.messages import BaseMessage
from typing import Annotated, List, Sequence, Tuple
from agent_modules.database.types.safety_result import SafetyResult
from agent_modules.database.types.search_result import SearchResult
from typing_extensions import TypedDict
from enum import Enum
        
class Category(Enum):
    BLOCKCHAIN_ACTION = 1
    WEB3_INFORMATION = 2
    PRIVATE_DATA = 3

    REJECTED = 4
    NEEDS_CLARIFICATION = 5

    # For final response, this category won't be classified by the classifier
    FINAL_RESPONSE = 6

class Subcategory(Enum):
    # Blockchain Action
    TRADE = 1
    SEND = 2
    CROSS_CHAIN = 3
    PAIR_PRICE = 4
    PAIR_QUERY = 5
    TOKEN_PRICE = 6
    TOKEN_QUERY = 7
    WALLET_BALANCE = 8
    OTHER = 13

    # INFORMATIONAL
    MIGHTY = 9
    PARTNERS = 10
    GENERAL = 11

    # PRIVATE_DATA
    MYSELF = 12

class PlanExecute(TypedDict):
    """State definition for the agent workflow"""
    ask_human_question: str
    chain: str
    dump_field: str # This field is used for temporary update the state, for steps that don't need to update the graph state
    error_message: str
    input: str
    is_cancelled: bool
    next_executor_node: str
    rejected_reason: str
    response: str
    total_gas: dict
    user_data: str

    category: Category
    subcategory: Subcategory
    safety_result: SafetyResult
    tasks: List[cl.Task]

    plan: List[str]
    past_steps: List[Tuple]
    sub_prompts: List[str]
    retrieved_data: List[SearchResult]
    human_responses: List[Tuple[str, str]]
    
    messages: Annotated[List[Tuple], operator.add]
    processed_sub_prompts: Annotated[List[Tuple[str, str]], operator.add]

class ExecutorState(TypedDict):
    """The state of the executor"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    tool_retries: int
    past_steps: List[Tuple]