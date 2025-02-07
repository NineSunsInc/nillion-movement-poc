import os

from typing import Dict, List

from agent_modules.agent.nodes.base import BaseNode
from agent_modules.agent.nodes.web3_retriever_node import Web3RetrieverNode
from agent_modules.agent.nodes.user_data_retriever_node import UserDataRetrieverNode
from agent_modules.agent.nodes.classifier_node import ClassifierNode
from agent_modules.agent.nodes.llm_node import LlmNode
from agent_modules.agent.nodes.executor_node import ExecutorNode
from agent_modules.agent.nodes.function_node import FunctionNode
from agent_modules.agent.nodes.formatter_node import DynamicFormatterNode
from agent_modules.classifier.blockchain_action.ft_blockchain_actions_classifier import BlockchainActionClassifier
from agent_modules.classifier.domain.ft_domain_action_classifier_v3 import (
    DomainClassifierV3, 
    SafetyClassifierV3
)
from agent_modules.classifier.run_unified_tests_v3 import UnifiedMainClassifierV3
from agent_modules.database.const.prompt import *
from agent_modules.agent.tools import (
    transfer_token,
    get_wallet_balance_tool,
    estimate_total_gas_cost_swap_tool,
    estimate_total_gas_cost_transfer_tool,
    verify_balance_transfer,
    verify_balance_swap,
    swap_tokens,
    calculate_pair_price,
    suggest_yields,
    get_user_information,
    get_transaction_data,
    calculate_taxes,
    check_single_token_price
)
from agent_modules.agent.steps import (
    DomainClassifierStep,
    SafetyClassifierStep,
    SubPromptsBreakerStep,
    SubPromptsCheckerStep,
    TaskSupervisorStep,
    PlannerStep,
    RequirementCheckerStep,
    GasEstimatorStep,
    ReadCacherStep,
    DynamicFormatterStep,
    Web3RetrieverStep,
    UserDataRetrieverStep
)
from agent_modules.database.types.node_factory_config import NodeFactoryConfig
from agent_modules.database.types.response_models import (
    PlannerResponse,
    RequirementCheckerResponse,
    GasEstimatorResponse,
    SubPromptsBreakerResponse
)

    
class NodeFactory:
    """Factory class for creating different types of nodes"""
    
    def __init__(self, config: NodeFactoryConfig):
        self.config = config
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize tool sets"""
        self.blockchain_tools = [
            transfer_token,
            get_wallet_balance_tool,
            estimate_total_gas_cost_transfer_tool,
            verify_balance_transfer,
            swap_tokens,
            estimate_total_gas_cost_swap_tool,
            verify_balance_swap,
            calculate_pair_price,
            suggest_yields,
            get_user_information,
            get_transaction_data,
            calculate_taxes,
            check_single_token_price
        ]
        self.information_tools = []
    
    def create_executor_nodes(self) -> Dict[str, ExecutorNode]:
        """Create executor nodes"""
        return {
            "blockchain_executor": ExecutorNode(
                BLOCKCHAIN_EXECUTOR_PROMPT, 
                self.config.llama_llm, 
                self.blockchain_tools
            ),
            "information_retriever": ExecutorNode(
                INFORMATION_RETRIEVER_PROMPT, 
                self.config.llama_llm, 
                self.information_tools
            )
        }
    
    def create_agent_nodes(self, executor_members: List[str]) -> Dict[str, LlmNode]:
        """Create agent nodes"""
        available_tokens = self._get_formatted_tokens()
        
        return {
            "task_supervisor": LlmNode(
                TASK_SUPERVISOR_PROMPT.format(members=executor_members),
                self.config.llama_llm,
                TaskSupervisorStep().execute
            ),
            "safety_classifier": ClassifierNode(
                SafetyClassifierStep().execute,
                SafetyClassifierV3()
            ),
            "domain_classifier": ClassifierNode(
                DomainClassifierStep().execute,
                DomainClassifierV3(),
                BlockchainActionClassifier()
            ),
            "planner": LlmNode(
                PLANNER_PROMPT.format(
                    available_tokens_formatted=available_tokens
                ),
                self.config.provided_llm,
                PlannerStep().execute,
                PlannerResponse
            ),
            "requirement_checker": LlmNode(
                REQUIREMENT_CHECKER_PROMPT.format(
                    available_tokens_formatted=available_tokens
                ),
                self.config.provided_llm,
                RequirementCheckerStep().execute,
                RequirementCheckerResponse
            ),
            "gas_estimator": LlmNode(
                GAS_ESTIMATOR_PROMPT.format(
                    available_tokens_formatted=available_tokens
                ),
                self.config.provided_llm,
                GasEstimatorStep().execute,
                GasEstimatorResponse
            ),

            "read_cacher": FunctionNode(
                ReadCacherStep().execute
            ),
            "dynamic_formatter": DynamicFormatterNode(
                self.config.llama_llm if os.getenv("DYNAMIC_FORMATTER_MODEL") == "llama" else self.config.provided_llm,
                DynamicFormatterStep().execute
            ),
            "sub_prompts_checker": FunctionNode(
                SubPromptsCheckerStep().execute
            ),
            "sub_prompts_breaker": LlmNode(
                SUB_PROMPTS_BREAKER_PROMPT,
                self.config.provided_llm,
                SubPromptsBreakerStep().execute,
                SubPromptsBreakerResponse
            )
        } 
    
    def create_rag_nodes(self) -> Dict[str, BaseNode]:
        return {
            "web3_info_retriever": Web3RetrieverNode(
                opensearch_repository=self.config.opensearch_repository,
                cross_encoder=self.config.cross_encoder,
                step=Web3RetrieverStep().execute
            ),
            "user_data_retriever": UserDataRetrieverNode(
                user_data_embedding_repository=self.config.user_data_embedding_repository,
                step=UserDataRetrieverStep().execute
            )
        }
    
    def _get_formatted_tokens(self) -> str:
        """Get formatted available tokens"""
        available_tokens = self.config.user_store.get(
            ("users", "1"), 
            "user_data"
        ).value["available_tokens"]
        
        # This will return available tokens with respected balance
        # return "\n".join([
        #     f"\t- {token_type}: {available_tokens[token_type]}"
        #     for token_type in available_tokens.keys()
        # ])

        # This will return available tokens list
        return ", ".join(available_tokens.keys())